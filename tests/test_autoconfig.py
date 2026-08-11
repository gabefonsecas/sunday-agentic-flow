import json
from pathlib import Path
import tempfile
import unittest

from sunday.adapters.base import ExecutionResult
from sunday.autoconfig import AutoConfigurationService, needs_configuration
from sunday.config import ProjectConfig, Settings, load_settings


class CatalogClient:
    def tool(self, name, arguments=None):
        if name == "list_workspaces":
            return [{"id": 37, "name": "Aqui Ads"}]
        if name == "list_boards":
            return [{"id": 46, "name": "Squad Mustafar", "workspace_id": 37}]
        if name == "list_groups":
            return [{"id": 90, "name": "Desenvolvimento", "board_id": 46}]
        if name == "list_columns":
            return [
                {"id": 200, "name": "Responsável", "type": "people"},
                {"id": 298, "name": "IA", "type": "checkbox"},
                {
                    "id": 201, "name": "Status", "type": "status",
                    "settings": {"options": [
                        {"id": "working", "label": "Development"},
                        {"id": "qa", "label": "QA"},
                        {"id": "review", "label": "Review Pull Request"},
                        {"id": "release", "label": "Release Candidate"},
                        {"id": "done", "label": "Done"},
                        {"id": "stuck", "label": "Blocked"},
                    ]},
                },
            ]
        raise AssertionError(name)


class ConfigHost:
    name = "codex"

    def __init__(self, status="working"):
        self.status = status

    def execute_agent(self, route, prompt, repository, read_only):
        states = {
            "discovery": self.status, "stories": self.status,
            "publication": self.status, "implementation": self.status,
            "verification": "qa", "review": "review", "pull_request": "release",
            "completed": "done", "failed": "stuck",
        }
        config = {
            "workspace_id": 37, "board_id": 46, "intake_group_id": 90,
            "people_column": "200", "status_column": "201", "pr_column": "",
            "ai_column": "298",
            "states": states,
        }
        output = "SUNDAY_CONFIG: " + json.dumps(config)
        return ExecutionResult(True, output, route.model, route.model, True, 0.1, 0.95, {})

    def verify_model_used(self, route, result):
        return True


class ConfigHosts:
    def __init__(self, host=None):
        self.host = host or ConfigHost()

    def detect(self, preferred="auto"):
        return self.host


class AutoConfigurationTests(unittest.TestCase):
    def test_first_run_ai_configuration_is_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "smb-products"
            root.mkdir()
            destination = Path(temp) / "config.toml"
            settings = Settings(projects={
                "example": ProjectConfig("example", root, workspace_id=0, board_id=0)
            })
            project = AutoConfigurationService(
                settings, CatalogClient(), ConfigHosts()
            ).configure(root, "corrigir login", "auto", destination)
            loaded = load_settings(destination).projects["smb-products"]
        self.assertEqual(project.board_id, 46)
        self.assertEqual(loaded.status_column, "201")
        self.assertEqual(loaded.ai_column, "298")
        self.assertEqual(loaded.states["verification"], "qa")
        self.assertFalse(needs_configuration(loaded))

    def test_ai_cannot_invent_status_options(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            service = AutoConfigurationService(
                Settings(max_phase_attempts=1), CatalogClient(), ConfigHosts(ConfigHost("invented"))
            )
            with self.assertRaisesRegex(RuntimeError, "invented Friday status"):
                service.configure(root, "task", "auto", Path(temp) / "config.toml")


if __name__ == "__main__":
    unittest.main()
