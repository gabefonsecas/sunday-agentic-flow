"""Stable integration contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sunday.routing import Route


VerificationStatus = Literal["confirmed", "requested_only", "mismatched", "unavailable"]


@dataclass(slots=True)
class ModelExecution:
    requested_model: str
    observed_model: str | None
    verification_status: VerificationStatus
    verification_evidence: dict[str, Any]
    exit_code: int
    duration: float
    output: str
    confidence: float | None = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def model_verified(self) -> bool:
        return self.verification_status == "confirmed"

    @property
    def duration_seconds(self) -> float:
        return self.duration

    @property
    def evidence(self) -> dict[str, Any]:
        return self.verification_evidence

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_model": self.requested_model,
            "observed_model": self.observed_model,
            "verification_status": self.verification_status,
            "verification_evidence": self.verification_evidence,
            "exit_code": self.exit_code,
            "duration": self.duration,
            "output": self.output,
        }


class ExecutionResult(ModelExecution):
    """Compatibility wrapper for integrations using the original contract."""

    __slots__ = ()

    def __init__(
        self,
        success: bool,
        output: str,
        requested_model: str,
        observed_model: str | None,
        model_verified: bool,
        duration_seconds: float,
        confidence: float | None = None,
        evidence: dict[str, Any] | None = None,
    ):
        if model_verified:
            status: VerificationStatus = "confirmed"
        elif observed_model:
            status = "mismatched"
        elif success:
            status = "requested_only"
        else:
            status = "unavailable"
        super().__init__(
            requested_model=requested_model,
            observed_model=observed_model,
            verification_status=status,
            verification_evidence=evidence or {},
            exit_code=0 if success else 1,
            duration=duration_seconds,
            output=output,
            confidence=confidence,
        )


class HostAdapter(ABC):
    @abstractmethod
    def capabilities(self) -> dict: ...

    @abstractmethod
    def discover_models(self) -> list[str]: ...

    @abstractmethod
    def probe_model(self, model: str, repository: Path | None = None) -> ModelExecution: ...

    @abstractmethod
    def execute_agent(self, route: Route, prompt: str, repository: Path, read_only: bool) -> ModelExecution: ...

    @abstractmethod
    def verify_model_used(self, route: Route, result: ModelExecution) -> bool: ...

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
    def list_ready_tasks(
        self, label: str, board_id: int | None = None,
        completed_status: str = "",
    ) -> list[dict]: ...

    @abstractmethod
    def claim_task(self, task: dict, workspace_id: int, board_id: int, people_column: str = "") -> dict: ...

    @abstractmethod
    def create_story(self, story: dict, board_id: int, group_id: int) -> dict: ...

    @abstractmethod
    def find_story(self, marker: str, group_id: int) -> dict | None: ...

    @abstractmethod
    def transition(self, item_id: int, group_id: int) -> dict: ...

    @abstractmethod
    def set_status(self, item_id: int, board_id: int, column: str, value: str) -> dict: ...

    @abstractmethod
    def mark_ai(self, item_id: int, board_id: int, column: str) -> dict: ...

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
    def inspect_branch(
        self, repository: Path, branch: str, base: str | None = None,
    ) -> dict | None: ...

    @abstractmethod
    def checkout_revision(self, repository: Path, revision: str) -> dict: ...

    @abstractmethod
    def inspect_revision(self, repository: Path, revision: str) -> dict | None: ...

    @abstractmethod
    def restore_checkout(
        self, repository: Path, branch: str | None, revision: str,
    ) -> dict: ...

    @abstractmethod
    def inspect_restored_checkout(
        self, repository: Path, branch: str | None, revision: str,
    ) -> dict | None: ...

    @abstractmethod
    def publish_branch(self, repository: Path, branch: str) -> dict: ...

    @abstractmethod
    def open_pull_request(self, repository: Path, branch: str, base: str, title: str, body: str) -> dict: ...

    @abstractmethod
    def inspect_pull_request(self, repository: Path, reference: str) -> dict: ...
