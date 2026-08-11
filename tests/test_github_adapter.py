import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from sunday.adapters.github import GitHubAdapter


def completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


class GitHubAdapterTests(unittest.TestCase):
    def test_review_pull_request_is_fetched_at_observed_head(self):
        head = "a" * 40
        base = "c" * 40
        pull_request = {
            "url": "https://github.test/pr/7", "number": 7,
            "headRefName": "feature", "baseRefName": "main",
            "headRefOid": head, "baseRefOid": base, "state": "OPEN",
        }
        responses = [
            completed(json.dumps(pull_request)), completed(""), completed(""),
            completed(""), completed(""),
        ]
        with patch("sunday.adapters.github.run", side_effect=responses) as invoked:
            resolved = GitHubAdapter().resolve_review_reference(Path("."), "7")
        self.assertEqual(resolved["commit"], head)
        self.assertEqual(resolved["baseCommit"], base)
        self.assertEqual(resolved["kind"], "pull_request")
        self.assertIn("refs/pull/7/head", invoked.call_args_list[1].args[0])

    def test_review_branch_uses_remote_oid_not_shared_fetch_head(self):
        head = "b" * 40
        base = "d" * 40
        responses = [
            subprocess.CompletedProcess([], 1, stdout="", stderr="not a PR"),
            completed("feature/safe\n"),
            completed(f"{head}\trefs/heads/feature/safe\n"),
            completed(f"{base}\trefs/heads/main\n"),
            completed(""), completed(""), completed(""), completed(""),
        ]
        with patch("sunday.adapters.github.run", side_effect=responses) as invoked:
            resolved = GitHubAdapter().resolve_review_reference(
                Path("."), "feature/safe"
            )
        self.assertEqual(resolved["commit"], head)
        self.assertEqual(resolved["baseCommit"], base)
        commands = [call.args[0] for call in invoked.call_args_list]
        self.assertFalse(any("FETCH_HEAD" in command for command in commands))
        self.assertTrue(any(f"{head}^{{commit}}" in command for command in commands))
        self.assertTrue(any(f"{base}^{{commit}}" in command for command in commands))

    def test_existing_pull_request_must_match_base(self):
        pull_request = {
            "url": "https://github.test/pr/1", "number": 1,
            "headRefName": "sunday/42-fix", "baseRefName": "homolog",
            "state": "OPEN",
        }
        with patch(
            "sunday.adapters.github.run",
            return_value=completed(json.dumps([pull_request])),
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected base"):
                GitHubAdapter().open_pull_request(
                    Path("."), "sunday/42-fix", "main", "Fix", "Body"
                )

    def test_created_pull_request_is_inspected_strictly(self):
        mismatched = {
            "url": "https://github.test/pr/2", "number": 2,
            "headRefName": "other-branch", "baseRefName": "main",
            "state": "OPEN",
        }
        responses = [
            completed("[]"), completed("https://github.test/pr/2\n"),
            completed(json.dumps(mismatched)),
        ]
        with patch("sunday.adapters.github.run", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "branch mismatch"):
                GitHubAdapter().open_pull_request(
                    Path("."), "sunday/42-fix", "main", "Fix", "Body"
                )
