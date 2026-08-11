"""Isolated Git worktrees owned by Sunday runs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
from typing import TYPE_CHECKING

from .paths import state_dir

if TYPE_CHECKING:
    from .state import RunStore


RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def run(command: list[str], repository: Path, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command, cwd=repository, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{result.stderr.strip()}")
    return result


class WorktreeManager:
    def __init__(self, root: Path | None = None):
        self.root = (root or state_dir() / "worktrees").expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, run_id: str) -> Path:
        if not RUN_ID.fullmatch(run_id):
            raise ValueError(f"Invalid Sunday run ID: {run_id}")
        return self.root / run_id

    def inspect(
        self, repository: Path, run_id: str, branch: str | None = None,
    ) -> dict | None:
        destination = self._managed_path(run_id)
        records = self._records(repository)
        record = next(
            (item for item in records if Path(item["path"]).resolve() == destination),
            None,
        )
        if not record:
            if destination.exists():
                raise RuntimeError(f"Unregistered path blocks Sunday worktree: {destination}")
            return None
        if branch and record.get("branch") != branch:
            raise RuntimeError(
                f"Sunday worktree branch mismatch: {record.get('branch')} != {branch}"
            )
        return {**record, "path": str(destination), "existing": True}

    def create(self, repository: Path, run_id: str, branch: str, base: str) -> dict:
        repository = repository.resolve()
        existing = self.inspect(repository, run_id, branch)
        if existing:
            return {**existing, "base": base}
        destination = self._managed_path(run_id)
        run(["git", "fetch", "origin", base], repository)
        branch_exists = run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            repository, False,
        ).returncode == 0
        if branch_exists:
            raise RuntimeError(
                f"Refusing to reuse an unregistered existing branch: {branch}"
            )
        command = [
            "git", "worktree", "add", "-b", branch,
            str(destination), f"origin/{base}",
        ]
        run(command, repository)
        created = self.inspect(repository, run_id, branch)
        if not created:
            raise RuntimeError("Git did not register the Sunday worktree")
        return {**created, "base": base, "existing": False}

    def create_detached(
        self, repository: Path, run_id: str, revision: str,
    ) -> dict:
        repository = repository.resolve()
        existing = self.inspect(repository, run_id)
        if existing:
            if existing.get("head") != revision:
                raise RuntimeError(
                    f"Sunday review worktree revision mismatch: "
                    f"{existing.get('head')} != {revision}"
                )
            return {**existing, "revision": revision}
        destination = self._managed_path(run_id)
        run(
            ["git", "worktree", "add", "--detach", str(destination), revision],
            repository,
        )
        created = self.inspect(repository, run_id)
        if not created or created.get("head") != revision:
            raise RuntimeError("Git did not register the Sunday review worktree")
        return {**created, "revision": revision, "existing": False}

    def remove(self, repository: Path, run_id: str, branch: str | None = None) -> dict:
        repository = repository.resolve()
        destination = self._managed_path(run_id)
        existing = self.inspect(repository, run_id, branch)
        if not existing:
            return {"path": str(destination), "removed": True, "reconciled": True}
        status = run(
            ["git", "status", "--porcelain", "--ignored"], destination,
        ).stdout.splitlines()
        if status:
            raise RuntimeError("Refusing to remove a dirty Sunday worktree")
        run(["git", "worktree", "remove", str(destination)], repository)
        if self.inspect(repository, run_id, branch):
            raise RuntimeError("Git still reports the removed Sunday worktree")
        return {"path": str(destination), "removed": True}

    def _managed_path(self, run_id: str) -> Path:
        destination = self.path_for(run_id).resolve()
        if destination.parent != self.root:
            raise RuntimeError(f"Sunday worktree escaped its managed root: {destination}")
        return destination

    @staticmethod
    def _records(repository: Path) -> list[dict]:
        output = run(["git", "worktree", "list", "--porcelain"], repository).stdout
        records: list[dict] = []
        current: dict[str, str] = {}
        for line in (*output.splitlines(), ""):
            if not line:
                if current:
                    records.append(current)
                    current = {}
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                current["path"] = value
            elif key == "HEAD":
                current["head"] = value
            elif key == "branch":
                current["branch"] = value.removeprefix("refs/heads/")
            elif key == "detached":
                current["detached"] = "true"
        return records


def cleanup_worktrees(
    store: RunStore,
    run_id: str | None = None,
    older_than_days: int | None = None,
    repository: Path | str | None = None,
) -> dict[str, list[dict]]:
    """Remove eligible completed worktrees without deleting files directly."""
    manager = WorktreeManager(store.path.parent / "worktrees")
    runs = [store.get(run_id)] if run_id else store.list(limit=1_000_000)
    cutoff = None
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, older_than_days))
    selected_repository = Path(repository).expanduser().resolve() if repository else None
    result: dict[str, list[dict]] = {"removed": [], "preserved": []}

    for item in runs:
        record = {"run_id": item.id, "path": item.worktree_path}
        source_value = item.metadata.get("repository")
        source = Path(source_value).expanduser().resolve() if source_value else None
        if selected_repository and source != selected_repository:
            continue
        if item.state != "completed":
            result["preserved"].append({**record, "reason": f"run_{item.state}"})
            continue
        if store.active_for_task(item.task_ref):
            result["preserved"].append({**record, "reason": "active_lease"})
            continue
        retained_until = item.metadata.get("retained_until")
        if retained_until and datetime.fromisoformat(str(retained_until)) > datetime.now(timezone.utc):
            result["preserved"].append({**record, "reason": "retained"})
            continue
        if cutoff and datetime.fromisoformat(item.updated_at) > cutoff:
            result["preserved"].append({**record, "reason": "too_recent"})
            continue
        if not item.worktree_path:
            result["preserved"].append({**record, "reason": "missing_path"})
            continue
        try:
            expected = manager._managed_path(item.id)
        except Exception as exc:
            result["preserved"].append({**record, "reason": str(exc)})
            continue
        if Path(item.worktree_path).expanduser().resolve() != expected:
            result["preserved"].append({**record, "reason": "unmanaged_path"})
            continue
        if not source:
            result["preserved"].append({**record, "reason": "missing_repository"})
            continue
        try:
            removed = manager.remove(source, item.id, item.metadata.get("branch"))
        except Exception as exc:
            result["preserved"].append({**record, "reason": str(exc)})
        else:
            result["removed"].append({"run_id": item.id, **removed})
    return result
