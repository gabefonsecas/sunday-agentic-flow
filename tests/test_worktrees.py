import subprocess
import tempfile
from pathlib import Path
import unittest

from sunday.adapters.github import GitHubAdapter
from sunday.state import RunStore
from sunday.worktrees import WorktreeManager, cleanup_worktrees


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repository, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


class WorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "seed"
        self.repository = self.root / "repository"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        self.seed.mkdir()
        git(self.seed, "init", "-b", "main")
        git(self.seed, "config", "user.email", "sunday@example.test")
        git(self.seed, "config", "user.name", "Sunday Test")
        (self.seed / "README.md").write_text("seed\n", encoding="utf-8")
        git(self.seed, "add", "README.md")
        git(self.seed, "commit", "-m", "seed")
        git(self.seed, "remote", "add", "origin", str(self.remote))
        git(self.seed, "push", "-u", "origin", "main")
        subprocess.run(
            ["git", "clone", "-b", "main", str(self.remote), str(self.repository)],
            check=True, capture_output=True,
        )
        git(self.repository, "config", "user.email", "sunday@example.test")
        git(self.repository, "config", "user.name", "Sunday Test")
        self.store = RunStore(self.root / "state" / "sunday.db")
        self.manager = WorktreeManager(self.store.path.parent / "worktrees")

    def tearDown(self):
        self.temp.cleanup()

    def test_commit_only_stages_changes_inside_worktree(self):
        created = self.manager.create(
            self.repository, "run-1", "sunday/42-isolated", "main"
        )
        worktree = Path(created["path"])
        (self.repository / "root-only.txt").write_text("private\n", encoding="utf-8")
        (worktree / "feature.txt").write_text("isolated\n", encoding="utf-8")

        commit = GitHubAdapter().commit(worktree, "feat: isolated")

        self.assertTrue(commit["created"])
        self.assertEqual(git(worktree, "show", "--pretty=", "--name-only", "HEAD"), "feature.txt")
        self.assertIn("root-only.txt", git(self.repository, "status", "--porcelain"))

    def test_safe_remove_refuses_dirty_worktree(self):
        created = self.manager.create(
            self.repository, "run-2", "sunday/43-dirty", "main"
        )
        worktree = Path(created["path"])
        (worktree / "unfinished.txt").write_text("keep\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "dirty Sunday worktree"):
            self.manager.remove(self.repository, "run-2", "sunday/43-dirty")
        self.assertTrue(worktree.is_dir())

    def test_existing_unregistered_branch_is_never_reused(self):
        git(self.repository, "branch", "sunday/44-existing", "main")
        with self.assertRaisesRegex(RuntimeError, "Refusing to reuse"):
            self.manager.create(
                self.repository, "run-44", "sunday/44-existing", "main"
            )

    def test_review_worktree_is_detached_at_exact_revision(self):
        revision = git(self.repository, "rev-parse", "HEAD")
        created = self.manager.create_detached(
            self.repository, "review-1", revision
        )
        self.assertEqual(created["head"], revision)
        self.assertEqual(created["detached"], "true")
        self.assertEqual(git(Path(created["path"]), "rev-parse", "HEAD"), revision)

    def test_safe_remove_preserves_ignored_artifacts(self):
        created = self.manager.create(
            self.repository, "run-ignored", "sunday/45-ignored", "main"
        )
        worktree = Path(created["path"])
        (worktree / ".gitignore").write_text("artifact.bin\n", encoding="utf-8")
        git(worktree, "add", ".gitignore")
        git(worktree, "commit", "-m", "test: ignore artifact")
        (worktree / "artifact.bin").write_text("preserve\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "dirty Sunday worktree"):
            self.manager.remove(
                self.repository, "run-ignored", "sunday/45-ignored"
            )
        self.assertTrue((worktree / "artifact.bin").is_file())

    def test_cleanup_filters_completed_runs(self):
        completed = self.store.create(
            "42", "demo", "codex", {"repository": str(self.repository)}
        )
        created = self.manager.create(
            self.repository, completed.id, "sunday/42-clean", "main"
        )
        self.store.set_worktree(completed.id, created["path"])
        self.store.update_metadata(completed.id, {"branch": "sunday/42-clean"})
        for state in (
            "discovery", "stories", "publication", "implementation", "verification",
            "review", "pull_request", "completed",
        ):
            self.store.transition(completed.id, state)

        result = cleanup_worktrees(self.store, run_id=completed.id)

        self.assertEqual([item["run_id"] for item in result["removed"]], [completed.id])
        self.assertFalse(Path(created["path"]).exists())

    def test_cleanup_preserves_paused_runs(self):
        paused = self.store.create(
            "43", "demo", "codex", {"repository": str(self.repository)}
        )
        created = self.manager.create(
            self.repository, paused.id, "sunday/43-paused", "main"
        )
        self.store.set_worktree(paused.id, created["path"])
        self.store.update_metadata(paused.id, {"branch": "sunday/43-paused"})
        self.store.transition(paused.id, "paused")

        result = cleanup_worktrees(self.store, run_id=paused.id)

        self.assertEqual(result["preserved"][0]["reason"], "run_paused")
        self.assertTrue(Path(created["path"]).is_dir())
