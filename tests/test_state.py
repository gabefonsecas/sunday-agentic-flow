import tempfile
from pathlib import Path
import unittest

from sunday.state import RunStore


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
        self.assertEqual(self.store.uncertain_effects(run.id), ["friday:create"])
        self.assertEqual(self.store.retry_effects(run.id), ["friday:create"])
        self.assertIsNone(self.store.effect(run.id, "friday:create"))

    def test_invalid_transition_fails(self):
        run = self.store.create("42", "demo", "codex")
        with self.assertRaisesRegex(RuntimeError, "Invalid transition"):
            self.store.transition(run.id, "review")

    def test_terminal_run_cannot_change_state(self):
        run = self.store.create("42", "demo", "codex")
        run = self.store.transition(run.id, "failed")
        with self.assertRaisesRegex(RuntimeError, "Terminal run"):
            self.store.transition(run.id, "paused")
