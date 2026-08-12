"""Git and GitHub adapter using installed command-line clients."""

import json
from pathlib import Path
import re
import subprocess

from sunday.adapters.base import GitProviderAdapter


def run(command: list[str], repository: Path, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command, cwd=repository, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{result.stderr.strip()}")
    return result


class GitHubAdapter(GitProviderAdapter):
    def inspect_repository(self, repository: Path) -> dict:
        root = run(["git", "rev-parse", "--show-toplevel"], repository).stdout.strip()
        status = run(["git", "status", "--porcelain"], repository).stdout.splitlines()
        branch = run(["git", "branch", "--show-current"], repository).stdout.strip()
        remote = run(["git", "remote", "get-url", "origin"], repository).stdout.strip()
        branches = {
            name: run(["git", "rev-parse", "--verify", "--quiet", name], repository, False).returncode == 0
            for name in ("main", "homolog", "origin/main", "origin/homolog")
        }
        return {"root": root, "dirty": bool(status), "changes": status, "branch": branch, "remote": remote, "branches": branches}

    def create_branch(self, repository: Path, branch: str, base: str) -> dict:
        state = self.inspect_repository(repository)
        if state["dirty"]:
            raise RuntimeError(
                "Repository has local changes. Commit or stash them before Sunday starts."
            )
        run(["git", "fetch", "origin", base], repository)
        exists = run(["git", "rev-parse", "--verify", "--quiet", branch], repository, False).returncode == 0
        if exists:
            raise RuntimeError(
                f"Refusing to reuse an existing Sunday branch: {branch}"
            )
        run(["git", "switch", "-c", branch, f"origin/{base}"], repository)
        return {
            "path": str(repository.resolve()), "branch": branch,
            "base": base, "existing": exists, "mode": "checkout",
        }

    def inspect_branch(
        self, repository: Path, branch: str, base: str | None = None,
    ) -> dict | None:
        state = self.inspect_repository(repository)
        if state["branch"] != branch:
            return None
        return {
            "path": str(repository.resolve()), "branch": branch,
            "base": base, "existing": True, "mode": "checkout",
        }

    def checkout_revision(self, repository: Path, revision: str) -> dict:
        state = self.inspect_repository(repository)
        if state["dirty"]:
            raise RuntimeError(
                "Repository has local changes. Commit or stash them before Sunday reviews."
            )
        original_branch = state["branch"] or None
        original_head = self.inspect_head(repository)
        run(["git", "switch", "--detach", revision], repository)
        return {
            "path": str(repository.resolve()), "head": revision,
            "revision": revision, "detached": "true", "mode": "checkout",
            "original_branch": original_branch, "original_head": original_head,
        }

    def inspect_revision(self, repository: Path, revision: str) -> dict | None:
        state = self.inspect_repository(repository)
        head = self.inspect_head(repository)
        if state["branch"] or head != revision:
            return None
        return {
            "path": str(repository.resolve()), "head": head,
            "revision": revision, "detached": "true", "mode": "checkout",
        }

    def restore_checkout(
        self, repository: Path, branch: str | None, revision: str,
    ) -> dict:
        state = self.inspect_repository(repository)
        if state["dirty"]:
            raise RuntimeError("Review left local changes; refusing to switch checkout")
        if branch:
            run(["git", "switch", branch], repository)
        else:
            run(["git", "switch", "--detach", revision], repository)
        return {
            "path": str(repository.resolve()), "restored": True,
            "branch": branch, "head": self.inspect_head(repository),
        }

    def inspect_restored_checkout(
        self, repository: Path, branch: str | None, revision: str,
    ) -> dict | None:
        state = self.inspect_repository(repository)
        head = self.inspect_head(repository)
        if branch:
            if state["branch"] != branch or head != revision:
                return None
        elif state["branch"] or head != revision:
            return None
        return {
            "path": str(repository.resolve()), "restored": True,
            "branch": branch, "head": head, "reconciled": True,
        }

    def commit(self, repository: Path, message: str) -> dict:
        root = Path(run(["git", "rev-parse", "--show-toplevel"], repository).stdout.strip()).resolve()
        if root != repository.resolve():
            raise RuntimeError("Commits must run from the Sunday worktree root")
        paths: set[str] = set()
        for command in (
            ["git", "diff", "--name-only", "-z"],
            ["git", "diff", "--cached", "--name-only", "-z"],
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        ):
            paths.update(filter(None, run(command, repository).stdout.split("\0")))
        if paths:
            run(["git", "add", "-A", "--", *sorted(paths)], repository)
        staged = run(["git", "diff", "--cached", "--quiet"], repository, False)
        if staged.returncode == 0:
            head = run(["git", "rev-parse", "HEAD"], repository).stdout.strip()
            return {"commit": head, "created": False}
        run(["git", "commit", "-m", message], repository)
        head = run(["git", "rev-parse", "HEAD"], repository).stdout.strip()
        return {"commit": head, "created": True}

    def inspect_head(self, repository: Path) -> str:
        return run(["git", "rev-parse", "HEAD"], repository).stdout.strip()

    def reconcile_commit(
        self, repository: Path, message: str, previous_head: str | None,
    ) -> dict | None:
        head = self.inspect_head(repository)
        subject = run(["git", "log", "-1", "--format=%s"], repository).stdout.strip()
        dirty = bool(run(["git", "status", "--porcelain"], repository).stdout.strip())
        if previous_head and head != previous_head and subject == message:
            return {"commit": head, "created": True, "reconciled": True}
        if previous_head == head and not dirty:
            return {"commit": head, "created": False, "reconciled": True}
        return None

    def publish_branch(self, repository: Path, branch: str) -> dict:
        run(["git", "push", "--set-upstream", "origin", branch], repository)
        return {"branch": branch, "published": True}

    def reconcile_published_branch(self, repository: Path, branch: str) -> dict | None:
        local = self.inspect_head(repository)
        remote = run(
            ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
            repository,
        ).stdout.strip()
        remote_head = remote.split(maxsplit=1)[0] if remote else None
        if remote_head == local:
            return {"branch": branch, "published": True, "reconciled": True}
        return None

    def open_pull_request(self, repository: Path, branch: str, base: str, title: str, body: str) -> dict:
        existing = self.find_pull_request(repository, branch, base)
        if existing:
            return {**existing, "existing": True}
        created = run(
            ["gh", "pr", "create", "--head", branch, "--base", base, "--title", title, "--body", body], repository
        )
        url = created.stdout.strip().splitlines()[-1]
        pull_request = self.inspect_pull_request(repository, url)
        self.validate_pull_request(pull_request, branch, base)
        return {**pull_request, "existing": False}

    def find_pull_request(self, repository: Path, branch: str, base: str) -> dict | None:
        result = run(
            [
                "gh", "pr", "list", "--head", branch, "--state", "open",
                "--json", "url,number,title,headRefName,baseRefName,state", "--limit", "100",
            ],
            repository,
        )
        candidates = [
            item for item in json.loads(result.stdout or "[]")
            if item.get("headRefName") == branch
        ]
        if not candidates:
            return None
        exact = [item for item in candidates if item.get("baseRefName") == base]
        if len(candidates) != 1 or len(exact) != 1:
            actual = sorted({str(item.get("baseRefName")) for item in candidates})
            raise RuntimeError(
                f"Open pull request head {branch} targets unexpected base branches: {actual}"
            )
        self.validate_pull_request(exact[0], branch, base)
        return exact[0]

    def inspect_pull_request(self, repository: Path, reference: str) -> dict:
        result = run(["gh", "pr", "view", reference, "--json", "url,number,title,headRefName,baseRefName,state"], repository)
        return json.loads(result.stdout)

    def resolve_review_reference(
        self, repository: Path, reference: str, base: str = "main",
    ) -> dict:
        """Resolve a branch or pull request to one immutable commit."""
        pull_request = run(
            [
                "gh", "pr", "view", reference, "--json",
                "url,number,title,headRefName,baseRefName,headRefOid,baseRefOid,state",
            ],
            repository,
            False,
        )
        if pull_request.returncode == 0:
            value = json.loads(pull_request.stdout)
            number = int(value["number"])
            commit = str(value.get("headRefOid") or "")
            base_commit = str(value.get("baseRefOid") or "")
            if not all(
                re.fullmatch(r"[0-9a-fA-F]{40,64}", oid)
                for oid in (commit, base_commit)
            ):
                raise RuntimeError("GitHub omitted immutable pull request commits")
            run(
                ["git", "fetch", "origin", f"refs/pull/{number}/head"],
                repository,
            )
            run(
                ["git", "fetch", "origin", f"refs/heads/{value['baseRefName']}"],
                repository,
            )
            run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], repository)
            run(["git", "cat-file", "-e", f"{base_commit}^{{commit}}"], repository)
            return {
                **value, "commit": commit, "baseCommit": base_commit,
                "kind": "pull_request",
            }

        checked = run(
            ["git", "check-ref-format", "--branch", reference], repository, False,
        )
        if checked.returncode:
            raise RuntimeError(f"Invalid review branch: {reference}")
        remote_ref = f"refs/heads/{reference}"
        base_ref = f"refs/heads/{base}"
        remote = run(
            ["git", "ls-remote", "--heads", "origin", remote_ref], repository,
        ).stdout.splitlines()
        remote_base = run(
            ["git", "ls-remote", "--heads", "origin", base_ref], repository,
        ).stdout.splitlines()
        if len(remote) != 1:
            raise RuntimeError(f"Review branch was not uniquely found: {reference}")
        if len(remote_base) != 1:
            raise RuntimeError(f"Review base was not uniquely found: {base}")
        commit = remote[0].split(maxsplit=1)[0]
        base_commit = remote_base[0].split(maxsplit=1)[0]
        run(["git", "fetch", "origin", remote_ref], repository)
        run(["git", "fetch", "origin", base_ref], repository)
        run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], repository)
        run(["git", "cat-file", "-e", f"{base_commit}^{{commit}}"], repository)
        return {
            "reference": reference, "remote_ref": remote_ref,
            "commit": commit, "baseRefName": base, "baseCommit": base_commit,
            "kind": "branch",
        }

    @staticmethod
    def validate_pull_request(pull_request: dict, branch: str, base: str) -> None:
        head = pull_request.get("headRefName")
        target = pull_request.get("baseRefName")
        if head != branch or target != base:
            raise RuntimeError(
                f"Pull request branch mismatch: expected {branch} -> {base}, got {head} -> {target}"
            )


def branch_slug(task_ref: str, title: str, run_id: str | None = None) -> str:
    task_id = str(task_ref).rstrip("/").split("/")[-1]
    words = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:45]
    run_suffix = f"-{run_id[:8]}" if run_id else ""
    return f"sunday/{task_id}{run_suffix}-{words or 'task'}"
