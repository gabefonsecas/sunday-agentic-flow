"""Sunday configuration from TOML and environment variables."""

from dataclasses import dataclass, field, replace
import os
from pathlib import Path

import tomllib

from .paths import config_dir
from .security import load_env


@dataclass(slots=True)
class ProjectConfig:
    name: str
    repository: Path
    workspace_id: int | None = None
    board_id: int | None = None
    intake_group_id: int | None = None
    states: dict[str, int | str] = field(default_factory=dict)
    ready_label: str = ""
    ai_column: str = ""
    base_branch: str = "auto"
    pr_column: str = ""
    people_column: str = ""
    status_column: str = ""
    publish_stories: bool = False


@dataclass(slots=True)
class Settings:
    default_host: str = "auto"
    default_project: str | None = None
    cross_provider: bool = False
    strict_model_verification: bool = True
    watcher_interval: int = 60
    minimum_confidence: float = 0.7
    max_phase_attempts: int = 3
    lease_ttl_seconds: int = 300
    lease_heartbeat_seconds: int = 60
    completed_worktree_retention_days: int = 0
    projects: dict[str, ProjectConfig] = field(default_factory=dict)

    def project_for(self, name: str | None, cwd: Path | None = None) -> ProjectConfig:
        if name:
            if name not in self.projects:
                raise KeyError(f"Unknown project: {name}")
            return self.projects[name]
        resolved = _repository_root((cwd or Path.cwd()).resolve())
        matches = [
            project
            for project in self.projects.values()
            if resolved == project.repository or project.repository in resolved.parents
        ]
        if len(matches) == 1:
            return matches[0]
        if self.default_project:
            if self.default_project not in self.projects:
                raise KeyError(f"Unknown default project: {self.default_project}")
            template = self.projects[self.default_project]
            return replace(template, name=resolved.name, repository=resolved)
        if len(self.projects) == 1:
            template = next(iter(self.projects.values()))
            return replace(template, name=resolved.name, repository=resolved)
        if not self.projects:
            return ProjectConfig(name=resolved.name, repository=resolved)
        raise RuntimeError("Select a configured project with --project")


def _repository_root(path: Path) -> Path:
    current = path if path.is_dir() else path.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def config_path() -> Path:
    return Path(os.environ.get("SUNDAY_CONFIG_FILE", config_dir() / "config.toml")).expanduser()


def _project(name: str, data: dict) -> ProjectConfig:
    return ProjectConfig(
        name=name,
        repository=Path(data.get("repository", ".")).expanduser().resolve(),
        workspace_id=data.get("workspace_id"),
        board_id=data.get("board_id"),
        intake_group_id=data.get("intake_group_id"),
        states={str(key): value for key, value in data.get("states", {}).items()},
        ready_label=data.get("ready_label", ""),
        ai_column=data.get("ai_column", ""),
        base_branch=data.get("base_branch", "auto"),
        pr_column=data.get("pr_column", ""),
        people_column=data.get("people_column", ""),
        status_column=data.get("status_column", ""),
        publish_stories=bool(data.get("publish_stories", False)),
    )


def load_settings(path: Path | None = None) -> Settings:
    load_env()
    selected = path or config_path()
    if not selected.is_file():
        return Settings()
    data = tomllib.loads(selected.read_text(encoding="utf-8"))
    runtime = data.get("runtime", {})
    projects = {
        name: _project(name, project)
        for name, project in data.get("projects", {}).items()
    }
    return Settings(
        default_host=runtime.get("default_host", "auto"),
        default_project=runtime.get("default_project"),
        cross_provider=bool(runtime.get("cross_provider", False)),
        strict_model_verification=bool(runtime.get("strict_model_verification", True)),
        watcher_interval=int(runtime.get("watcher_interval", 60)),
        minimum_confidence=float(runtime.get("minimum_confidence", 0.7)),
        max_phase_attempts=int(runtime.get("max_phase_attempts", 3)),
        lease_ttl_seconds=max(30, int(runtime.get("lease_ttl_seconds", 300))),
        lease_heartbeat_seconds=max(10, int(runtime.get("lease_heartbeat_seconds", 60))),
        completed_worktree_retention_days=max(
            0, int(runtime.get("completed_worktree_retention_days", 0))
        ),
        projects=projects,
    )


DEFAULT_CONFIG = '''# Sunday configuration. Secrets belong in .env.
[runtime]
default_host = "auto"
default_project = "example"
cross_provider = false
strict_model_verification = true
watcher_interval = 60
minimum_confidence = 0.70
max_phase_attempts = 3
lease_ttl_seconds = 300
lease_heartbeat_seconds = 60
completed_worktree_retention_days = 0

[projects.example]
repository = "~/src/example"
workspace_id = 0
board_id = 0
intake_group_id = 0
ready_label = ""
ai_column = ""
base_branch = "auto"
pr_column = "Pull Request"
people_column = "Responsável"
status_column = ""
publish_stories = false
'''
