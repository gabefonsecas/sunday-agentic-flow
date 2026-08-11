import json
from pathlib import Path
import unittest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parent.parent


class VersionTests(unittest.TestCase):
    def test_all_manifests_share_version(self):
        expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        paths = (ROOT / ".codex-plugin" / "plugin.json", ROOT / ".claude-plugin" / "plugin.json", ROOT / "gemini-extension.json")
        for path in paths:
            value = json.loads(path.read_text(encoding="utf-8"))["version"].split("+", 1)[0]
            self.assertEqual(value, expected, path)
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["version"], expected)

    def test_plugin_identifiers_use_sunday(self):
        manifests = (ROOT / ".codex-plugin" / "plugin.json", ROOT / ".claude-plugin" / "plugin.json", ROOT / "gemini-extension.json")
        for path in manifests:
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["name"], "sunday-agentic-flow")
