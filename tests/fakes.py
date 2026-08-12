from sunday.adapters.base import ExecutionResult


class FakeTasks:
    def __init__(self, title="Safe task"):
        self.task = {"id": 42, "name": title, "description": "Deliver tested behavior", "tags": [{"name": "sunday-ready"}]}
        self.calls = []
        self.created = []

    def authenticate(self): return {"authenticated": True}
    def get_current_user(self, workspace_id): return {"id": 7, "email": "user@example.com"}
    def get_task(self, task_ref, board_id=None): return self.task
    def list_ready_tasks(self, label, board_id=None, completed_status=""):
        return [self.task]
    def claim_task(self, task, workspace_id, board_id, people_column=""):
        self.calls.append(("claim", task["id"]))
        return {"assigned": True, "member_id": 7, "member_email": "user@example.com", "identity_source": "token"}
    def create_story(self, story, board_id, group_id):
        self.calls.append(("story", story["title"]))
        item = {**story, "id": 100 + len(self.calls)}
        self.created.append(item)
        return item
    def find_story(self, marker, group_id):
        return next((item for item in self.created if marker in item["description"]), None)
    def transition(self, item_id, group_id):
        self.calls.append(("transition", item_id, group_id))
        return {"moved": True}
    def set_status(self, item_id, board_id, column, value):
        self.calls.append(("status", item_id, board_id, column, value))
        return {"updated": True}
    def mark_ai(self, item_id, board_id, column):
        self.calls.append(("ai", item_id, board_id, column))
        return {"updated": True}
    def comment(self, item_id, text):
        self.calls.append(("comment", item_id, text))
        return {"commented": True}
    def attach_pull_request(self, item_id, board_id, url, column=""):
        self.calls.append(("pr", item_id, url))
        return {"attached": True}


class FakeGit:
    def __init__(self):
        self.calls = []

    def inspect_repository(self, repository):
        return {
            "root": str(repository), "dirty": False, "changes": [], "branch": "main",
            "remote": "git@example/repo", "branches": {"main": True, "homolog": True, "origin/main": True, "origin/homolog": True},
        }
    def inspect_head(self, repository): return "base123"
    def create_branch(self, repository, branch, base):
        self.calls.append(("branch", branch, base))
        return {"path": str(repository), "branch": branch, "base": base, "mode": "checkout"}
    def inspect_branch(self, repository, branch, base=None):
        return {"path": str(repository), "branch": branch, "base": base, "mode": "checkout"}
    def checkout_revision(self, repository, revision):
        self.calls.append(("checkout_revision", revision))
        return {
            "path": str(repository), "head": revision, "revision": revision,
            "detached": "true", "mode": "checkout", "original_branch": "main",
            "original_head": "base123",
        }
    def inspect_revision(self, repository, revision):
        return {"path": str(repository), "head": revision, "revision": revision, "detached": "true"}
    def restore_checkout(self, repository, branch, revision):
        self.calls.append(("restore_checkout", branch, revision))
        return {"path": str(repository), "restored": True, "branch": branch, "head": revision}
    def inspect_restored_checkout(self, repository, branch, revision):
        return {"path": str(repository), "restored": True, "branch": branch, "head": revision, "reconciled": True}
    def commit(self, repository, message):
        self.calls.append(("commit", message))
        return {"commit": "abc123", "created": True}
    def publish_branch(self, repository, branch):
        self.calls.append(("push", branch))
        return {"published": True}
    def open_pull_request(self, repository, branch, base, title, body):
        self.calls.append(("open_pr", branch, base))
        return {
            "url": "https://github.test/pr/1", "headRefName": branch,
            "baseRefName": base,
        }
    def find_pull_request(self, repository, branch, base): return None
    def inspect_pull_request(self, repository, reference):
        call = next(call for call in reversed(self.calls) if call[0] == "open_pr")
        return {"url": reference, "headRefName": call[1], "baseRefName": call[2]}
    def resolve_review_reference(self, repository, reference, base="main"):
        self.calls.append(("resolve_review", reference))
        return {
            "reference": reference, "commit": "abc123", "kind": "branch",
            "headRefName": reference, "baseRefName": base, "baseCommit": "base123",
        }


class FakeWorktrees:
    def __init__(self, root):
        self.root = root
        self.items = {}
        self.calls = []

    def create(self, repository, run_id, branch, base):
        path = self.root / run_id
        value = {"path": str(path), "branch": branch, "base": base, "existing": False}
        self.items[run_id] = value
        self.calls.append(("create", run_id, branch, base))
        return value

    def inspect(self, repository, run_id, branch=None):
        return self.items.get(run_id)

    def create_detached(self, repository, run_id, revision):
        path = self.root / run_id
        value = {
            "path": str(path), "head": revision, "revision": revision,
            "detached": "true", "existing": False,
        }
        self.items[run_id] = value
        self.calls.append(("create_detached", run_id, revision))
        return value

    def remove(self, repository, run_id, branch=None):
        value = self.items.pop(run_id, None)
        self.calls.append(("remove", run_id, branch))
        return {"path": value["path"] if value else str(self.root / run_id), "removed": True}


class FakeHost:
    name = "codex"

    def __init__(self):
        self.routes = []
        self.repositories = []

    def capabilities(self): return {"available": True}
    def execute_agent(self, route, prompt, repository, read_only):
        self.routes.append(route)
        self.repositories.append(repository)
        stories = ''
        if route.phase == "discovery":
            stories = 'SUNDAY_STORIES: [{"title":"[dev] outcome","description":"complete story"}]\n'
        output = stories + 'SUNDAY_RESULT: {"success": true, "confidence": 0.95, "summary": "passed"}'
        return ExecutionResult(True, output, route.model, route.model, True, 0.1, 0.95, {"fake": True})
    def verify_model_used(self, route, result): return result.observed_model == route.model
    def cancel(self): pass


class FakeHosts:
    def __init__(self): self.host = FakeHost()
    def detect(self, preferred="auto"): return self.host
    def alternatives(self, current): return []
