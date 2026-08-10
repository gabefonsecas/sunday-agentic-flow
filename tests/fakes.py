from sunday.adapters.base import ExecutionResult


class FakeTasks:
    def __init__(self, title="Safe task"):
        self.task = {"id": 42, "name": title, "description": "Deliver tested behavior", "tags": [{"name": "sunday-ready"}]}
        self.calls = []

    def authenticate(self): return {"authenticated": True}
    def get_current_user(self, workspace_id): return {"id": 7, "email": "user@example.com"}
    def get_task(self, task_ref, board_id=None): return self.task
    def list_ready_tasks(self, label): return [self.task]
    def claim_task(self, task, workspace_id, board_id, people_column=""):
        self.calls.append(("claim", task["id"]))
        return {"assigned": True, "member_id": 7, "member_email": "user@example.com", "identity_source": "token"}
    def create_story(self, story, board_id, group_id):
        self.calls.append(("story", story["title"]))
        return {"id": 100 + len(self.calls)}
    def transition(self, item_id, group_id):
        self.calls.append(("transition", item_id, group_id))
        return {"moved": True}
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
    def create_branch(self, repository, branch, base):
        self.calls.append(("branch", branch, base))
        return {"branch": branch, "base": base}
    def commit(self, repository, message):
        self.calls.append(("commit", message))
        return {"commit": "abc123", "created": True}
    def publish_branch(self, repository, branch):
        self.calls.append(("push", branch))
        return {"published": True}
    def open_pull_request(self, repository, branch, base, title, body):
        self.calls.append(("open_pr", branch, base))
        return {"url": "https://github.test/pr/1"}
    def inspect_pull_request(self, repository, reference): return {"url": reference}


class FakeHost:
    name = "codex"

    def __init__(self):
        self.routes = []

    def capabilities(self): return {"available": True}
    def execute_agent(self, route, prompt, repository, read_only):
        self.routes.append(route)
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
