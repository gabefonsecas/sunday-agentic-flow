"""Deterministic Sunday workflow engine."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Callable

from sunday.adapters.base import ExecutionResult, GitProviderAdapter, HostAdapter, TaskManagerAdapter
from sunday.adapters.github import GitHubAdapter, branch_slug
from sunday.adapters.hosts import HostRegistry
from sunday.config import ProjectConfig, Settings
from sunday.routing import ModelRouter, classify_complexity
from sunday.state import LeaseLostError, Run, RunStore
from sunday.worktrees import WorktreeManager

HIGH_RISK = re.compile(
    r"\b(drop|truncate|delete\s+all|production|produ[cç][aã]o|deploy|secret|segredo|"
    r"credential|credencial|migration\s+destructive|migra[cç][aã]o\s+destrutiva)\b",
    re.IGNORECASE,
)


class UncertainEffectError(RuntimeError):
    pass


def task_title(task: dict) -> str:
    return str(task.get("name") or task.get("title") or task.get("nome") or f"Friday {task.get('id')}")


def task_description(task: dict) -> str:
    return str(task.get("description") or task.get("descricao") or task.get("content") or "")


def _host_text_candidates(output: str):
    """Yield raw and decoded host text, including JSONL message envelopes."""
    yield output
    values = []
    try:
        values.append(json.loads(output))
    except json.JSONDecodeError:
        for line in output.splitlines():
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    for value in values:
        yield from strings(value)


def _marked_json(output: str, marker: str, expected_type):
    decoder = json.JSONDecoder()
    found = False
    decoded = []
    pattern = re.compile(rf"{re.escape(marker)}\s*:\s*")
    for candidate in _host_text_candidates(output):
        for match in pattern.finditer(candidate):
            found = True
            payload = candidate[match.end():].lstrip()
            if payload.startswith("```"):
                payload = payload.split("\n", 1)[1].lstrip() if "\n" in payload else ""
            opening = "{" if expected_type is dict else "["
            start = payload.find(opening)
            if start < 0:
                continue
            try:
                value, _ = decoder.raw_decode(payload[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, expected_type):
                decoded.append(value)
    if decoded:
        return decoded[-1]
    if found:
        raise RuntimeError(f"Host returned malformed {marker} JSON")
    return None


def sunday_result(output: str) -> dict:
    value = _marked_json(output, "SUNDAY_RESULT", dict)
    if value is None:
        return {"success": True, "confidence": None, "summary": output[-4000:]}
    return value


def sunday_stories(output: str, task: dict) -> list[dict]:
    try:
        stories = _marked_json(output, "SUNDAY_STORIES", list)
        if stories:
            return stories
    except RuntimeError:
        pass
    title = task_title(task)
    description = task_description(task)
    return [{
        "title": f"[dev] {title}",
        "description": (
            "## Context\n" + (description or title) +
            "\n\n## Outcome\nDeliver the requested behavior.\n\n"
            "## Acceptance criteria\n- [ ] Requested behavior is implemented.\n"
            "- [ ] Relevant validation passes.\n- [ ] Pull request contains evidence.\n\n"
            "## Dependencies\nnone"
        ),
    }]


class SundayEngine:
    def __init__(
        self,
        settings: Settings,
        store: RunStore | None = None,
        tasks: TaskManagerAdapter | None = None,
        git: GitProviderAdapter | None = None,
        hosts: HostRegistry | None = None,
        progress: Callable[[str, dict], None] | None = None,
        worktrees: WorktreeManager | None = None,
    ):
        self.settings = settings
        self.store = store or RunStore()
        self.tasks = tasks
        self.git = git or GitHubAdapter()
        self.hosts = hosts or HostRegistry()
        self.progress = progress
        self.worktrees = worktrees or WorktreeManager(self.store.path.parent / "worktrees")
        self._model_probes: dict[tuple[str, str, str], dict] = {}
        self._active_host: HostAdapter | None = None

    def start(self, task_ref: str, project: ProjectConfig, host_name: str = "auto") -> Run:
        previous = self.store.latest_for_task(task_ref)
        if previous:
            if previous.state == "completed":
                raise RuntimeError(
                    f"Task already completed by Sunday run {previous.id}. "
                    "Create a new Friday item for additional work."
                )
            if previous.state in {"paused", "failed"}:
                instruction = "resume it" if previous.state == "paused" else "create a new Friday item"
                raise RuntimeError(
                    f"Task has Sunday run {previous.id} in {previous.state}; {instruction}."
                )
            if self.store.active_for_task(task_ref):
                raise RuntimeError(f"Task already has an active Sunday run: {task_ref}")
            self.store.acquire_lease(previous.id)
            self.store.event(
                previous.id, "run.recovered", previous.state,
                {"reason": "expired lease", "execution": "automatic"},
            )
            return self.execute(previous.id, project)
        host = self.hosts.detect(host_name if host_name != "auto" else self.settings.default_host)
        run = self.store.create(task_ref, project.name, host.name, {"repository": str(project.repository)})
        return self.execute(run.id, project)

    def resume(self, run_id: str, project: ProjectConfig, approved: bool = False) -> Run:
        run = self.store.get(run_id)
        self.store.acquire_lease(run_id)
        if approved:
            self.store.update_metadata(run_id, {"high_risk_approved": True})
        if run.state == "paused":
            if not run.resume_state:
                raise RuntimeError("Paused run has no resumable state")
            self.store.transition(run_id, run.resume_state, {"approved": approved})
        return self.execute(run_id, project)

    def execute(self, run_id: str, project: ProjectConfig) -> Run:
        initial = self.store.get(run_id)
        if initial.state in {"completed", "failed", "paused"}:
            return initial
        try:
            with self.store.heartbeat_lease(run_id, self._cancel_active_host):
                while True:
                    run = self.store.get(run_id)
                    if run.state in {"completed", "failed", "paused"}:
                        return run
                    handler = getattr(self, f"_phase_{run.state}")
                    handler(run, project)
        except LeaseLostError:
            raise
        except UncertainEffectError as exc:
            run = self.store.get(run_id)
            self.store.event(run_id, "effect.uncertain", run.state, {"error": str(exc)})
            self._sync_failed_safely(run, project)
            return self.store.transition(run_id, "paused", {"reason": str(exc)})
        except Exception as exc:
            run = self.store.get(run_id)
            error = str(exc)
            self.store.event(run_id, "phase.error", run.state, {"error": error})
            try:
                if self.tasks and run.metadata.get("task_id"):
                    self._effect(
                        run, f"comment:error:{run.state}",
                        lambda error=error: self.tasks.comment(
                            int(run.metadata["task_id"]),
                            f"[sunday:{run.id}] Blocked during {run.state}. Evidence: {error}",
                        ),
                    )
            except Exception as comment_error:
                self.store.event(run_id, "friday.comment_failed", run.state, {"error": str(comment_error)})
            self._sync_failed_safely(run, project)
            return self.store.transition(run_id, "paused", {"reason": str(exc)})

    def _phase_intake(self, run: Run, project: ProjectConfig) -> None:
        if run.metadata.get("review_only"):
            self._phase_review_intake(run, project)
            return
        self._require_project(project)
        task = self._tasks().get_task(run.task_ref, project.board_id)
        task_id = int(task["id"])
        repository = self.git.inspect_repository(project.repository)
        run = self.store.update_metadata(run.id, {
            "task": task, "task_id": task_id, "title": task_title(task),
            "description": task_description(task), "repository_state": repository,
        })
        base = self._base_branch(project, run)
        branch = branch_slug(run.task_ref, run.metadata["title"], run.id)
        worktree = self._effect(
            run,
            "git:create_worktree",
            lambda: self.worktrees.create(project.repository, run.id, branch, base),
            reconcile=lambda _: self.worktrees.inspect(project.repository, run.id, branch),
            intent={"branch": branch, "base": base},
        )
        run = self.store.set_worktree(run.id, worktree["path"])
        claim = self._effect(
            run, "friday:claim",
            lambda: self._tasks().claim_task(
                task, int(project.workspace_id), int(project.board_id), project.people_column
            ),
            reconcile=self._friday_reconciler(
                "reconcile_claim", run.task_ref, int(project.workspace_id),
                int(project.board_id), project.people_column,
            ),
            intent={"task_id": task_id},
        )
        ai_mark = None
        if project.ai_column:
            ai_mark = self._effect(
                run, "friday:mark_ai",
                lambda: self._tasks().mark_ai(
                    task_id, int(project.board_id), project.ai_column
                ),
                reconcile=self._friday_reconciler(
                    "reconcile_cell", run.task_ref, int(project.board_id),
                    project.ai_column, "true",
                ),
                intent={"task_id": task_id, "column": project.ai_column, "value": "true"},
            )
        run = self.store.update_metadata(run.id, {
            "claim": claim, "ai_mark": ai_mark, "base_branch": base,
            "branch": branch, "branch_result": worktree,
        })
        self._sync_friday(run, project, "discovery")
        self.store.transition(run.id, "discovery")

    def _phase_discovery(self, run: Run, project: ProjectConfig) -> None:
        if run.metadata.get("review_only"):
            self.store.transition(run.id, "stories")
            return
        prompt = self._prompt(run, "discovery", read_only=True)
        result = self._routed(run, project, "discovery", prompt, read_only=True)
        self.store.update_metadata(run.id, {"discovery": result.output})
        self._sync_friday(run, project, "stories")
        self.store.transition(run.id, "stories")

    def _phase_stories(self, run: Run, project: ProjectConfig) -> None:
        if run.metadata.get("review_only"):
            self.store.transition(run.id, "publication")
            return
        stories = sunday_stories(run.metadata.get("discovery", ""), run.metadata["task"])
        self.store.update_metadata(run.id, {"stories": stories})
        self._sync_friday(run, project, "publication")
        self.store.transition(run.id, "publication")

    def _phase_publication(self, run: Run, project: ProjectConfig) -> None:
        if run.metadata.get("review_only"):
            self.store.transition(run.id, "implementation")
            return
        published = []
        if project.publish_stories:
            for index, story in enumerate(run.metadata["stories"]):
                marker = f"\n\nSunday-Key: {run.id}:story:{index}"
                materialized = {**story, "description": story["description"] + marker}
                published.append(self._effect(
                    run, f"friday:story:{index}",
                    lambda story=materialized: self._tasks().create_story(
                        story, int(project.board_id), int(project.intake_group_id)
                    ),
                    reconcile=lambda _, marker=marker: self._tasks().find_story(
                        marker.strip(), int(project.intake_group_id)
                    ),
                    intent={"marker": marker.strip()},
                ))
        self.store.update_metadata(run.id, {"published_stories": published})
        risk_text = f"{run.metadata['title']}\n{run.metadata['description']}"
        if HIGH_RISK.search(risk_text) and not run.metadata.get("high_risk_approved"):
            self.store.transition(run.id, "paused", {"reason": "High-risk action requires approval"})
            return
        self._sync_friday(run, project, "implementation")
        self.store.transition(run.id, "implementation")

    def _phase_implementation(self, run: Run, project: ProjectConfig) -> None:
        if run.metadata.get("review_only"):
            self.store.transition(run.id, "verification")
            return
        prompt = self._prompt(run, "implementation", read_only=False)
        result = self._routed(run, project, "implementation", prompt, read_only=False)
        self.store.update_metadata(run.id, {"implementation": result.output})
        self._sync_friday(run, project, "verification")
        self.store.transition(run.id, "verification")

    def _phase_verification(self, run: Run, project: ProjectConfig) -> None:
        if run.metadata.get("review_only"):
            self.store.transition(run.id, "review")
            return
        prompt = self._prompt(run, "verification", read_only=True)
        result = self._routed(run, project, "verification", prompt, read_only=True)
        self.store.update_metadata(run.id, {"verification": result.output})
        self._sync_friday(run, project, "review")
        self.store.transition(run.id, "review")

    def _phase_review(self, run: Run, project: ProjectConfig) -> None:
        prompt = self._prompt(run, "review", read_only=True)
        result = self._routed(run, project, "review", prompt, read_only=True)
        self.store.update_metadata(run.id, {"review": result.output})
        self.store.transition(run.id, "pull_request")

    def _phase_pull_request(self, run: Run, project: ProjectConfig) -> None:
        if run.metadata.get("review_only"):
            retention_days = max(0, self.settings.completed_worktree_retention_days)
            if retention_days and not run.metadata.get("retained_until"):
                self.store.update_metadata(run.id, {
                    "retained_until": (
                        datetime.now(timezone.utc) + timedelta(days=retention_days)
                    ).isoformat(),
                })
            elif not retention_days:
                cleanup = self._effect(
                    run, "git:remove_review_worktree",
                    lambda: self.worktrees.remove(project.repository, run.id),
                    reconcile=lambda _: (
                        {"path": run.worktree_path, "removed": True, "reconciled": True}
                        if self.worktrees.inspect(project.repository, run.id) is None
                        else None
                    ),
                    intent={"path": run.worktree_path},
                )
                self.store.update_metadata(run.id, {"worktree_cleanup": cleanup})
            self.store.transition(run.id, "completed")
            return
        workspace = self._workspace(run, project)
        message = f"feat: {run.metadata['title']}"
        inspect_head = getattr(self.git, "inspect_head", None)
        pending_commit = self.store.effect(run.id, "git:commit")
        previous_head = (
            pending_commit["payload"].get("previous_head")
            if pending_commit and pending_commit["status"] == "started"
            else inspect_head(workspace) if callable(inspect_head) else None
        )
        commit = self._effect(
            run, "git:commit",
            lambda: self.git.commit(workspace, message),
            reconcile=self._git_reconciler(
                "reconcile_commit", workspace, message, previous_head,
            ),
            intent={"message": message, "previous_head": previous_head},
        )
        self._effect(
            run, "git:push",
            lambda: self.git.publish_branch(workspace, run.metadata["branch"]),
            reconcile=self._git_reconciler(
                "reconcile_published_branch", workspace, run.metadata["branch"],
            ),
            intent={"branch": run.metadata["branch"], "commit": commit.get("commit")},
        )
        body = self._pr_body(run, commit)
        pull_request = self._effect(
            run, "github:pull_request",
            lambda: self.git.open_pull_request(
                workspace, run.metadata["branch"], run.metadata["base_branch"],
                run.metadata["title"], body,
            ),
            reconcile=self._git_reconciler(
                "find_pull_request", workspace, run.metadata["branch"],
                run.metadata["base_branch"],
            ),
            intent={
                "head": run.metadata["branch"], "base": run.metadata["base_branch"],
            },
        )
        inspected = self.git.inspect_pull_request(workspace, pull_request["url"])
        self._validate_pull_request(
            inspected, run.metadata["branch"], run.metadata["base_branch"]
        )
        self._effect(
            run, "friday:attach_pr",
            lambda: self._tasks().attach_pull_request(
                int(run.metadata["task_id"]), int(project.board_id), pull_request["url"], project.pr_column
            ),
            reconcile=self._friday_reconciler(
                "reconcile_pull_request", run.task_ref, int(project.board_id),
                pull_request["url"], project.pr_column,
            ),
            intent={"url": pull_request["url"], "column": project.pr_column},
        )
        self.store.update_metadata(run.id, {
            "commit": commit, "pull_request": {**pull_request, **inspected},
        })
        self._sync_friday(run, project, "pull_request")
        self._sync_friday(run, project, "completed")
        retention_days = max(0, self.settings.completed_worktree_retention_days)
        if retention_days:
            retained_until = (
                datetime.now(timezone.utc) + timedelta(days=retention_days)
            ).isoformat()
            self.store.update_metadata(run.id, {
                "retained_until": retained_until,
                "worktree_cleanup": {
                    "path": str(workspace), "removed": False,
                    "retained_until": retained_until,
                },
            })
        else:
            cleanup = self._effect(
                run,
                "git:remove_worktree",
                lambda: self.worktrees.remove(
                    project.repository, run.id, run.metadata["branch"]
                ),
                reconcile=lambda _: (
                    {"path": str(workspace), "removed": True, "reconciled": True}
                    if self.worktrees.inspect(
                        project.repository, run.id, run.metadata["branch"]
                    ) is None
                    else None
                ),
                intent={"path": str(workspace), "branch": run.metadata["branch"]},
            )
            self.store.update_metadata(run.id, {"worktree_cleanup": cleanup})
        self.store.transition(run.id, "completed")

    def _routed(
        self, run: Run, project: ProjectConfig, phase: str, prompt: str, read_only: bool
    ) -> ExecutionResult:
        primary = self.hosts.detect(run.host)
        adapters: list[HostAdapter] = [primary]
        if self.settings.cross_provider:
            adapters.extend(self.hosts.alternatives(run.host))
        last_error = "phase did not execute"
        attempts = max(1, self.settings.max_phase_attempts)
        risk_text = f"{run.metadata.get('title', '')}\n{run.metadata.get('description', '')}"
        risk = "high" if HIGH_RISK.search(risk_text) else "normal"
        complexity = classify_complexity(risk_text)
        for attempt in range(1, attempts + 1):
            adapter = adapters[min(attempt - 1, len(adapters) - 1)]
            route = ModelRouter(adapter.name).route(phase, attempt, risk, complexity)
            started_payload = asdict(route)
            self.store.event(run.id, "route.started", phase, started_payload)
            if self.progress:
                self.progress("route.started", started_payload)
            probe = self._probe_model(
                adapter, route.model, self._workspace(run, project), run.id,
            )
            if (
                probe is not None
                and self.settings.strict_model_verification
                and probe["verification_status"] != "confirmed"
            ):
                payload = {
                    **asdict(route), "success": False, "accepted": False,
                    "observed_model": probe.get("observed_model"),
                    "model_verified": False,
                    "verification_status": probe["verification_status"],
                    "verification_evidence": probe["verification_evidence"],
                    "exit_code": probe["exit_code"],
                    "duration_seconds": probe["duration_seconds"],
                    "confidence": None, "evidence": probe["verification_evidence"],
                    "signal": {"success": False, "summary": "model probe rejected"},
                }
                self.store.event(run.id, "route.completed", phase, payload)
                if self.progress:
                    self.progress("route.completed", payload)
                last_error = (
                    f"model {route.model} probe was {probe['verification_status']}"
                )
                continue
            try:
                self.store.heartbeat(run.id)
                self._active_host = adapter
                result = adapter.execute_agent(
                    route, prompt, self._workspace(run, project), read_only
                )
            except Exception as exc:
                payload = {
                    **asdict(route), "success": False, "accepted": False,
                    "observed_model": None, "model_verified": False,
                    "verification_status": "unavailable",
                    "verification_evidence": {"exception": type(exc).__name__},
                    "exit_code": 1,
                    "duration_seconds": 0, "confidence": None,
                    "evidence": {"exception": type(exc).__name__}, "error": str(exc),
                }
                self.store.event(run.id, "route.completed", phase, payload)
                if self.progress:
                    self.progress("route.completed", payload)
                last_error = str(exc)
                continue
            finally:
                self._active_host = None
            self.store.heartbeat(run.id)
            signal = sunday_result(result.output)
            confidence = signal.get("confidence", result.confidence)
            verified = adapter.verify_model_used(route, result)
            model_ok = verified or not self.settings.strict_model_verification
            accepted = (
                result.success and signal.get("success", True) and model_ok
                and (confidence is None or float(confidence) >= self.settings.minimum_confidence)
            )
            payload = {
                **asdict(route), "success": result.success, "accepted": accepted,
                "observed_model": result.observed_model, "model_verified": verified,
                "verification_status": getattr(
                    result, "verification_status", "confirmed" if verified else "unavailable"
                ),
                "verification_evidence": getattr(
                    result, "verification_evidence", result.evidence or {}
                ),
                "exit_code": getattr(result, "exit_code", 0 if result.success else 1),
                "duration_seconds": result.duration_seconds, "confidence": confidence,
                "evidence": result.evidence or {}, "signal": signal,
            }
            self.store.event(run.id, "route.completed", phase, payload)
            if self.progress:
                self.progress("route.completed", payload)
            if accepted:
                return result
            last_error = str(signal.get("summary") or result.output[-1000:])
        raise RuntimeError(f"{phase} failed after {attempts} attempts: {last_error}")

    def _probe_model(
        self, adapter: HostAdapter, model: str, repository: Path,
        run_id: str | None = None,
    ) -> dict | None:
        probe_model = getattr(adapter, "probe_model", None)
        if not callable(probe_model):
            return None
        key = (run_id or "diagnostic", adapter.name, model)
        if key in self._model_probes:
            return self._model_probes[key]
        try:
            if run_id:
                self.store.heartbeat(run_id)
            self._active_host = adapter
            result = probe_model(model, repository)
            probe = {
                "observed_model": result.observed_model,
                "verification_status": result.verification_status,
                "verification_evidence": result.verification_evidence,
                "exit_code": result.exit_code,
                "duration_seconds": result.duration_seconds,
            }
        except Exception as exc:
            probe = {
                "observed_model": None, "verification_status": "unavailable",
                "verification_evidence": {
                    "exception": type(exc).__name__, "error": str(exc),
                },
                "exit_code": 1, "duration_seconds": 0,
            }
        finally:
            self._active_host = None
        if run_id:
            self.store.heartbeat(run_id)
        self._model_probes[key] = probe
        return probe

    def _effect(
        self,
        run: Run,
        key: str,
        action: Callable[[], dict],
        reconcile: Callable[[dict], dict | None] | None = None,
        intent: dict | None = None,
    ) -> dict:
        self.store.heartbeat(run.id)
        existing = self.store.effect(run.id, key)
        if existing:
            if existing["status"] == "completed":
                return existing["payload"]
            retry_authorized = existing["status"] == "retry_authorized"
            if not reconcile and not retry_authorized:
                raise UncertainEffectError(f"External effect needs reconciliation: {key}")
            if reconcile:
                reconciled = reconcile(existing["payload"])
                if reconciled is not None:
                    self.store.heartbeat(run.id)
                    payload = reconciled if isinstance(reconciled, dict) else {"result": reconciled}
                    self.store.save_effect(run.id, key, "completed", payload)
                    self.store.event(
                        run.id, "effect.reconciled", run.state,
                        {"effect": key, "outcome": "applied", "result": payload},
                    )
                    completed = {
                        "effect": key, "result": payload, "execution": "deterministic",
                        "model": None, "reconciled": True,
                    }
                    self.store.event(run.id, "effect.completed", run.state, completed)
                    if self.progress:
                        self.progress("effect.completed", completed)
                    return payload
                self.store.event(
                    run.id, "effect.reconciled", run.state,
                    {"effect": key, "outcome": "absent"},
                )
            else:
                self.store.event(
                    run.id, "effect.reconciled", run.state,
                    {"effect": key, "outcome": "manual_absence_confirmation"},
                )
        else:
            self.store.save_effect(run.id, key, "started", intent or {})
        self.store.heartbeat(run.id)
        try:
            result = action()
        except Exception as exc:
            failure = dict(intent or (existing or {}).get("payload", {}))
            failure["last_error"] = str(exc)
            self.store.save_effect(run.id, key, "started", failure)
            raise
        payload = result if isinstance(result, dict) else {"result": result}
        self.store.heartbeat(run.id)
        self.store.save_effect(run.id, key, "completed", payload)
        event = {"effect": key, "result": payload, "execution": "deterministic", "model": None}
        self.store.event(run.id, "effect.completed", run.state, event)
        if self.progress:
            self.progress("effect.completed", event)
        return payload

    def _cancel_active_host(self) -> None:
        adapter = self._active_host
        if adapter is not None:
            adapter.cancel()

    def _sync_friday(self, run: Run, project: ProjectConfig, state: str) -> None:
        target = project.states.get(state)
        if target is None or target == "" or not run.metadata.get("task_id"):
            return
        if project.status_column:
            self._effect(
                run, f"friday:status:{state}",
                lambda: self._tasks().set_status(
                    int(run.metadata["task_id"]), int(project.board_id),
                    project.status_column, str(target),
                ),
                reconcile=self._friday_reconciler(
                    "reconcile_cell", run.task_ref, int(project.board_id),
                    project.status_column, str(target),
                ),
                intent={"column": project.status_column, "value": str(target)},
            )
            return
        self._effect(
            run, f"friday:transition:{state}",
            lambda: self._tasks().transition(int(run.metadata["task_id"]), int(target)),
            reconcile=self._friday_reconciler(
                "reconcile_transition", run.task_ref, int(project.board_id), int(target),
            ),
            intent={"group_id": int(target)},
        )

    def _sync_failed_safely(self, run: Run, project: ProjectConfig) -> None:
        try:
            self._sync_friday(run, project, "failed")
        except Exception as exc:
            self.store.event(
                run.id, "friday.failed_state_sync_failed", run.state, {"error": str(exc)}
            )

    def _base_branch(self, project: ProjectConfig, run: Run) -> str:
        if project.base_branch in {"main", "homolog"}:
            return project.base_branch
        repository = run.metadata["repository_state"]
        intent = f"{run.metadata['title']} {run.metadata['description']}".casefold()
        staging = any(word in intent for word in ("homolog", "staging", "pré-produção", "pre-production"))
        if staging and (repository["branches"].get("homolog") or repository["branches"].get("origin/homolog")):
            return "homolog"
        if repository["branches"].get("main") or repository["branches"].get("origin/main"):
            return "main"
        raise RuntimeError("Neither main nor homolog exists in the repository")

    @staticmethod
    def _workspace(run: Run, project: ProjectConfig) -> Path:
        return Path(run.worktree_path) if run.worktree_path else project.repository

    def _friday_reconciler(
        self, method_name: str, *args: object,
    ) -> Callable[[dict], dict | None] | None:
        method = getattr(self._tasks(), method_name, None)
        if not callable(method):
            return None
        return lambda _payload: method(*args)

    def _git_reconciler(
        self, method_name: str, *args: object,
    ) -> Callable[[dict], dict | None] | None:
        method = getattr(self.git, method_name, None)
        if not callable(method):
            return None
        return lambda _payload: method(*args)

    @staticmethod
    def _validate_pull_request(pull_request: dict, branch: str, base: str) -> None:
        head = pull_request.get("headRefName")
        target = pull_request.get("baseRefName")
        if head != branch or target != base:
            raise RuntimeError(
                f"Pull request branch mismatch: expected {branch} -> {base}, "
                f"got {head} -> {target}"
            )

    def _prompt(self, run: Run, phase: str, read_only: bool) -> str:
        common = f"""You are the Sunday {phase} specialist.
