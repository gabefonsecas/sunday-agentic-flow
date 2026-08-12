"""AI-assisted first-run project configuration from live Friday metadata."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from sunday.adapters.friday import FridayMCPClient
from sunday.adapters.hosts import HostRegistry
from sunday.config import ProjectConfig, Settings
from sunday.routing import ModelRouter

PHASES = (
    "discovery", "stories", "publication", "implementation", "verification",
    "review", "pull_request", "completed", "failed",
)


def needs_configuration(project: ProjectConfig) -> bool:
    return not all((project.workspace_id, project.board_id, project.intake_group_id))


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for nested in value.values() for text in _strings(nested)]
    if isinstance(value, list):
        return [text for nested in value for text in _strings(nested)]
    return []


def parse_config(output: str) -> dict:
    candidates = [output]
    for raw_line in output.splitlines():
        try:
            candidates.extend(_strings(json.loads(raw_line)))
        except json.JSONDecodeError:
            continue
    lines = [line for candidate in candidates for line in candidate.splitlines()]
    for line in reversed(lines):
        if not line.strip().startswith("SUNDAY_CONFIG:"):
            continue
        try:
            value = json.loads(line.split(":", 1)[1].strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError("Host returned malformed SUNDAY_CONFIG JSON") from exc
        if isinstance(value, dict):
            return value
    raise RuntimeError("Host did not return SUNDAY_CONFIG")


class AutoConfigurationService:
    def __init__(
        self,
        settings: Settings,
        client: FridayMCPClient | None = None,
        hosts: HostRegistry | None = None,
    ):
        self.settings = settings
        self.client = client or FridayMCPClient()
        self.hosts = hosts or HostRegistry()

    def configure(
        self,
        repository: Path,
        request: str,
        host_name: str,
        destination: Path,
    ) -> ProjectConfig:
        catalog = self._catalog()
        host = self.hosts.detect(
            self.settings.default_host if host_name == "auto" else host_name
        )
        prompt = self._prompt(repository, request, catalog)
        last_error = "configuration discovery did not execute"
        for attempt in range(1, max(1, self.settings.max_phase_attempts) + 1):
            route = ModelRouter(host.name).route("discovery", attempt)
            result = host.execute_agent(route, prompt, repository, True)
            verified = host.verify_model_used(route, result)
            confidence_ok = (
                result.confidence is None
                or result.confidence >= self.settings.minimum_confidence
            )
            if (
                not result.success or not confidence_ok
                or (self.settings.strict_model_verification and not verified)
            ):
                last_error = result.output[-1000:]
                continue
            try:
                selected = parse_config(result.output)
                project = self._validate(selected, catalog, repository)
            except (KeyError, TypeError, ValueError, RuntimeError) as exc:
                last_error = str(exc)
                continue
            self._save(project, destination)
            return project
        raise RuntimeError(f"Sunday could not configure Friday automatically: {last_error}")

    def _catalog(self) -> dict:
        workspaces = self.client.tool("list_workspaces", {})
        catalog = {"workspaces": []}
        for workspace in workspaces:
            boards = []
            for board in self.client.tool("list_boards", {"workspace_id": workspace["id"]}):
                boards.append({
                    **board,
                    "groups": self.client.tool("list_groups", {"board_id": board["id"]}),
                    "columns": self.client.tool("list_columns", {"board_id": board["id"]}),
                })
            catalog["workspaces"].append({**workspace, "boards": boards})
        if not any(workspace["boards"] for workspace in catalog["workspaces"]):
            raise RuntimeError("Friday token can access no boards")
        return catalog

    @staticmethod
    def _prompt(repository: Path, request: str, catalog: dict) -> str:
        return f"""You are Sunday first-run configuration analyst. Work read-only.
Read repository instructions and inspect enough context to identify what this project builds.
Choose the best Friday workspace and software-development board for the request. Prefer a board
with a people column and a rich status workflow. Choose an intake group appropriate for development.
Map every Sunday phase to an existing status option ID. Never invent an ID. If the board genuinely
uses groups as workflow states, leave status_column empty and map phases to group IDs instead.
Choose a checkbox column used to identify work performed with AI when one exists.

Repository: {repository}
Request: {request}
Live Friday catalog: {json.dumps(catalog, ensure_ascii=False)}

