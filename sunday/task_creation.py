"""Agentic creation of Friday tasks from natural-language requests."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from uuid import uuid4

from sunday.adapters.base import TaskManagerAdapter
from sunday.adapters.friday import FridayAdapter
from sunday.adapters.hosts import HostRegistry
from sunday.config import ProjectConfig, Settings
from sunday.routing import ModelRouter
from sunday.state import RunStore


def _fallback_tasks(request: str, project: ProjectConfig, count: int) -> list[dict]:
    title = " ".join(request.strip().split())
    if len(title) > 100:
        title = title[:97].rstrip() + "..."
    return [
        {
            "title": title if count == 1 else f"{title} ({index + 1}/{count})",
            "description": (
                f"## Contexto\nSolicitação recebida para o projeto `{project.name}` em "
                f"`{project.repository}`.\n\n## Objetivo\n{request.strip()}\n\n"
                "## Critérios de aceite\n- [ ] O comportamento solicitado está implementado.\n"
                "- [ ] As regras do repositório foram respeitadas.\n"
                "- [ ] Os testes e verificações relevantes passam.\n\n"
                "## Validação\nAnexar evidências de testes e da pull request."
            ),
        }
        for index in range(count)
    ]


def parse_tasks(output: str, request: str, project: ProjectConfig, count: int) -> list[dict]:
    candidates = [output]
    for raw_line in output.splitlines():
        try:
            candidates.extend(_strings(json.loads(raw_line)))
        except json.JSONDecodeError:
            continue
    lines = [line for candidate in candidates for line in candidate.splitlines()]
    for line in reversed(lines):
        if not line.strip().startswith("SUNDAY_TASKS:"):
            continue
        try:
            value = json.loads(line.split(":", 1)[1].strip())
        except json.JSONDecodeError:
            break
        if isinstance(value, list) and len(value) == count and all(
            isinstance(item, dict) and item.get("title") and item.get("description") for item in value
        ):
            return [{"title": str(item["title"]), "description": str(item["description"])} for item in value]
    return _fallback_tasks(request, project, count)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for nested in value.values() for text in _strings(nested)]
    if isinstance(value, list):
        return [text for nested in value for text in _strings(nested)]
    return []


def _item_id(value: object) -> int:
    if isinstance(value, dict):
        for key in ("id", "item_id"):
            if key in value:
                return int(value[key])
        for nested in value.values():
            try:
                return _item_id(nested)
            except (TypeError, ValueError):
                continue
    raise ValueError("Friday create_item response did not contain an item ID")


class TaskCreationService:
    def __init__(
        self,
        settings: Settings,
        store: RunStore | None = None,
        tasks: TaskManagerAdapter | None = None,
        hosts: HostRegistry | None = None,
    ):
        self.settings = settings
        self.store = store or RunStore()
        self.tasks = tasks or FridayAdapter()
        self.hosts = hosts or HostRegistry()

    def create(
        self,
        request: str,
        project: ProjectConfig,
        host_name: str = "auto",
        count: int = 1,
        assign: bool = True,
        allow_duplicate: bool = False,
    ) -> dict:
        request = request.strip()
        if not request:
            raise ValueError("Task request cannot be empty")
        if count < 1 or count > 20:
            raise ValueError("Task count must be between 1 and 20")
        self._require_friday(project, assign)
        identity = {
            "project": project.name,
            "repository": str(project.repository),
            "request": request.casefold(),
            "count": count,
            "board_id": project.board_id,
            "group_id": project.intake_group_id,
            "assign": assign,
        }
        if allow_duplicate:
            identity["nonce"] = str(uuid4())
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        operation, created = self.store.create_operation("friday.task.create", key, identity)
        if not created:
            if operation.status == "completed":
                return {**operation.payload, "deduplicated": True}

        published: list[dict] = []
        try:
            host = self.hosts.detect(
                self.settings.default_host if host_name == "auto" else host_name
            )
            result, route = self._discover(host, request, project, count)
            stories = parse_tasks(result.output, request, project, count)
            for index, story in enumerate(stories):
                marker = f"Sunday-Key: {operation.id}:task:{index}"
                materialized = {
                    **story,
                    "description": story["description"] + f"\n\n{marker}",
                }
                created_item = self.tasks.find_story(marker, int(project.intake_group_id))
                if created_item is None:
                    created_item = self.tasks.create_story(
                        materialized, int(project.board_id), int(project.intake_group_id)
                    )
                item_id = _item_id(created_item)
                entry = {
                    "id": item_id, "title": materialized["title"],
                    "result": created_item, "assignment": None,
                }
                published.append(entry)
                self.store.update_operation(operation.id, "started", {
                    **identity, "operation_id": operation.id, "published": published,
                })
                assignment = None
                if assign:
                    assignment = self.tasks.claim_task(
                        {**materialized, **created_item, "id": item_id},
                        int(project.workspace_id), int(project.board_id), project.people_column,
                    )
                entry["assignment"] = assignment
                if project.ai_column:
                    entry["ai_mark"] = self.tasks.mark_ai(
                        item_id, int(project.board_id), project.ai_column
                    )
                self.store.update_operation(operation.id, "started", {
                    **identity, "operation_id": operation.id, "published": published,
                })
            payload = {
                "operation_id": operation.id,
                "status": "completed",
                "project": project.name,
                "repository": str(project.repository),
                "tasks": published,
                "route": {
                    **asdict(route), "observed_model": result.observed_model,
                    "model_verified": result.model_verified,
                    "duration_seconds": result.duration_seconds,
                    "confidence": result.confidence,
                    "evidence": result.evidence or {},
                },
                "deduplicated": False,
            }
            self.store.update_operation(operation.id, "completed", payload)
            return payload
        except Exception as exc:
            status = "paused" if published else "failed"
            self.store.update_operation(operation.id, status, {
                **identity, "operation_id": operation.id, "published": published, "error": str(exc),
            })
            raise

    def _discover(self, host, request: str, project: ProjectConfig, count: int):
        prompt = f"""You are Sunday task analyst. Work read-only in this repository.
Read AGENTS.md and equivalent repository instructions. Inspect only enough project context to turn
the request into exactly {count} executable Friday task(s). Preserve the user's intent. Add concrete
context, acceptance criteria, exclusions, dependencies, risks, and validation. Do not implement.

Repository: {project.repository}
Project: {project.name}
Original request: {request}

Your final output must contain one single-line marker with valid JSON and no markdown fences:
SUNDAY_TASKS: [{{"title":"concise observable outcome","description":"complete Markdown story"}}]
"""
        last_error = "task analysis did not execute"
        for attempt in range(1, max(1, self.settings.max_phase_attempts) + 1):
            route = ModelRouter(host.name).route("discovery", attempt)
            result = host.execute_agent(route, prompt, project.repository, True)
            verified = host.verify_model_used(route, result)
            confidence_ok = result.confidence is None or result.confidence >= self.settings.minimum_confidence
            if result.success and confidence_ok and (verified or not self.settings.strict_model_verification):
                return result, route
            last_error = result.output[-1000:]
        raise RuntimeError(f"Task analysis failed: {last_error}")

    @staticmethod
    def _require_friday(project: ProjectConfig, assign: bool) -> None:
        missing = []
        for key in ("board_id", "intake_group_id"):
            if not getattr(project, key):
                missing.append(key)
        if assign and not project.workspace_id:
            missing.append("workspace_id")
        if missing:
            raise RuntimeError(
                "Configure Friday mapping for the current repository: " + ", ".join(missing)
            )
