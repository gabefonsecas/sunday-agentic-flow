"""Stable integration contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sunday.routing import Route


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    output: str
    requested_model: str
    observed_model: str | None
    model_verified: bool
    duration_seconds: float
    confidence: float | None = None
    evidence: dict[str, Any] | None = None


class HostAdapter(ABC):
    @abstractmethod
    def capabilities(self) -> dict: ...

    @abstractmethod
    def execute_agent(self, route: Route, prompt: str, repository: Path, read_only: bool) -> ExecutionResult: ...

    @abstractmethod
    def verify_model_used(self, route: Route, result: ExecutionResult) -> bool: ...

    @abstractmethod
    def cancel(self) -> None: ...


class TaskManagerAdapter(ABC):
    @abstractmethod
    def authenticate(self) -> dict: ...

    @abstractmethod
    def get_current_user(self, workspace_id: int) -> dict: ...

    @abstractmethod
    def get_task(self, task_ref: str, board_id: int | None = None) -> dict: ...

    @abstractmethod
    def list_ready_tasks(self, label: str) -> list[dict]: ...

    @abstractmethod
    def claim_task(self, task: dict, workspace_id: int, board_id: int, people_column: str = "") -> dict: ...

    @abstractmethod
    def create_story(self, story: dict, board_id: int, group_id: int) -> dict: ...

    @abstractmethod
    def find_story(self, marker: str, group_id: int) -> dict | None: ...

    @abstractmethod
    def transition(self, item_id: int, group_id: int) -> dict: ...

    @abstractmethod
    def comment(self, item_id: int, text: str) -> dict: ...

    @abstractmethod
    def attach_pull_request(self, item_id: int, board_id: int, url: str, column: str = "") -> dict: ...


class GitProviderAdapter(ABC):
    @abstractmethod
    def inspect_repository(self, repository: Path) -> dict: ...

    @abstractmethod
    def create_branch(self, repository: Path, branch: str, base: str) -> dict: ...

    @abstractmethod
    def publish_branch(self, repository: Path, branch: str) -> dict: ...

    @abstractmethod
    def open_pull_request(self, repository: Path, branch: str, base: str, title: str, body: str) -> dict: ...

    @abstractmethod
    def inspect_pull_request(self, repository: Path, reference: str) -> dict: ...
