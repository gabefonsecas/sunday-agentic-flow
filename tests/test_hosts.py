import unittest
from unittest.mock import patch

from sunday.adapters.hosts import CommandHostAdapter, _models
from sunday.adapters.base import ExecutionResult
from sunday.routing import ModelRouter


class HostAdapterTests(unittest.TestCase):
    def test_codex_command_selects_model_and_sandbox(self):
        route = ModelRouter("codex").route("implementation")
        command, stdin = CommandHostAdapter("codex")._command(route, __import__("pathlib").Path("/repo"), False)
        self.assertTrue(stdin)
        self.assertIn(route.model, command)
        self.assertIn("workspace-write", command)

    def test_gemini_command_selects_model_and_json(self):
        route = ModelRouter("gemini").route("review")
        command, stdin = CommandHostAdapter("gemini")._command(route, __import__("pathlib").Path("/repo"), True)
        self.assertTrue(stdin)
        self.assertEqual(command[0], "gemini")
        self.assertIn(route.model, command)
        self.assertIn("json", command)

    def test_antigravity_falls_back_to_gemini_headless(self):
        route = ModelRouter("antigravity").route("discovery")
        with patch("sunday.adapters.hosts.shutil.which", side_effect=lambda value: None if value == "agy" else "/bin/gemini"):
            command, _ = CommandHostAdapter("antigravity")._command(route, __import__("pathlib").Path("/repo"), True)
        self.assertEqual(command[0], "gemini")

    def test_model_observation_parses_provider_usage(self):
        self.assertEqual(_models({"modelUsage": {"gemini-3-pro": {"tokens": 10}}}), ["gemini-3-pro"])

    def test_explicit_cli_selection_is_not_reported_as_observed(self):
        adapter = CommandHostAdapter("codex")
        route = ModelRouter("codex").route("discovery")
        result = ExecutionResult(
            True, "ok", route.model, None, True, 0.1,
            evidence={"verification_source": "explicit CLI selection"},
        )
        self.assertTrue(adapter.verify_model_used(route, result))
        self.assertIsNone(result.observed_model)
