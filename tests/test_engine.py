import tempfile
from pathlib import Path
import unittest

from sunday.adapters.base import ExecutionResult
from sunday.config import ProjectConfig, Settings
from sunday.engine import SundayEngine
from sunday.state import LeaseLostError, RunStore
from tests.fakes import FakeGit, FakeHost, FakeHosts, FakeTasks, FakeWorktrees


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


class MismatchedPullRequestGit(FakeGit):
    def inspect_pull_request(self, repository, reference):
        return {
            "url": reference, "headRefName": "someone/else",
            "baseRefName": "main",
        }


class ProbedHost(FakeHost):
    def __init__(self):
        super().__init__()
        self.probes = []

    def probe_model(self, model, repository=None):
        self.probes.append(model)
        available = model != "gpt-5.4"
        return ExecutionResult(
            available, "probe", model, model if available else None,
            available, 0.01, evidence={"probe": True},
        )


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
        self.worktrees = FakeWorktrees(Path(self.temp.name) / "worktrees")
        self.engine = SundayEngine(
            Settings(projects={"demo": self.project}), self.store, self.tasks,
            self.git, self.hosts, worktrees=self.worktrees,
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
        self.assertTrue(run.worktree_path)
        self.assertTrue(all(
            repository == Path(run.worktree_path)
            for repository in self.hosts.host.repositories
        ))

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

    def test_started_effect_uses_probe_before_retrying(self):
        run = self.store.create("42", "demo", "codex")
        self.store.save_effect(run.id, "remote:update", "started", {"value": "x"})
        calls = []
        result = self.engine._effect(
            run, "remote:update", lambda: calls.append("action") or {"updated": True},
            reconcile=lambda payload: {"updated": True, "value": payload["value"]},
        )
        self.assertEqual(result, {"updated": True, "value": "x"})
        self.assertEqual(calls, [])

    def test_probe_confirming_absence_retries_effect(self):
        run = self.store.create("42", "demo", "codex")
        self.store.save_effect(run.id, "remote:update", "started", {})
        calls = []
        result = self.engine._effect(
            run, "remote:update", lambda: calls.append("action") or {"updated": True},
            reconcile=lambda _: None,
        )
        self.assertEqual(result, {"updated": True})
        self.assertEqual(calls, ["action"])

    def test_lost_lease_after_reconcile_blocks_external_action(self):
        run = self.store.create("42", "demo", "codex")
        self.store.save_effect(run.id, "remote:update", "started", {})
        calls = []

        def lose_lease(_payload):
            with self.store.connect() as connection:
                connection.execute(
                    "UPDATE task_locks SET owner_id = ? WHERE run_id = ?",
                    ("replacement", run.id),
                )
            return None

        with self.assertRaises(LeaseLostError):
            self.engine._effect(
                run, "remote:update",
                lambda: calls.append("action") or {"updated": True},
                reconcile=lose_lease,
            )
        self.assertEqual(calls, [])

    def test_manual_reconciliation_authorizes_unprobeable_effect(self):
        run = self.store.create("42", "demo", "codex")
        self.store.save_effect(run.id, "remote:comment", "started", {})
        self.store.retry_effects(run.id)
        result = self.engine._effect(
            run, "remote:comment", lambda: {"commented": True},
        )
        self.assertEqual(result, {"commented": True})
        self.assertEqual(
            self.store.effect(run.id, "remote:comment")["status"], "completed"
        )

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
            self.tasks, self.git, hosts,
            progress=lambda kind, payload: progress.append((kind, payload)),
            worktrees=self.worktrees,
        )
        run = engine.start("42", self.project, "codex")
        discovery = [route for route in hosts.host.routes if route.phase == "discovery"]
        self.assertEqual(run.state, "completed")
        self.assertEqual([route.model for route in discovery], ["gpt-5.4", "gpt-5.6-terra"])
        route_progress = [(kind, payload) for kind, payload in progress if kind.startswith("route.")]
        self.assertEqual([kind for kind, _ in route_progress[:4]], [
            "route.started", "route.completed", "route.started", "route.completed",
        ])

    def test_strict_probe_skips_unavailable_candidate_and_records_evidence(self):
        hosts = FakeHosts()
        hosts.host = ProbedHost()
        engine = SundayEngine(
            Settings(projects={"demo": self.project}), self.store,
            self.tasks, self.git, hosts, worktrees=self.worktrees,
        )
        run = engine.start("42", self.project, "codex")
        discovery_events = [
            event for event in self.store.events(run.id)
            if event["kind"] == "route.completed" and event["phase"] == "discovery"
        ]
        self.assertEqual(discovery_events[0]["payload"]["verification_status"], "unavailable")
        self.assertEqual(discovery_events[0]["payload"]["exit_code"], 1)
        self.assertEqual(hosts.host.routes[0].model, "gpt-5.6-terra")
        self.assertEqual(len(hosts.host.probes), len(set(hosts.host.probes)))

    def test_git_and_github_effects_never_use_models(self):
        progress = []
        engine = SundayEngine(
            Settings(projects={"demo": self.project}), self.store,
            self.tasks, self.git, self.hosts,
            progress=lambda kind, payload: progress.append((kind, payload)),
            worktrees=self.worktrees,
        )
        engine.start("42", self.project, "codex")
        operations = [
            payload for kind, payload in progress
            if kind == "effect.completed" and payload["effect"].startswith(("git:", "github:"))
        ]
        self.assertTrue(operations)
        self.assertTrue(all(operation["model"] is None for operation in operations))

    def test_review_command_uses_detached_worktree_and_skips_friday(self):
        run = self.engine.review_only("feature/review-me", self.project, "codex")
        self.assertEqual(run.state, "completed")
        self.assertTrue(run.metadata["review_only"])
        self.assertEqual(run.metadata["review_target"]["commit"], "abc123")
        self.assertIn(
            ("create_detached", run.id, "abc123"), self.worktrees.calls
        )
        self.assertEqual(self.tasks.calls, [])
        self.assertEqual(self.hosts.host.repositories, [Path(run.worktree_path)])

    def test_review_resume_keeps_commit_persisted_before_completed_effect(self):
        resolved = {
            "reference": "feature/moving", "commit": "old123", "kind": "branch",
            "headRefName": "feature/moving", "baseRefName": "main",
            "baseCommit": "base123",
        }
        run = self.store.create(
            "review:feature/moving", "demo", "codex",
            {
                "repository": str(self.repository), "title": "Review moving",
                "description": "Independent review", "review_only": True,
                "review_reference": "feature/moving",
                "review_target_pending": resolved,
            },
        )
        worktree = self.worktrees.create_detached(
            self.repository, run.id, "old123"
        )
        self.store.save_effect(
            run.id, "git:create_review_worktree", "completed", worktree
        )
        completed = self.engine.execute(run.id, self.project)
        self.assertEqual(completed.state, "completed")
        self.assertEqual(completed.metadata["review_target"]["commit"], "old123")
        self.assertFalse(any(call[0] == "resolve_review" for call in self.git.calls))

    def test_review_resume_from_intermediate_state_skips_normal_handlers(self):
        run = self.store.create(
            "review:feature/interrupted", "demo", "codex",
            {
                "repository": str(self.repository), "title": "Review interrupted",
                "description": "Independent review", "review_only": True,
                "review_reference": "feature/interrupted",
            },
        )
        worktree = self.worktrees.create_detached(
            self.repository, run.id, "abc123"
        )
        self.store.set_worktree(run.id, worktree["path"])
        self.store.transition(run.id, "discovery")
        self.store.transition(run.id, "stories")
        completed = self.engine.execute(run.id, self.project)
        self.assertEqual(completed.state, "completed")
        self.assertEqual([route.phase for route in self.hosts.host.routes], ["review"])
        self.assertEqual(self.tasks.calls, [])

    def test_review_resume_from_pull_request_state_has_no_delivery_effects(self):
        run = self.store.create(
            "review:feature/already-reviewed", "demo", "codex",
            {
                "repository": str(self.repository), "title": "Review complete",
                "description": "Independent review", "review_only": True,
                "review_reference": "feature/already-reviewed",
                "review": "passed",
            },
        )
        for state in (
            "discovery", "stories", "publication", "implementation",
            "verification", "review", "pull_request",
        ):
            self.store.transition(run.id, state)
        completed = self.engine.execute(run.id, self.project)
        self.assertEqual(completed.state, "completed")
        self.assertEqual(self.git.calls, [])
        self.assertEqual(self.tasks.calls, [])

    def test_completed_task_cannot_publish_again(self):
        first = self.engine.start("42", self.project, "codex")
        with self.assertRaisesRegex(RuntimeError, first.id):
            self.engine.start("42", self.project, "codex")

    def test_expired_execution_is_recovered_without_new_run(self):
        original = self.store.create("42", "demo", "codex")
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE task_locks SET expires_at = ? WHERE run_id = ?",
                ("2000-01-01T00:00:00+00:00", original.id),
            )
        recovered = self.engine.start("42", self.project, "codex")
        self.assertEqual(recovered.id, original.id)
        self.assertEqual(recovered.state, "completed")
        self.assertTrue(any(
            event["kind"] == "run.recovered"
            for event in self.store.events(original.id)
        ))

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
            self.tasks, self.git, self.hosts, worktrees=self.worktrees,
        )
        engine.start("42", project, "codex")
        status_values = [call[4] for call in self.tasks.calls if call[0] == "status"]
        self.assertEqual(
            status_values,
            ["working", "working", "working", "working", "qa", "review", "release", "done"],
        )
        self.assertFalse(any(call[0] == "transition" for call in self.tasks.calls))

    def test_mismatched_pull_request_pauses_before_attachment(self):
        git = MismatchedPullRequestGit()
        engine = SundayEngine(
            Settings(projects={"demo": self.project}), self.store,
            self.tasks, git, self.hosts, worktrees=self.worktrees,
        )
        run = engine.start("42", self.project, "codex")
        self.assertEqual(run.state, "paused")
        self.assertEqual(run.resume_state, "pull_request")
        self.assertFalse(any(call[0] == "pr" for call in self.tasks.calls))
        self.assertIsNotNone(self.worktrees.inspect(self.repository, run.id))

    def test_zero_retention_removes_clean_worktree(self):
        settings = Settings(
            projects={"demo": self.project}, completed_worktree_retention_days=0,
        )
        engine = SundayEngine(
            settings, self.store, self.tasks, self.git, self.hosts,
            worktrees=self.worktrees,
        )
        run = engine.start("42", self.project, "codex")
        self.assertEqual(run.state, "completed")
        self.assertIsNone(self.worktrees.inspect(self.repository, run.id))

    def test_zero_retention_removes_completed_review_worktree(self):
        settings = Settings(
            projects={"demo": self.project}, completed_worktree_retention_days=0,
        )
        engine = SundayEngine(
            settings, self.store, self.tasks, self.git, self.hosts,
            worktrees=self.worktrees,
        )
        run = engine.review_only("feature/review-me", self.project, "codex")
        self.assertEqual(run.state, "completed")
        self.assertIsNone(self.worktrees.inspect(self.repository, run.id))
