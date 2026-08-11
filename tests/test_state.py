from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
import unittest

from sunday.state import DatabaseStateError, LeaseLostError, RunStore


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RunStore(Path(self.temp.name) / "state.db")

    def tearDown(self): self.temp.cleanup()

    def test_state_machine_releases_completed_task(self):
        run = self.store.create("42", "demo", "codex")
        for state in ("discovery", "stories", "publication", "implementation", "verification", "review", "pull_request", "completed"):
            run = self.store.transition(run.id, state)
        self.assertEqual(run.state, "completed")
        self.assertIsNone(self.store.active_for_task("42"))

    def test_duplicate_active_task_is_rejected(self):
        self.store.create("42", "demo", "codex")
        with self.assertRaisesRegex(RuntimeError, "active Sunday run"):
            self.store.create("42", "demo", "claude")

    def test_pause_remembers_resume_state(self):
        run = self.store.create("42", "demo", "codex")
        run = self.store.transition(run.id, "paused")
        self.assertEqual(run.resume_state, "intake")
        run = self.store.transition(run.id, "intake")
        self.assertEqual(run.state, "intake")

    def test_effect_is_idempotent_and_retryable(self):
        run = self.store.create("42", "demo", "codex")
        self.store.save_effect(run.id, "friday:create", "started", {})
        self.assertEqual(self.store.effects(run.id)[0]["effect_key"], "friday:create")
        self.assertEqual(self.store.uncertain_effects(run.id), ["friday:create"])
        self.assertEqual(self.store.retry_effects(run.id), ["friday:create"])
        self.assertEqual(
            self.store.effect(run.id, "friday:create")["status"], "retry_authorized"
        )

    def test_invalid_transition_fails(self):
        run = self.store.create("42", "demo", "codex")
        with self.assertRaisesRegex(RuntimeError, "Invalid transition"):
            self.store.transition(run.id, "review")

    def test_terminal_run_cannot_change_state(self):
        run = self.store.create("42", "demo", "codex")
        run = self.store.transition(run.id, "failed")
        with self.assertRaisesRegex(RuntimeError, "Terminal run"):
            self.store.transition(run.id, "paused")

    def test_operation_is_idempotent(self):
        operation, created = self.store.create_operation("create", "same-key", {"request": "work"})
        self.assertTrue(created)
        self.store.update_operation(operation.id, "completed", {"tasks": [{"id": 10}]})
        repeated, created = self.store.create_operation("create", "same-key", {})
        self.assertFalse(created)
        self.assertEqual(repeated.status, "completed")
        self.assertEqual(repeated.payload["tasks"][0]["id"], 10)

    def test_expired_lease_allows_a_new_run(self):
        first = self.store.create("42", "demo", "codex")
        with self.store.connect() as connection:
            expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            connection.execute(
                "UPDATE task_locks SET expires_at = ? WHERE run_id = ?",
                (expired, first.id),
            )
        replacement = RunStore(self.store.path, owner_id="replacement").create(
            "42", "demo", "claude"
        )
        self.assertEqual(self.store.active_for_task("42").id, replacement.id)

    def test_foreign_owner_cannot_heartbeat_active_lease(self):
        run = self.store.create("42", "demo", "codex")
        contender = RunStore(self.store.path, owner_id="contender")
        with self.assertRaises(LeaseLostError):
            contender.heartbeat(run.id)

    def test_heartbeat_context_renews_long_running_lease(self):
        path = Path(self.temp.name) / "heartbeat.db"
        owner = RunStore(path, lease_seconds=0.2, heartbeat_seconds=0.03)
        run = owner.create("99", "demo", "codex")
        with owner.heartbeat_lease(run.id):
            time.sleep(0.3)
            contender = RunStore(path, lease_seconds=0.2, owner_id="contender")
            with self.assertRaises(LeaseLostError):
                contender.acquire_lease(run.id)

    def test_lost_lease_invokes_cancellation_callback(self):
        path = Path(self.temp.name) / "lost.db"
        owner = RunStore(path, lease_seconds=0.2, heartbeat_seconds=0.02)
        run = owner.create("100", "demo", "codex")
        cancelled = threading.Event()
        with self.assertRaises(LeaseLostError):
            with owner.heartbeat_lease(run.id, cancelled.set):
                with owner.connect() as connection:
                    connection.execute(
                        "UPDATE task_locks SET owner_id = ? WHERE run_id = ?",
                        ("replacement", run.id),
                    )
                self.assertTrue(cancelled.wait(0.3))

    def test_lost_lease_overrides_simultaneous_body_failure(self):
        path = Path(self.temp.name) / "lost-with-body-error.db"
        owner = RunStore(path, lease_seconds=0.2, heartbeat_seconds=0.02)
        run = owner.create("101", "demo", "codex")
        cancelled = threading.Event()
        with self.assertRaises(LeaseLostError):
            with owner.heartbeat_lease(run.id, cancelled.set):
                with owner.connect() as connection:
                    connection.execute(
                        "UPDATE task_locks SET owner_id = ? WHERE run_id = ?",
                        ("replacement", run.id),
                    )
                self.assertTrue(cancelled.wait(0.3))
                raise ValueError("phase also failed")

    def test_worktree_path_is_persisted(self):
        run = self.store.create("42", "demo", "codex")
        path = Path(self.temp.name) / "worktrees" / run.id
        updated = self.store.set_worktree(run.id, path)
        self.assertEqual(updated.worktree_path, str(path.resolve()))

    def test_database_uses_busy_timeout(self):
        with self.store.connect() as connection:
            timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertEqual(timeout, 30000)

    def test_corrupt_database_is_preserved_with_actionable_error(self):
        corrupt = Path(self.temp.name) / "corrupt.db"
        original = b"not a sqlite database"
        corrupt.write_bytes(original)
        with self.assertRaisesRegex(DatabaseStateError, "preserved"):
            RunStore(corrupt)
        self.assertEqual(corrupt.read_bytes(), original)

    def test_legacy_database_is_migrated_additively(self):
        path = Path(self.temp.name) / "legacy.db"
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE runs (
                id TEXT PRIMARY KEY, task_ref TEXT NOT NULL, project TEXT NOT NULL,
                host TEXT NOT NULL, state TEXT NOT NULL, resume_state TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE task_locks (
                task_ref TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL
            );
            """
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)",
            ("legacy", "7", "demo", "codex", "intake", timestamp, timestamp, "{}"),
        )
        connection.execute(
            "INSERT INTO task_locks VALUES (?, ?, ?)", ("7", "legacy", timestamp)
        )
        connection.commit()
        connection.close()

        migrated = RunStore(path, owner_id="legacy")
        self.assertIsNone(migrated.get("legacy").worktree_path)
        self.assertEqual(migrated.heartbeat("legacy")["owner_id"], "legacy")
        self.assertTrue(Path(f"{path}.backup-v0").is_file())
        with migrated.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
