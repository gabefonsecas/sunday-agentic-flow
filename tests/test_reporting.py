import tempfile
from pathlib import Path
import unittest

from sunday.reporting import markdown_report, report_data
from sunday.state import RunStore


class ReportingTests(unittest.TestCase):
    def test_report_includes_reliability_and_model_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = RunStore(Path(temporary) / "sunday.db")
            run = store.create("42", "demo", "codex")
            store.set_worktree(run.id, Path(temporary) / "worktree")
            store.save_effect(run.id, "friday:claim", "completed", {"assigned": True})
            store.event(run.id, "effect.reconciled", "intake", {
                "effect": "friday:claim", "outcome": "applied",
            })
            store.event(run.id, "route.completed", "discovery", {
                "phase": "discovery", "agent": "analyst", "model": "gpt-test",
                "observed_model": "gpt-test", "verification_status": "confirmed",
                "accepted": True, "duration_seconds": 1.0,
            })
            data = report_data(store, run.id)
            markdown = markdown_report(data)

        self.assertEqual(data["reliability"]["reconciled_effects"], 1)
        self.assertEqual(data["effects"][0]["effect_key"], "friday:claim")
        self.assertIn("confirmed", markdown)
        self.assertIn("External effects", markdown)
