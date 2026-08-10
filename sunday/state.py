"""Durable run state, events, locks, and idempotency."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator
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


class RunStore:
    def __init__(self, path: Path | None = None):
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.path.parent.chmod(0o700)
        self._initialize()
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

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
                    metadata_json TEXT NOT NULL
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
                    acquired_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_run_id ON events(run_id, id);
                """
            )

    def create(self, task_ref: str, project: str, host: str, metadata: dict | None = None) -> Run:
        run_id = str(uuid4())
        timestamp = now()
        clean = redact(metadata or {})
        with self.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO runs VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)",
                    (run_id, task_ref, project, host, "intake", timestamp, timestamp, json.dumps(clean)),
                )
                connection.execute(
                    "INSERT INTO task_locks VALUES (?, ?, ?)",
                    (task_ref, run_id, timestamp),
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
            row = connection.execute(
                "SELECT runs.* FROM task_locks JOIN runs ON runs.id = task_locks.run_id WHERE task_locks.task_ref = ?",
                (task_ref,),
            ).fetchone()
        return self._run(row) if row else None

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
                "DELETE FROM effects WHERE run_id = ? AND status = 'started'", (run_id,)
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
        )
