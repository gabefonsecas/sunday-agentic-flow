import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sunday.installation as installation


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.patches = (
            patch.object(Path, "home", return_value=self.home),
            patch.object(installation, "config_dir", return_value=self.home / ".config" / "sunday"),
            patch.object(installation, "bin_dir", return_value=self.home / ".local" / "bin"),
        )
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_install_and_uninstall_managed_files(self):
        result = installation.install()
        self.assertTrue(result["installed"])
        launcher = "sunday.cmd" if os.name == "nt" else "sunday"
        self.assertTrue((self.home / ".local" / "bin" / launcher).is_file())
        self.assertTrue((self.home / ".config" / "sunday" / "config.toml").is_file())
        marketplace = json.loads((self.home / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(marketplace["plugins"][0]["name"], "sunday-agentic-flow")
        removed = installation.uninstall()
        self.assertTrue(removed["uninstalled"])
        self.assertFalse((self.home / ".local" / "bin" / launcher).exists())
        self.assertTrue((self.home / ".config" / "sunday" / ".env").exists())

    def test_install_rolls_back_when_marketplace_fails(self):
        with patch.object(installation, "_marketplace", side_effect=RuntimeError("broken")):
            with self.assertRaisesRegex(RuntimeError, "broken"):
                installation.install()
        launcher = "sunday.cmd" if os.name == "nt" else "sunday"
        self.assertFalse((self.home / ".local" / "bin" / launcher).exists())
