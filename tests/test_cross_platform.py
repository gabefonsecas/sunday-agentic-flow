import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sunday.paths as paths


class CrossPlatformTests(unittest.TestCase):
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
