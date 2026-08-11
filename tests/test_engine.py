import tempfile
from pathlib import Path
import unittest

from sunday.adapters.base import ExecutionResult
from sunday.config import ProjectConfig, Settings
from sunday.engine import SundayEngine
from sunday.state import RunStore
from tests.fakes import FakeGit, FakeHost, FakeHosts, FakeTasks


class RetryHost(FakeHost):
    def execute_agent(self, route, prompt, repository, read_only):
        self.routes.append(route)
        discovery_attempts = [item for item in self.routes if item.phase == "discovery"]
        if route.phase == "discovery" and len(discovery_attempts) == 1:
            return ExecutionResult(
                False, "SUNDAY_RESULT: {\"success\": false, \"summary\": \"retry\"}",
                route.model, route.model, True, 0.1, 0.2, {"fake": True},
            )
        stories = ""
        if route.phase == "discovery":
            stories = 'SUNDAY_STORIES: [{"title":"[dev] outcome","description":"complete story"}]\n'
        output = stories + 'SUNDAY_RESULT: {"success": true, "confidence": 0.95, "summary": "passed"}'
        return ExecutionResult(True, output, route.model, route.model, True, 0.1, 0.95, {"fake": True})


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = Path(self.temp.name) / "repo"
        self.repository.mkdir()
        self.store = RunStore(Path(self.temp.name) / "sunday.db")
        self.project = ProjectConfig(
            "demo", self.repository, workspace_id=1, board_id=2,
            intake_group_id=3, states={"discovery": 10, "implementation": 11, "verification": 12, "review": 13, "completed": 14},
        )
        self.tasks = FakeTasks()
        self.git = FakeGit()
        self.hosts = FakeHosts()
        self.engine = SundayEngine(
            Settings(projects={"demo": self.project}), self.store, self.tasks, self.git, self.hosts
        )

    def tearDown(self): self.temp.cleanup()

    def test_complete_flow_creates_pr_and_audit_routes(self):
        run = self.engine.start("42", self.project, "codex")
        self.assertEqual(run.state, "completed")
        self.assertEqual(run.metadata["pull_request"]["url"], "https://github.test/pr/1")
        self.assertEqual([route.phase for route in self.hosts.host.routes], ["discovery", "implementation", "verification", "review"])
        route_events = [event for event in self.store.events(run.id) if event["kind"] == "route.completed"]
        self.assertTrue(all(event["payload"]["model_verified"] for event in route_events))
        self.assertEqual(len([call for call in self.tasks.calls if call[0] == "story"]), 1)

    def test_homolog_intent_selects_homolog(self):
        self.tasks.task["description"] = "Release para homolog"
        run = self.engine.start("42", self.project, "codex")
        self.assertEqual(run.metadata["base_branch"], "homolog")

    def test_high_risk_task_pauses_until_approval(self):
        self.tasks.task["description"] = "Deploy production database migration"
        run = self.engine.start("42", self.project, "codex")
        self.assertEqual(run.state, "paused")
        self.assertEqual(run.resume_state, "publication")
        run = self.engine.resume(run.id, self.project, approved=True)
        self.assertEqual(run.state, "completed")

    def test_external_effects_are_not_repeated_on_phase_resume(self):
        run = self.store.create("42", "demo", "codex")
        first = self.engine._effect(run, "once", lambda: {"id": 1})
        second = self.engine._effect(run, "once", lambda: {"id": 2})
        self.assertEqual(first, second)

    def test_route_models_change_across_phases(self):
        self.engine.start("42", self.project, "codex")
        models = [route.model for route in self.hosts.host.routes]
        self.assertGreaterEqual(len(set(models)), 2)

    def test_failed_route_escalates_model_and_emits_progress(self):
        hosts = FakeHosts()
        hosts.host = RetryHost()
        progress = []
        engine = SundayEngine(
            Settings(projects={"demo": self.project}), self.store,
            self.tasks, self.git, hosts, progress=lambda kind, payload: progress.append((kind, payload)),
        )
        run = engine.start("42", self.project, "codex")
        discovery = [route for route in hosts.host.routes if route.phase == "discovery"]
        self.assertEqual(run.state, "completed")
        self.assertEqual([route.model for route in discovery], ["gpt-5.6-luna", "gpt-5.6-terra"])
        self.assertEqual([kind for kind, _ in progress[:4]], [
            "route.started", "route.completed", "route.started", "route.completed",
        ])

    def test_completed_task_cannot_publish_again(self):
        first = self.engine.start("42", self.project, "codex")
        with self.assertRaisesRegex(RuntimeError, first.id):
            self.engine.start("42", self.project, "codex")

    def test_status_column_is_updated_instead_of_moving_groups(self):
        states = {
            "discovery": "working", "stories": "working", "publication": "working",
            "implementation": "working", "verification": "qa", "review": "review",
            "pull_request": "release", "completed": "done",
        }
        project = ProjectConfig(
            "status-board", self.repository, workspace_id=1, board_id=2,
            intake_group_id=3, states=states, status_column="201",
        )
        engine = SundayEngine(
            Settings(projects={"status-board": project}), self.store,
            self.tasks, self.git, self.hosts,
        )
        engine.start("42", project, "codex")
        status_values = [call[4] for call in self.tasks.calls if call[0] == "status"]
        self.assertEqual(
            status_values,
            ["working", "working", "working", "working", "qa", "review", "release", "done"],
        )
        self.assertFalse(any(call[0] == "transition" for call in self.tasks.calls))
