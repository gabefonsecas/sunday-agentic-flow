import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sunday.adapters.hosts import CommandHostAdapter, _models
from sunday.adapters.base import ExecutionResult, ModelExecution
from sunday.routing import ModelRouter


class HostAdapterTests(unittest.TestCase):
    def test_codex_command_selects_model_and_sandbox(self):
        route = ModelRouter("codex").route("implementation")
        command, stdin = CommandHostAdapter("codex")._command(route, __import__("pathlib").Path("/repo"), False)
        self.assertTrue(stdin)
        self.assertIn(route.model, command)
        self.assertIn("workspace-write", command)
        self.assertIn("--skip-git-repo-check", command)

    def test_gemini_command_selects_model_and_json(self):
        route = ModelRouter("gemini").route("review")
        command, stdin = CommandHostAdapter("gemini")._command(route, __import__("pathlib").Path("/repo"), True)
        self.assertTrue(stdin)
        self.assertEqual(command[0], "gemini")
        self.assertIn(route.model, command)
        self.assertIn("json", command)
        self.assertIn("plan", command)
        self.assertIn("--sandbox", command)

    def test_native_antigravity_uses_documented_headless_flags(self):
        route = ModelRouter("antigravity").route("discovery")
        with patch("sunday.adapters.hosts.shutil.which", return_value="/bin/agy"):
            command, stdin = CommandHostAdapter("antigravity")._command(
                route, Path("/repo"), True
            )
        self.assertFalse(stdin)
        self.assertEqual(command[:3], ["agy", "--model", route.model])
        self.assertEqual(command[-1], "-p")
        self.assertNotIn("--mode", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_native_antigravity_write_mode_is_noninteractive(self):
        route = ModelRouter("antigravity").route("implementation")
        with patch("sunday.adapters.hosts.shutil.which", return_value="/bin/agy"):
            command, stdin = CommandHostAdapter("antigravity")._command(
                route, Path("/repo"), False
            )
        self.assertFalse(stdin)
        self.assertIn("--dangerously-skip-permissions", command)
        self.assertEqual(command[-1], "-p")

    def test_non_stdin_host_receives_prompt_as_p_argument(self):
        adapter = CommandHostAdapter("antigravity")
        process = MagicMock(returncode=0)
        process.communicate.return_value = ("ok", "")
        with patch("sunday.adapters.hosts.shutil.which", return_value="/bin/agy"), patch(
            "sunday.adapters.hosts.subprocess.Popen", return_value=process
        ) as popen:
            adapter._execute(
                ["agy", "--model", "flash", "-p"], False, "inspect safely",
                Path("/repo"), "flash",
            )
        self.assertEqual(popen.call_args.args[0][-2:], ["-p", "inspect safely"])
        self.assertEqual(process.communicate.call_args.args[0], None)

    def test_gemini_write_mode_is_sandboxed_and_noninteractive(self):
        route = ModelRouter("gemini").route("implementation")
        command, _ = CommandHostAdapter("gemini")._command(
            route, Path("/repo"), False
        )
        self.assertIn("--sandbox", command)
        self.assertIn("yolo", command)

    def test_antigravity_falls_back_to_gemini_headless(self):
        route = ModelRouter("antigravity").route("discovery")
        with patch("sunday.adapters.hosts.shutil.which", side_effect=lambda value: None if value == "agy" else "/bin/gemini"):
            command, _ = CommandHostAdapter("antigravity")._command(route, __import__("pathlib").Path("/repo"), True)
        self.assertEqual(command[0], "gemini")

    def test_cross_provider_alternatives_skip_gemini_fallback_duplicate(self):
        from sunday.adapters.hosts import HostRegistry

        def available(value):
            return None if value in {"claude", "agy"} else f"/bin/{value}"
        with patch("sunday.adapters.hosts.shutil.which", side_effect=available):
            names = [adapter.name for adapter in HostRegistry().alternatives("codex")]
        self.assertEqual(names, ["gemini"])

    def test_model_observation_parses_provider_usage(self):
        self.assertEqual(_models({"modelUsage": {"gemini-3-pro": {"tokens": 10}}}), ["gemini-3-pro"])

    def test_explicit_cli_selection_does_not_confirm_model(self):
        adapter = CommandHostAdapter("codex")
        route = ModelRouter("codex").route("discovery")
        result = ExecutionResult(
            True, "ok", route.model, None, False, 0.1,
            evidence={"verification_source": "explicit CLI selection"},
        )
        self.assertFalse(adapter.verify_model_used(route, result))
        self.assertIsNone(result.observed_model)

    def test_model_execution_exposes_legacy_engine_properties(self):
        result = ModelExecution(
            requested_model="gpt-5.4",
            observed_model="gpt-5.4",
            verification_status="confirmed",
            verification_evidence={"source": "host output"},
            exit_code=0,
            duration=0.2,
            output="ok",
        )
        self.assertTrue(result.success)
        self.assertTrue(result.model_verified)
        self.assertEqual(result.duration_seconds, 0.2)
        self.assertEqual(result.evidence, {"source": "host output"})

    def test_discovery_returns_unique_configured_models(self):
        models = CommandHostAdapter("codex").discover_models()
        self.assertEqual(len(models), len(set(models)))
        self.assertIn("gpt-5.6-sol", models)

    def test_success_without_observed_model_is_requested_only(self):
        process = MagicMock(returncode=0)
        process.communicate.return_value = ('{"type":"result","value":"ok"}', "")
        with patch("sunday.adapters.hosts.shutil.which", return_value="/bin/codex"), patch(
            "sunday.adapters.hosts.subprocess.Popen", return_value=process
        ) as popen:
            result = CommandHostAdapter("codex").probe_model("gpt-5.4")
        command = popen.call_args.args[0]
        self.assertEqual(
            popen.call_args.kwargs["start_new_session"], os.name != "nt"
        )
        prompt = process.communicate.call_args.args[0]
        self.assertIn("read-only", command)
        self.assertIn("Do not inspect files", prompt)
        self.assertEqual(result.verification_status, "requested_only")
        self.assertFalse(result.model_verified)

    def test_codex_rollout_confirms_observed_model(self):
        process = MagicMock(returncode=0)
        process.communicate.return_value = (
            '{"type":"thread.started","thread_id":"thread-123"}\n'
            '{"type":"turn.completed"}',
            "",
        )
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary)
            session = codex_home / "sessions" / "2026" / "08" / "11"
            session.mkdir(parents=True)
            rollout = session / "rollout-test-thread-123.jsonl"
            rollout.write_text(json.dumps({
                "type": "turn_context", "payload": {"model": "gpt-5.4"},
            }) + "\n", encoding="utf-8")
            with patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}), patch(
                "sunday.adapters.hosts.shutil.which", return_value="/bin/codex"
            ), patch("sunday.adapters.hosts.subprocess.Popen", return_value=process):
                result = CommandHostAdapter("codex").probe_model("gpt-5.4")
        self.assertEqual(result.observed_model, "gpt-5.4")
        self.assertEqual(result.verification_status, "confirmed")
        self.assertEqual(
            result.verification_evidence["verification_source"],
            "codex rollout turn_context",
        )

    def test_observed_model_is_confirmed_or_mismatched(self):
        adapter = CommandHostAdapter("codex")
        self.assertEqual(adapter._verification_status("gpt-5.4", "gpt-5.4", 0), "confirmed")
        self.assertEqual(adapter._verification_status("gpt-5.4", "gpt-5.6-sol", 0), "mismatched")
        self.assertEqual(adapter._verification_status("gpt-5.4", "gpt-5.4-mini", 0), "mismatched")
        self.assertEqual(adapter._verification_status("gpt-5.4", "gpt-5.4", 1), "unavailable")

    def test_missing_host_marks_probe_unavailable(self):
        with patch("sunday.adapters.hosts.shutil.which", return_value=None):
            result = CommandHostAdapter("codex").probe_model("gpt-5.4")
        self.assertEqual(result.verification_status, "unavailable")
        self.assertEqual(result.exit_code, 127)