Run ID: {run.id}
Task: {run.metadata.get('title', run.task_ref)}
Description: {run.metadata.get('description', '')}
Repository: {run.worktree_path or run.metadata.get('repository')}
Read all applicable repository instruction files first.
Do not mutate Friday, Git remotes, pull requests, or external systems.
Mode: {'read-only' if read_only else 'workspace-write'}.
Immutable review target: {json.dumps(run.metadata.get('review_target', {}), ensure_ascii=False)}
Finish with exactly one line:
SUNDAY_RESULT: {{"success": true, "confidence": 0.0, "summary": "brief evidence"}}
Set success false when checks, requirements, or review fail.
"""
        if phase == "discovery":
            return common + """
Inspect architecture, repository rules, tests, risks, and branch policy.
Derive executable stories from the vague request.
Before SUNDAY_RESULT, emit one compact JSON line:
SUNDAY_STORIES: [{"title":"[type] outcome","description":"complete Friday story"}]
"""
        if phase == "implementation":
            return common + f"""
Implement the task and focused tests. Do not commit or push.
Stories: {json.dumps(run.metadata.get('stories', []), ensure_ascii=False)}
Discovery: {str(run.metadata.get('discovery', ''))[-6000:]}
"""
        if phase == "verification":
            return common + """
Inspect the complete diff. Run relevant tests, lint, and build.
Do not edit files. Fail when acceptance evidence is insufficient.
"""
        review_scope = (
            "Review the exact `commit` against the exact `baseCommit` from the "
            "immutable review target. Use those OIDs explicitly. Do not infer "
            "main, homolog, or a moving remote ref."
            if run.metadata.get("review_only")
            else "Review the worktree branch against its configured merge base."
        )
        return common + f"""
{review_scope}
Check correctness, security, regressions, compatibility, and tests.
Do not edit files. Fail on any unresolved P0, P1, or P2 finding.
"""

    def _pr_body(self, run: Run, commit: dict) -> str:
        events = self.store.events(run.id)
        routes = [event["payload"] for event in events if event["kind"] == "route.completed"]
        route_lines = "\n".join(
            f"- {route['phase']}: {route['requested_model'] if 'requested_model' in route else route['model']} -> "
            f"{route.get('observed_model') or 'not reported'}"
            for route in routes
        )
        return f"""## Outcome
{run.metadata['title']}

