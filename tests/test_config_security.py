import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from sunday.config import ProjectConfig, Settings, load_settings
from sunday.security import redact


class ConfigSecurityTests(unittest.TestCase):
    def test_project_configuration_loads(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text('''[runtime]\ndefault_host="claude"\n[projects.app]\nrepository="."\nworkspace_id=1\nboard_id=2\nintake_group_id=3\n[projects.app.states]\ncompleted=9\n''', encoding="utf-8")
            settings = load_settings(path)
        self.assertEqual(settings.default_host, "claude")
        self.assertEqual(settings.projects["app"].states["completed"], 9)

    def test_reliability_runtime_configuration_loads(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text(
                '[runtime]\nlease_ttl_seconds=90\nlease_heartbeat_seconds=20\n'
                'completed_worktree_retention_days=14\n',
                encoding="utf-8",
            )
            settings = load_settings(path)
        self.assertEqual(settings.lease_ttl_seconds, 90)
        self.assertEqual(settings.lease_heartbeat_seconds, 20)
        self.assertEqual(settings.completed_worktree_retention_days, 14)

    def test_status_values_can_be_strings(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text('''[projects.app]\nrepository="."\nstatus_column="201"\n[projects.app.states]\nimplementation="working"\nfailed="stuck"\n''', encoding="utf-8")
            project = load_settings(path).projects["app"]
        self.assertEqual(project.status_column, "201")
        self.assertEqual(project.states["implementation"], "working")

    def test_tokens_and_query_strings_are_redacted(self):
        with patch.dict(os.environ, {"FRIDAY_MCP_API_TOKEN": "super-secret-token"}, clear=False):
            value = redact({"url": "https://test/?api_token=super-secret-token", "api_token": "raw"})
        self.assertNotIn("super-secret-token", str(value))
        self.assertEqual(value["api_token"], "[REDACTED]")

    def test_authenticated_headers_are_redacted(self):
        value = redact({"Authorization": "Bearer visible", "Cookie": "session=visible"})
        self.assertEqual(value["Authorization"], "[REDACTED]")
        self.assertEqual(value["Cookie"], "[REDACTED]")

    def test_current_git_repository_becomes_implicit_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "smb-products"
            nested = root / "src" / "api"
            nested.mkdir(parents=True)
            (root / ".git").mkdir()
            template = ProjectConfig(
                name="template", repository=Path(temp) / "other",
                workspace_id=1, board_id=2, intake_group_id=3,
            )
            project = Settings(projects={"template": template}).project_for(None, nested)
        self.assertEqual(project.name, "smb-products")
        self.assertEqual(project.repository, root.resolve())
        self.assertEqual(project.board_id, 2)

    def test_default_project_maps_new_repository_without_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "new-service"
            root.mkdir()
            (root / ".git").mkdir()
            settings = Settings(
                default_project="shared",
                projects={
                    "shared": ProjectConfig("shared", Path(temp) / "one", board_id=9),
                    "other": ProjectConfig("other", Path(temp) / "two", board_id=10),
                },
            )
            project = settings.project_for(None, root)
        self.assertEqual(project.name, "new-service")
        self.assertEqual(project.board_id, 9)
