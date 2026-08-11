"""Durable run state, events, locks, and idempotency."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Callable, Iterator
from uuid import uuid4

from .paths import database_path
from .security import redact

STATES = (
    "intake",
    "discovery",
    "stories",
    "publication",
    "implementation",
    "verification",
    "review",
    "pull_request",
    "completed",
    "paused",
    "failed",
)
TERMINAL_STATES = {"completed", "failed"}
DEFAULT_LEASE_SECONDS = 300
SCHEMA_VERSION = 2
NEXT_STATE = {
    "intake": "discovery",
    "discovery": "stories",
    "stories": "publication",
    "publication": "implementation",
    "implementation": "verification",
    "verification": "review",
    "review": "pull_request",
    "pull_request": "completed",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def expires_at(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class LeaseLostError(RuntimeError):
    """The run no longer owns its execution lease."""


class DatabaseStateError(RuntimeError):
    """Sunday state is unavailable without destructive automatic recovery."""


@dataclass(slots=True)
class Run:
    id: str
    task_ref: str
    project: str
    host: str
    state: str
    resume_state: str | None
    created_at: str
    updated_at: str
    metadata: dict
    worktree_path: str | None = None


@dataclass(slots=True)
class Operation:
    id: str
    kind: str
    idempotency_key: str
    status: str
    created_at: str
    updated_at: str
    payload: dict


class RunStore:
    def __init__(
        self,
        path: Path | None = None,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        heartbeat_seconds: float | None = None,
        owner_id: str | None = None,
    ):
        self.path = path or database_path()
        self.lease_seconds = max(float(lease_seconds), 0.1)
        configured_heartbeat = (
            self.lease_seconds / 3 if heartbeat_seconds is None else float(heartbeat_seconds)
        )
        self.heartbeat_seconds = max(0.001, min(configured_heartbeat, self.lease_seconds / 3))
        self.owner_id = owner_id or str(uuid4())
        self.migration_backup_path: Path | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.path.parent.chmod(0o700)
        try:
            self._backup_before_migration()
            self._initialize()
            self._check_integrity()
        except sqlite3.DatabaseError as exc:
            raise DatabaseStateError(
                f"Sunday state database is invalid or unavailable: {self.path}. "
                "The file was preserved for manual recovery."
            ) from exc
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _check_integrity(self) -> None:
        with self.connect() as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise DatabaseStateError(
                f"Sunday state database failed integrity check: {self.path}: {result}"
            )

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    task_ref TEXT NOT NULL,
                    project TEXT NOT NULL,
                    host TEXT NOT NULL,
                    state TEXT NOT NULL,
                    resume_state TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    worktree_path TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    timestamp TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    phase TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS effects (
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    effect_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, effect_key)
                );
                CREATE TABLE IF NOT EXISTS task_locks (
                    task_ref TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    acquired_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    owner_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_run_id ON events(run_id, id);
                """
            )
            self._migrate(connection)
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version < SCHEMA_VERSION:
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _backup_before_migration(self) -> None:
        if not self.path.is_file() or self.path.stat().st_size == 0:
            return
        source = sqlite3.connect(self.path, timeout=30)
        try:
            version = int(source.execute("PRAGMA user_version").fetchone()[0])
            if version >= SCHEMA_VERSION:
                return
            backup_path = self.path.with_name(f"{self.path.name}.backup-v{version}")
            if not backup_path.exists():
                destination = sqlite3.connect(backup_path)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
                if os.name != "nt":
                    backup_path.chmod(0o600)
            self.migration_backup_path = backup_path
        finally:
            source.close()

    def _migrate(self, connection: sqlite3.Connection) -> None:
        """Apply additive migrations to existing Sunday databases."""
        if "worktree_path" not in self._columns(connection, "runs"):
            connection.execute("ALTER TABLE runs ADD COLUMN worktree_path TEXT")

        lock_columns = self._columns(connection, "task_locks")
        for column in ("heartbeat_at", "expires_at", "owner_id"):
            if column not in lock_columns:
                connection.execute(f"ALTER TABLE task_locks ADD COLUMN {column} TEXT")
        timestamp = now()
        connection.execute(
            "UPDATE task_locks SET heartbeat_at = COALESCE(heartbeat_at, acquired_at, ?)",
            (timestamp,),
        )
        connection.execute(
            "UPDATE task_locks SET expires_at = COALESCE(expires_at, ?)",
            (expires_at(self.lease_seconds),),
        )
        connection.execute(
            "UPDATE task_locks SET owner_id = COALESCE(owner_id, 'legacy')"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS task_locks_expiration ON task_locks(expires_at)"
        )

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}

    def create_operation(self, kind: str, idempotency_key: str, payload: dict) -> tuple[Operation, bool]:
        timestamp = now()
        operation_id = str(uuid4())
        clean = redact(payload)
        with self.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO operations VALUES (?, ?, ?, 'started', ?, ?, ?)",
                    (operation_id, kind, idempotency_key, timestamp, timestamp, json.dumps(clean)),
                )
                created = True
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT * FROM operations WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
                if not row:
                    raise
                return self._operation(row), False
        return self.get_operation(operation_id), created

    def get_operation(self, operation_id: str) -> Operation:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM operations WHERE id = ?", (operation_id,)).fetchone()
        if not row:
            raise KeyError(f"Unknown operation: {operation_id}")
        return self._operation(row)

    def update_operation(self, operation_id: str, status: str, payload: dict) -> Operation:
        with self.connect() as connection:
            connection.execute(
                "UPDATE operations SET status = ?, updated_at = ?, payload_json = ? WHERE id = ?",
                (status, now(), json.dumps(redact(payload), ensure_ascii=False), operation_id),
            )
        return self.get_operation(operation_id)

    def create(self, task_ref: str, project: str, host: str, metadata: dict | None = None) -> Run:
        run_id = str(uuid4())
        timestamp = now()
        clean = redact(metadata or {})
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM task_locks WHERE expires_at <= ?", (timestamp,))
                connection.execute(
                    """
                    INSERT INTO runs(
                        id, task_ref, project, host, state, resume_state,
                        created_at, updated_at, metadata_json, worktree_path
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)
                    """,
                    (run_id, task_ref, project, host, "intake", timestamp, timestamp, json.dumps(clean)),
                )
                connection.execute(
                    """
                    INSERT INTO task_locks(
                        task_ref, run_id, acquired_at, heartbeat_at, expires_at, owner_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_ref, run_id, timestamp, timestamp,
                        expires_at(self.lease_seconds), self.owner_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RuntimeError(f"Task already has an active Sunday run: {task_ref}") from exc
        self.event(run_id, "run.created", "intake", clean)
        return self.get(run_id)

    def get(self, run_id: str) -> Run:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise KeyError(f"Unknown run: {run_id}")
        return self._run(row)

    def active_for_task(self, task_ref: str) -> Run | None:
        with self.connect() as connection:
            connection.execute("DELETE FROM task_locks WHERE expires_at <= ?", (now(),))
            row = connection.execute(
                "SELECT runs.* FROM task_locks JOIN runs ON runs.id = task_locks.run_id WHERE task_locks.task_ref = ?",
                (task_ref,),
            ).fetchone()
        return self._run(row) if row else None

    def acquire_lease(self, run_id: str) -> dict:
        timestamp = now()
        expiration = expires_at(self.lease_seconds)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not run:
                raise KeyError(f"Unknown run: {run_id}")
            if run["state"] in TERMINAL_STATES:
                raise LeaseLostError(f"Terminal run cannot acquire a lease: {run_id}")
            connection.execute("DELETE FROM task_locks WHERE expires_at <= ?", (timestamp,))
            lock = connection.execute(
                "SELECT * FROM task_locks WHERE task_ref = ?", (run["task_ref"],)
            ).fetchone()
            same_owner = lock and lock["run_id"] == run_id and lock["owner_id"] == self.owner_id
            paused_takeover = lock and lock["run_id"] == run_id and run["state"] == "paused"
            if lock and not (same_owner or paused_takeover):
                raise LeaseLostError(f"Task lease is owned by Sunday run {lock['run_id']}")
            if lock:
                connection.execute(
                    """
                    UPDATE task_locks
                    SET run_id = ?, heartbeat_at = ?, expires_at = ?, owner_id = ?
                    WHERE task_ref = ?
                    """,
                    (run_id, timestamp, expiration, self.owner_id, run["task_ref"]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO task_locks(
                        task_ref, run_id, acquired_at, heartbeat_at, expires_at, owner_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run["task_ref"], run_id, timestamp, timestamp,
                        expiration, self.owner_id,
                    ),
                )
        return self.lease_status(run_id)

    def heartbeat(self, run_id: str) -> dict:
        timestamp = now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE task_locks SET heartbeat_at = ?, expires_at = ?
                WHERE run_id = ? AND owner_id = ? AND expires_at > ?
                """,
                (
                    timestamp, expires_at(self.lease_seconds), run_id,
                    self.owner_id, timestamp,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseLostError(f"Sunday run lost its lease: {run_id}")
        return self.lease_status(run_id)

    def lease_status(self, run_id: str) -> dict:
        with self.connect() as connection:
            connection.execute("DELETE FROM task_locks WHERE expires_at <= ?", (now(),))
            row = connection.execute(
                "SELECT * FROM task_locks WHERE run_id = ?", (run_id,)
            ).fetchone()
        if not row:
            raise LeaseLostError(f"Sunday run has no lease: {run_id}")
        return dict(row)

    @contextmanager
    def heartbeat_lease(
        self, run_id: str, on_lost: Callable[[], None] | None = None,
    ) -> Iterator[None]:
        """Renew a run lease while a long phase executes."""
        self.acquire_lease(run_id)
        stopped = threading.Event()
        failures: list[BaseException] = []
        interval = self.heartbeat_seconds

        def renew() -> None:
            while not stopped.wait(interval):
                try:
                    self.heartbeat(run_id)
                except BaseException as exc:
                    failures.append(exc)
                    stopped.set()
                    if on_lost:
                        try:
                            on_lost()
                        except BaseException:
                            pass

        thread = threading.Thread(target=renew, name=f"sunday-lease-{run_id}", daemon=True)
        thread.start()
        body_error: BaseException | None = None
        try:
            yield
        except BaseException as exc:
            body_error = exc
        finally:
            stopped.set()
            thread.join(timeout=max(1.0, interval * 2))
        if failures:
            raise LeaseLostError(str(failures[0])) from failures[0]
        if body_error:
            raise body_error.with_traceback(body_error.__traceback__)

    def latest_for_task(self, task_ref: str) -> Run | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE task_ref = ? ORDER BY created_at DESC LIMIT 1",
                (task_ref,),
            ).fetchone()
        return self._run(row) if row else None

    def list(self, limit: int = 20) -> list[Run]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._run(row) for row in rows]

    def transition(self, run_id: str, target: str, payload: dict | None = None) -> Run:
        if target not in STATES:
            raise ValueError(f"Unknown state: {target}")
        current = self.get(run_id)
        if current.state in TERMINAL_STATES:
            raise RuntimeError(f"Terminal run cannot transition: {current.state}")
        allowed = {NEXT_STATE.get(current.state), "paused", "failed"}
        if current.state == "paused" and current.resume_state:
            allowed.add(current.resume_state)
        if target not in allowed:
            raise RuntimeError(f"Invalid transition: {current.state} -> {target}")
        resume_state = current.state if target == "paused" else None
        timestamp = now()
        with self.connect() as connection:
            connection.execute(
                "UPDATE runs SET state = ?, resume_state = ?, updated_at = ? WHERE id = ?",
                (target, resume_state, timestamp, run_id),
            )
            if target in TERMINAL_STATES:
                connection.execute("DELETE FROM task_locks WHERE run_id = ?", (run_id,))
        self.event(run_id, "state.transition", target, payload or {"from": current.state})
        return self.get(run_id)

    def update_metadata(self, run_id: str, values: dict) -> Run:
        run = self.get(run_id)
        metadata = dict(run.metadata)
        metadata.update(redact(values))
        with self.connect() as connection:
            connection.execute(
                "UPDATE runs SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(metadata), now(), run_id),
            )
        return self.get(run_id)

    def set_worktree(self, run_id: str, path: Path | str) -> Run:
        value = str(Path(path).resolve())
        with self.connect() as connection:
            connection.execute(
                "UPDATE runs SET worktree_path = ?, updated_at = ? WHERE id = ?",
                (value, now(), run_id),
            )
        return self.get(run_id)

    def event(self, run_id: str, kind: str, phase: str | None, payload: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO events(run_id, timestamp, kind, phase, payload_json) VALUES (?, ?, ?, ?, ?)",
                (run_id, now(), kind, phase, json.dumps(redact(payload), ensure_ascii=False)),
            )

    def events(self, run_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "kind": row["kind"],
                "phase": row["phase"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def effect(self, run_id: str, key: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM effects WHERE run_id = ? AND effect_key = ?", (run_id, key)
            ).fetchone()
        if not row:
            return None
        return {"status": row["status"], "payload": json.loads(row["payload_json"])}

    def effects(self, run_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM effects WHERE run_id = ? ORDER BY effect_key", (run_id,)
            ).fetchall()
        return [
            {
                "effect_key": row["effect_key"], "status": row["status"],
                "payload": json.loads(row["payload_json"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def save_effect(self, run_id: str, key: str, status: str, payload: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO effects VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, effect_key) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (run_id, key, status, json.dumps(redact(payload), ensure_ascii=False), now()),
            )

    def uncertain_effects(self, run_id: str) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT effect_key FROM effects WHERE run_id = ? AND status = 'started' ORDER BY effect_key",
                (run_id,),
            ).fetchall()
        return [row["effect_key"] for row in rows]

    def retry_effects(self, run_id: str) -> list[str]:
        keys = self.uncertain_effects(run_id)
        with self.connect() as connection:
            connection.execute(
                "UPDATE effects SET status = 'retry_authorized', updated_at = ? "
                "WHERE run_id = ? AND status = 'started'",
                (now(), run_id),
            )
        self.event(run_id, "effect.retry_authorized", None, {"keys": keys})
        return keys

    @staticmethod
    def _run(row: sqlite3.Row) -> Run:
        return Run(
            id=row["id"], task_ref=row["task_ref"], project=row["project"],
            host=row["host"], state=row["state"], resume_state=row["resume_state"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"]),
            worktree_path=row["worktree_path"] if "worktree_path" in row.keys() else None,
        )

    @staticmethod
    def _operation(row: sqlite3.Row) -> Operation:
        return Operation(
            id=row["id"], kind=row["kind"], idempotency_key=row["idempotency_key"],
            status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"],
            payload=json.loads(row["payload_json"]),
        )
