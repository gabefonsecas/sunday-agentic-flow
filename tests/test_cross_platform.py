import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sunday.paths as paths


class CrossPlatformTests(unittest.TestCase):
    def test_relative_installation_override_is_resolved(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"SUNDAY_INSTALL_DIR": "relative-sunday"}, clear=False
        ), patch.object(Path, "cwd", return_value=Path(temp)):
            with patch("os.getcwd", return_value=temp):
                result = paths.installation_dir()
        self.assertTrue(result.is_absolute())

    def test_wsl_uses_posix_configuration(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(paths, "_is_windows", return_value=False), patch.dict(
            os.environ, {"HOME": temp, "WSL_DISTRO_NAME": "Ubuntu", "XDG_CONFIG_HOME": str(Path(temp) / "config")}, clear=False
        ):
            self.assertEqual(paths.config_dir(), Path(temp) / "config" / "sunday")

    def test_windows_uses_appdata(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(paths, "_is_windows", return_value=True), patch.dict(
            os.environ, {"APPDATA": str(Path(temp) / "Roaming")}, clear=False
        ):
            self.assertEqual(paths.config_dir(), Path(temp) / "Roaming" / "sunday")

    def test_windows_launcher_uses_standard_user_path(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            paths, "_is_windows", return_value=True
        ), patch.dict(
            os.environ, {"LOCALAPPDATA": str(Path(temp) / "Local")}, clear=False
        ):
            self.assertEqual(
                paths.bin_dir(),
                Path(temp) / "Local" / "sunday" / "bin",
            )