## Friday
- Item: {run.metadata['task_id']}
- Sunday run: `{run.id}`

## Validation
{str(run.metadata.get('verification', ''))[-3000:]}

## Review
{str(run.metadata.get('review', ''))[-3000:]}

## Model routes
{route_lines or '- No route evidence recorded'}

## Commit
`{commit.get('commit', 'none')}`
"""

    def _tasks(self) -> TaskManagerAdapter:
        if not self.tasks:
            from sunday.adapters.friday import FridayAdapter
            self.tasks = FridayAdapter()
        return self.tasks

    @staticmethod
    def _require_project(project: ProjectConfig) -> None:
        missing = [
            name for name, value in (
                ("workspace_id", project.workspace_id), ("board_id", project.board_id),
                ("intake_group_id", project.intake_group_id),
            ) if not value
        ]
        if missing:
            raise RuntimeError(f"Project lacks Friday configuration: {', '.join(missing)}")

    def review_only(self, reference: str, project: ProjectConfig, host_name: str = "auto") -> Run:
        host = self.hosts.detect(host_name if host_name != "auto" else self.settings.default_host)
        run = self.store.create(f"review:{reference}", project.name, host.name, {
            "repository": str(project.repository), "title": f"Review {reference}",
            "description": "Independent branch or pull request review",
            "review_reference": reference, "review_only": True,
        })
        return self.execute(run.id, project)

    def _phase_review_intake(self, run: Run, project: ProjectConfig) -> None:
        resolver = getattr(self.git, "resolve_review_reference", None)
        if not callable(resolver):
            raise RuntimeError("Git provider cannot resolve review references")
        pending = self.store.effect(run.id, "git:create_review_worktree")
        resolved = run.metadata.get("review_target_pending") or (
            pending["payload"].get("resolved")
            if pending and pending["status"] != "completed"
            else None
        )
        if resolved is not None and (
            not isinstance(resolved, dict)
            or not resolved.get("commit")
            or not resolved.get("baseCommit")
        ):
            raise RuntimeError("Persisted review target lacks immutable commit evidence")
        if resolved is None:
            base = project.base_branch if project.base_branch in {"main", "homolog"} else "main"
            resolved = resolver(
                project.repository, run.metadata["review_reference"], base
            )
            if not resolved.get("commit") or not resolved.get("baseCommit"):
                raise RuntimeError("Git provider omitted immutable review commits")
            run = self.store.update_metadata(
                run.id, {"review_target_pending": resolved}
            )

        def reconcile_review_worktree(_intent: dict) -> dict | None:
            inspected = self.worktrees.inspect(project.repository, run.id)
            if inspected and inspected.get("head") != resolved["commit"]:
                raise RuntimeError("Sunday review worktree changed revision")
            return inspected

        worktree = self._effect(
            run,
            "git:create_review_worktree",
            lambda: self.worktrees.create_detached(
                project.repository, run.id, resolved["commit"]
            ),
            reconcile=reconcile_review_worktree,
            intent={"revision": resolved["commit"], "resolved": resolved},
        )
        inspected = self.worktrees.inspect(project.repository, run.id)
        if not inspected or inspected.get("head") != resolved["commit"]:
            raise RuntimeError("Sunday review worktree changed revision")
        self.store.set_worktree(run.id, worktree["path"])
        self.store.update_metadata(run.id, {
            "review_target": resolved,
            "base_branch": resolved.get("baseRefName"),
            "branch": resolved.get("headRefName"),
        })
        self.store.transition(run.id, "discovery")