Return exactly one single-line marker with valid JSON and no markdown fences:
SUNDAY_CONFIG: {{"workspace_id":1,"board_id":2,"intake_group_id":3,
"people_column":"column-id","status_column":"status-column-id","pr_column":"",
"ai_column":"ai-checkbox-column-id",
"states":{{"discovery":"option-id","stories":"option-id","publication":"option-id",
"implementation":"option-id","verification":"option-id","review":"option-id",
"pull_request":"option-id","completed":"option-id","failed":"option-id"}}}}
"""

    @staticmethod
    def _validate(selected: dict, catalog: dict, repository: Path) -> ProjectConfig:
        workspace_id = int(selected["workspace_id"])
        board_id = int(selected["board_id"])
        group_id = int(selected["intake_group_id"])
        workspace = next(
            (item for item in catalog["workspaces"] if int(item["id"]) == workspace_id), None
        )
        if not workspace:
            raise ValueError("AI selected an inaccessible Friday workspace")
        board = next((item for item in workspace["boards"] if int(item["id"]) == board_id), None)
        if not board:
            raise ValueError("AI selected a board outside the selected workspace")
        if group_id not in {int(item["id"]) for item in board["groups"]}:
            raise ValueError("AI selected an intake group outside the selected board")

        columns = board["columns"]
        people_column = str(selected.get("people_column", ""))
        if not any(
            item.get("type") == "people" and str(item.get("id")) == people_column
            for item in columns
        ):
            raise ValueError("AI selected an invalid people column")

        status_column = str(selected.get("status_column", ""))
        states = selected.get("states") or {}
        if set(states) != set(PHASES):
            raise ValueError("AI must map every Sunday phase")
        if status_column:
            column = next((
                item for item in columns
                if item.get("type") == "status" and str(item.get("id")) == status_column
            ), None)
            if not column:
                raise ValueError("AI selected an invalid status column")
            option_ids = {
                str(option["id"])
                for option in (column.get("settings") or {}).get("options", [])
            }
            invalid = {str(value) for value in states.values()} - option_ids
            if invalid:
                raise ValueError(f"AI invented Friday status options: {sorted(invalid)}")
            normalized_states: dict[str, int | str] = {
                str(key): str(value) for key, value in states.items()
            }
        else:
            group_ids = {int(item["id"]) for item in board["groups"]}
            normalized_states = {str(key): int(value) for key, value in states.items()}
            if set(normalized_states.values()) - group_ids:
                raise ValueError("AI invented Friday group IDs")

        pr_column = str(selected.get("pr_column", ""))
        if pr_column and not any(
            str(item.get("id")) == pr_column and item.get("type") in {"link", "url"}
            for item in columns
        ):
            raise ValueError("AI selected an invalid pull-request column")
        ai_column = str(selected.get("ai_column", ""))
        if ai_column and not any(
            str(item.get("id")) == ai_column and item.get("type") == "checkbox"
            for item in columns
        ):
            raise ValueError("AI selected an invalid AI checkbox column")
        return ProjectConfig(
            name=repository.name, repository=repository,
            workspace_id=workspace_id, board_id=board_id, intake_group_id=group_id,
            states=normalized_states, base_branch="auto", pr_column=pr_column,
            people_column=people_column, status_column=status_column,
            ai_column=ai_column,
            publish_stories=False,
        )

    def _save(self, project: ProjectConfig, destination: Path) -> None:
        projects = {
            name: value for name, value in self.settings.projects.items()
            if all((value.workspace_id, value.board_id, value.intake_group_id))
        }
        projects[project.name] = project
        self.settings.projects = projects
        self.settings.default_project = project.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=destination.parent,
                prefix=".sunday-config-", delete=False,
            ) as stream:
                stream.write(_toml(self.settings))
                temporary = Path(stream.name)
            if os.name != "nt":
                temporary.chmod(0o600)
            os.replace(temporary, destination)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        if os.name != "nt" and destination.stat().st_mode & 0o077:
            try:
                destination.chmod(0o600)
            except OSError:
                pass


def _quoted(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _toml(settings: Settings) -> str:
    lines = [
        "# Generated by Sunday first-run AI configuration. Secrets belong in .env.",
        "[runtime]",
        f"default_host = {_quoted(settings.default_host)}",
        f"default_project = {_quoted(settings.default_project or '')}",
        f"cross_provider = {_quoted(settings.cross_provider)}",
        f"strict_model_verification = {_quoted(settings.strict_model_verification)}",
        f"watcher_interval = {settings.watcher_interval}",
        f"minimum_confidence = {settings.minimum_confidence}",
        f"max_phase_attempts = {settings.max_phase_attempts}",
    ]
    for name, project in sorted(settings.projects.items()):
        lines.extend([
            "", f"[projects.{_quoted(name)}]",
            f"repository = {_quoted(project.repository)}",
            f"workspace_id = {project.workspace_id}",
            f"board_id = {project.board_id}",
            f"intake_group_id = {project.intake_group_id}",
            f"ready_label = {_quoted(project.ready_label)}",
            f"ai_column = {_quoted(project.ai_column)}",
            f"base_branch = {_quoted(project.base_branch)}",
            f"pr_column = {_quoted(project.pr_column)}",
            f"people_column = {_quoted(project.people_column)}",
            f"status_column = {_quoted(project.status_column)}",
            f"publish_stories = {_quoted(project.publish_stories)}",
            "", f"[projects.{_quoted(name)}.states]",
        ])
        lines.extend(f"{key} = {_quoted(value)}" for key, value in project.states.items())
    return "\n".join(lines) + "\n"
