"""Deterministic Sunday workflow engine."""

from dataclasses import asdict
import json
import re
from typing import Callable

from sunday.adapters.base import ExecutionResult, GitProviderAdapter, HostAdapter, TaskManagerAdapter
from sunday.adapters.github import GitHubAdapter, branch_slug
from sunday.adapters.hosts import HostRegistry
from sunday.config import ProjectConfig, Settings
from sunday.routing import ModelRouter
from sunday.state import Run, RunStore

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


def sunday_result(output: str) -> dict:
    matches = re.findall(r"SUNDAY_RESULT\s*:\s*(\{.*\})", output)
    if not matches:
        return {"success": True, "confidence": None, "summary": output[-4000:]}
    try:
        value = json.loads(matches[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Host returned malformed SUNDAY_RESULT JSON") from exc
    return value


def sunday_stories(output: str, task: dict) -> list[dict]:
    matches = re.findall(r"SUNDAY_STORIES\s*:\s*(\[.*\])", output)
    if matches:
        try:
            stories = json.loads(matches[-1])
            if isinstance(stories, list) and stories:
                return stories
        except json.JSONDecodeError:
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
    ):
        self.settings = settings
        self.store = store or RunStore()
        self.tasks = tasks
        self.git = git or GitHubAdapter()
        self.hosts = hosts or HostRegistry()

    def start(self, task_ref: str, project: ProjectConfig, host_name: str = "auto") -> Run:
        previous = self.store.latest_for_task(task_ref)
        if previous and previous.state == "completed":
            raise RuntimeError(
                f"Task already completed by Sunday run {previous.id}. "
                "Create a new Friday item for additional work."
            )
        host = self.hosts.detect(host_name if host_name != "auto" else self.settings.default_host)
        run = self.store.create(task_ref, project.name, host.name, {"repository": str(project.repository)})
        return self.execute(run.id, project)

    def resume(self, run_id: str, project: ProjectConfig, approved: bool = False) -> Run:
        run = self.store.get(run_id)
        if approved:
            self.store.update_metadata(run_id, {"high_risk_approved": True})
        if run.state == "paused":
            if not run.resume_state:
                raise RuntimeError("Paused run has no resumable state")
            self.store.transition(run_id, run.resume_state, {"approved": approved})
        return self.execute(run_id, project)

    def execute(self, run_id: str, project: ProjectConfig) -> Run:
        try:
            while True:
                run = self.store.get(run_id)
                if run.state in {"completed", "failed", "paused"}:
                    return run
                handler = getattr(self, f"_phase_{run.state}")
                handler(run, project)
        except UncertainEffectError as exc:
            run = self.store.get(run_id)
            self.store.event(run_id, "effect.uncertain", run.state, {"error": str(exc)})
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
            return self.store.transition(run_id, "paused", {"reason": str(exc)})

    def _phase_intake(self, run: Run, project: ProjectConfig) -> None:
        self._require_project(project)
        task = self._tasks().get_task(run.task_ref, project.board_id)
        task_id = int(task["id"])
        repository = self.git.inspect_repository(project.repository)
        if repository["dirty"]:
            raise RuntimeError("Repository has uncommitted changes before Sunday execution")
        claim = self._effect(
            run, "friday:claim",
            lambda: self._tasks().claim_task(
                task, int(project.workspace_id), int(project.board_id), project.people_column
            ),
        )
        self.store.update_metadata(run.id, {
            "task": task, "task_id": task_id, "title": task_title(task),
            "description": task_description(task), "claim": claim, "repository_state": repository,
        })
        self._sync_friday(run, project, "discovery")
        self.store.transition(run.id, "discovery")

    def _phase_discovery(self, run: Run, project: ProjectConfig) -> None:
        prompt = self._prompt(run, "discovery", read_only=True)
        result = self._routed(run, project, "discovery", prompt, read_only=True)
        self.store.update_metadata(run.id, {"discovery": result.output})
        self._sync_friday(run, project, "stories")
        self.store.transition(run.id, "stories")

    def _phase_stories(self, run: Run, project: ProjectConfig) -> None:
        stories = sunday_stories(run.metadata.get("discovery", ""), run.metadata["task"])
        self.store.update_metadata(run.id, {"stories": stories})
        self._sync_friday(run, project, "publication")
        self.store.transition(run.id, "publication")

    def _phase_publication(self, run: Run, project: ProjectConfig) -> None:
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
                ))
        base = self._base_branch(project, run)
        branch = branch_slug(run.task_ref, run.metadata["title"])
        branch_result = self._effect(
            run, "git:create_branch",
            lambda: self.git.create_branch(project.repository, branch, base),
        )
        self.store.update_metadata(run.id, {
            "published_stories": published, "base_branch": base,
            "branch": branch, "branch_result": branch_result,
        })
        risk_text = f"{run.metadata['title']}\n{run.metadata['description']}"
        if HIGH_RISK.search(risk_text) and not run.metadata.get("high_risk_approved"):
            self.store.transition(run.id, "paused", {"reason": "High-risk action requires approval"})
            return
        self._sync_friday(run, project, "implementation")
        self.store.transition(run.id, "implementation")

    def _phase_implementation(self, run: Run, project: ProjectConfig) -> None:
        prompt = self._prompt(run, "implementation", read_only=False)
        result = self._routed(run, project, "implementation", prompt, read_only=False)
        self.store.update_metadata(run.id, {"implementation": result.output})
        self._sync_friday(run, project, "verification")
        self.store.transition(run.id, "verification")

    def _phase_verification(self, run: Run, project: ProjectConfig) -> None:
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
        commit = self._effect(
            run, "git:commit",
            lambda: self.git.commit(project.repository, f"feat: {run.metadata['title']}"),
        )
        self._effect(
            run, "git:push",
            lambda: self.git.publish_branch(project.repository, run.metadata["branch"]),
        )
        body = self._pr_body(run, commit)
        pull_request = self._effect(
            run, "github:pull_request",
            lambda: self.git.open_pull_request(
                project.repository, run.metadata["branch"], run.metadata["base_branch"],
                run.metadata["title"], body,
            ),
        )
        self._effect(
            run, "friday:attach_pr",
            lambda: self._tasks().attach_pull_request(
                int(run.metadata["task_id"]), int(project.board_id), pull_request["url"], project.pr_column
            ),
        )
        self.store.update_metadata(run.id, {"commit": commit, "pull_request": pull_request})
        self._sync_friday(run, project, "pull_request")
        self._sync_friday(run, project, "completed")
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
        for attempt in range(1, attempts + 1):
            adapter = adapters[min(attempt - 1, len(adapters) - 1)]
            route = ModelRouter(adapter.name).route(phase, attempt)
            self.store.event(run.id, "route.started", phase, asdict(route))
            result = adapter.execute_agent(route, prompt, project.repository, read_only)
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
                "duration_seconds": result.duration_seconds, "confidence": confidence,
                "evidence": result.evidence or {}, "signal": signal,
            }
            self.store.event(run.id, "route.completed", phase, payload)
            if accepted:
                return result
            last_error = str(signal.get("summary") or result.output[-1000:])
        raise RuntimeError(f"{phase} failed after {attempts} attempts: {last_error}")

    def _effect(self, run: Run, key: str, action: Callable[[], dict]) -> dict:
        existing = self.store.effect(run.id, key)
        if existing:
            if existing["status"] == "completed":
                return existing["payload"]
            raise UncertainEffectError(f"External effect needs reconciliation: {key}")
        self.store.save_effect(run.id, key, "started", {})
        result = action()
        payload = result if isinstance(result, dict) else {"result": result}
        self.store.save_effect(run.id, key, "completed", payload)
        self.store.event(run.id, "effect.completed", run.state, {"key": key, "result": payload})
        return payload

    def _sync_friday(self, run: Run, project: ProjectConfig, state: str) -> None:
        group_id = project.states.get(state)
        if not group_id or not run.metadata.get("task_id"):
            return
        self._effect(
            run, f"friday:transition:{state}",
            lambda: self._tasks().transition(int(run.metadata["task_id"]), group_id),
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

    def _prompt(self, run: Run, phase: str, read_only: bool) -> str:
        common = f"""You are the Sunday {phase} specialist.
Run ID: {run.id}
Task: {run.metadata.get('title', run.task_ref)}
Description: {run.metadata.get('description', '')}
Repository: {run.metadata.get('repository')}
Read all applicable repository instruction files first.
Do not mutate Friday, Git remotes, pull requests, or external systems.
Mode: {'read-only' if read_only else 'workspace-write'}.
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
        return common + """
Review the branch against its merge base.
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
            "description": "Independent branch or pull request review", "review_reference": reference,
        })
        self.store.transition(run.id, "discovery")
        self.store.transition(run.id, "stories")
        self.store.transition(run.id, "publication")
        self.store.transition(run.id, "implementation")
        self.store.transition(run.id, "verification")
        self.store.transition(run.id, "review")
        result = self._routed(self.store.get(run.id), project, "review", self._prompt(self.store.get(run.id), "review", True), True)
        self.store.update_metadata(run.id, {"review": result.output})
        self.store.transition(run.id, "pull_request")
        return self.store.transition(run.id, "completed")
