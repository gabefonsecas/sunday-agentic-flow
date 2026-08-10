import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from sunday.config import load_settings
from sunday.security import redact


class ConfigSecurityTests(unittest.TestCase):
    def test_project_configuration_loads(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text('''[runtime]\ndefault_host="claude"\n[projects.app]\nrepository="."\nworkspace_id=1\nboard_id=2\nintake_group_id=3\n[projects.app.states]\ncompleted=9\n''', encoding="utf-8")
            settings = load_settings(path)
        self.assertEqual(settings.default_host, "claude")
        self.assertEqual(settings.projects["app"].states["completed"], 9)

    def test_tokens_and_query_strings_are_redacted(self):
        with patch.dict(os.environ, {"FRIDAY_MCP_API_TOKEN": "super-secret-token"}, clear=False):
            value = redact({"url": "https://test/?api_token=super-secret-token", "api_token": "raw"})
        self.assertNotIn("super-secret-token", str(value))
        self.assertEqual(value["api_token"], "[REDACTED]")
