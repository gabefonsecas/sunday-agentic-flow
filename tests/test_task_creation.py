import tempfile
from pathlib import Path
import unittest

from sunday.config import ProjectConfig, Settings
from sunday.state import RunStore
from sunday.task_creation import TaskCreationService, parse_tasks
from tests.fakes import FakeHosts, FakeTasks


class FlakyAssignmentTasks(FakeTasks):
    def __init__(self):
        super().__init__()
        self.fail_once = True

    def claim_task(self, task, workspace_id, board_id, people_column=""):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary Friday assignment failure")
        return super().claim_task(task, workspace_id, board_id, people_column)


class TaskCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = Path(self.temp.name) / "smb-products"
        self.repository.mkdir()
        self.project = ProjectConfig(
            name="smb-products", repository=self.repository,
            workspace_id=1, board_id=2, intake_group_id=3,
        )
        self.tasks = FakeTasks()
        self.store = RunStore(Path(self.temp.name) / "state.db")
        self.service = TaskCreationService(
            Settings(strict_model_verification=True), self.store, self.tasks, FakeHosts()
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_creates_and_assigns_task_to_token_user(self):
        result = self.service.create("corrigir o login", self.project)
        self.assertEqual(result["project"], "smb-products")
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["assignment"]["member_id"], 7)
        self.assertEqual([call[0] for call in self.tasks.calls], ["story", "claim"])

    def test_repeated_request_returns_prior_result_without_duplicate(self):
        first = self.service.create("corrigir o login", self.project)
        second = self.service.create("corrigir o login", self.project)
        self.assertEqual(first["tasks"][0]["id"], second["tasks"][0]["id"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual([call[0] for call in self.tasks.calls].count("story"), 1)

    def test_retry_reconciles_marker_after_partial_failure(self):
        tasks = FlakyAssignmentTasks()
        service = TaskCreationService(
            Settings(strict_model_verification=True), self.store, tasks, FakeHosts()
        )
        with self.assertRaisesRegex(RuntimeError, "temporary Friday"):
            service.create("corrigir o login", self.project)
        result = service.create("corrigir o login", self.project)
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual([call[0] for call in tasks.calls].count("story"), 1)

    def test_count_is_respected_when_host_output_is_not_structured(self):
        result = self.service.create("separar a entrega", self.project, count=3)
        self.assertEqual(len(result["tasks"]), 3)

    def test_missing_friday_mapping_fails_before_host_or_remote_call(self):
        project = ProjectConfig(name="bare", repository=self.repository)
        with self.assertRaisesRegex(RuntimeError, "Friday mapping"):
            self.service.create("fazer algo", project)
        self.assertEqual(self.tasks.calls, [])

    def test_parser_accepts_exact_structured_tasks(self):
        output = 'SUNDAY_TASKS: [{"title":"A","description":"B"}]'
        self.assertEqual(parse_tasks(output, "fallback", self.project, 1)[0]["title"], "A")

    def test_parser_reads_marker_nested_in_host_json(self):
        output = '{"item":{"text":"SUNDAY_TASKS: [{\\"title\\":\\"A\\",\\"description\\":\\"B\\"}]"}}'
        self.assertEqual(parse_tasks(output, "fallback", self.project, 1)[0]["title"], "A")


if __name__ == "__main__":
    unittest.main()
