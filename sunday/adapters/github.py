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
        run(["git", "fetch", "origin", base], repository)
        exists = run(["git", "rev-parse", "--verify", "--quiet", branch], repository, False).returncode == 0
        run(["git", "switch", branch] if exists else ["git", "switch", "-c", branch, f"origin/{base}"], repository)
        return {"branch": branch, "base": base, "existing": exists}

    def commit(self, repository: Path, message: str) -> dict:
        run(["git", "add", "--all"], repository)
        staged = run(["git", "diff", "--cached", "--quiet"], repository, False)
        if staged.returncode == 0:
            head = run(["git", "rev-parse", "HEAD"], repository).stdout.strip()
            return {"commit": head, "created": False}
        run(["git", "commit", "-m", message], repository)
        head = run(["git", "rev-parse", "HEAD"], repository).stdout.strip()
        return {"commit": head, "created": True}

    def publish_branch(self, repository: Path, branch: str) -> dict:
        run(["git", "push", "--set-upstream", "origin", branch], repository)
        return {"branch": branch, "published": True}

    def open_pull_request(self, repository: Path, branch: str, base: str, title: str, body: str) -> dict:
        existing = run(
            ["gh", "pr", "list", "--head", branch, "--json", "url,number", "--limit", "1"], repository
        )
        matches = json.loads(existing.stdout or "[]")
        if matches:
            return {**matches[0], "existing": True}
        created = run(
            ["gh", "pr", "create", "--head", branch, "--base", base, "--title", title, "--body", body], repository
        )
        url = created.stdout.strip().splitlines()[-1]
        return {"url": url, "existing": False}

    def inspect_pull_request(self, repository: Path, reference: str) -> dict:
        result = run(["gh", "pr", "view", reference, "--json", "url,number,title,headRefName,baseRefName,state"], repository)
        return json.loads(result.stdout)


def branch_slug(task_ref: str, title: str) -> str:
    task_id = str(task_ref).rstrip("/").split("/")[-1]
    words = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:45]
    return f"sunday/{task_id}-{words or 'task'}"
