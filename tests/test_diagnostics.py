from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from sunday.adapters.base import ModelExecution
from sunday.diagnostics import _github, _probe_models, doctor


class ProbeAdapter:
    def __init__(self, name):
        self.name = name

    def discover_models(self):
        return ["model-a", "model-b"]

    def probe_model(self, model, repository=None):
        status = "confirmed" if model == "model-a" else "requested_only"
        return ModelExecution(
            requested_model=model,
            observed_model=model if status == "confirmed" else None,
            verification_status=status,
            verification_evidence={"source": "test"},
            exit_code=0,
            duration=0.1,
            output="ok",
        )


class DiagnosticsTests(unittest.TestCase):
    def test_github_requires_attestation_capable_cli(self):
        def command(arguments):
            if arguments[1:] == ["--version"]:
                return {
                    "available": True, "path": "/bin/gh", "healthy": True,
                    "output": "gh version 2.48.0 (test)",
                }
            return {
                "available": True, "path": "/bin/gh", "healthy": True,
                "output": "ok",
            }

        with patch("sunday.diagnostics._command", side_effect=command):
            result = _github()

        self.assertEqual(result["minimum_version"], "2.49.0")
        self.assertFalse(result["supported_version"])
        self.assertFalse(result["healthy"])

    def test_github_accepts_version_249_with_attestation(self):
        def command(arguments):
            output = "gh version 2.49.0 (test)" if arguments[1:] == ["--version"] else "ok"
            return {
                "available": True, "path": "/bin/gh", "healthy": True,
                "output": output,
            }

        with patch("sunday.diagnostics._command", side_effect=command):
            result = _github()

        self.assertTrue(result["supported_version"])
        self.assertTrue(result["healthy"])

    def test_model_probe_classifies_available_hosts(self):
        hosts = {
            "codex": {"available": True},
            "claude": {"available": False},
        }
        with patch("sunday.diagnostics.CommandHostAdapter", ProbeAdapter):
            checks, summary = _probe_models(hosts)
        self.assertEqual(list(checks), ["codex"])
        self.assertEqual(
            [item["verification_status"] for item in checks["codex"]],
            ["confirmed", "requested_only"],
        )
        self.assertEqual(summary["counts"]["confirmed"], 1)
        self.assertEqual(summary["counts"]["requested_only"], 1)
        self.assertFalse(summary["healthy"])

    def test_doctor_only_runs_model_probes_when_requested(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.toml"
            environment = Path(temp) / ".env"
            database = Path(temp) / "sunday.db"
            config.touch()
            environment.touch()
            command_health = {
                "available": True, "path": "/bin/tool", "healthy": True, "output": "ok"
            }
            model_result = (
                {"codex": [{"verification_status": "confirmed"}]},
                {
                    "total": 1,
                    "counts": {
                        "confirmed": 1, "requested_only": 0,
                        "mismatched": 0, "unavailable": 0,
                    },
                    "healthy": True,
                },
            )
            patches = (
                patch("sunday.diagnostics.load_env", return_value=environment),
                patch("sunday.diagnostics.load_settings", return_value=SimpleNamespace(projects={})),
                patch("sunday.diagnostics.config_path", return_value=config),
                patch("sunday.diagnostics.env_path", return_value=environment),
                patch("sunday.diagnostics.database_path", return_value=database),
                patch("sunday.diagnostics._command", return_value=command_health),
                patch("sunday.diagnostics._probe_models", return_value=model_result),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as probe:
                quick = doctor()
                thorough = doctor(models=True)
        self.assertNotIn("models", quick)
        self.assertEqual(thorough["models"], model_result[0])
        self.assertTrue(thorough["model_verification"]["healthy"])
        probe.assert_called_once()

    def test_doctor_is_unhealthy_when_github_cli_is_outdated(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.toml"
            environment = Path(temp) / ".env"
            config.touch()
            environment.touch()
            command_health = {
                "available": True, "path": "/bin/tool", "healthy": True,
                "output": "ok",
            }
            github_health = {
                **command_health,
                "healthy": False,
                "version": "2.48.0",
                "minimum_version": "2.49.0",
                "supported_version": False,
            }
            with patch("sunday.diagnostics.load_env", return_value=environment), patch(
                "sunday.diagnostics.load_settings",
                return_value=SimpleNamespace(projects={}),
            ), patch("sunday.diagnostics.config_path", return_value=config), patch(
                "sunday.diagnostics.env_path", return_value=environment
            ), patch("sunday.diagnostics.database_path", return_value=Path(temp) / "sunday.db"), patch(
                "sunday.diagnostics._command", return_value=command_health
            ), patch("sunday.diagnostics._github", return_value=github_health):
                result = doctor()

        self.assertFalse(result["healthy"])
        self.assertEqual(result["github"]["minimum_version"], "2.49.0")


if __name__ == "__main__":
    unittest.main()
