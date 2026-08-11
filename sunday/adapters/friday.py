"""Friday task-manager adapter over the legacy MCP SSE transport."""

import json
import os
import threading
import urllib.parse
import urllib.request
from itertools import count

from sunday.adapters.base import TaskManagerAdapter
from sunday.security import load_env


class FridayMCPClient:
    def __init__(self, url: str | None = None, timeout: float | None = None):
        load_env()
        base = os.environ.get(
            "FRIDAY_MCP_BASE_URL", "sua_url_friday_mcp"
        )
        token = os.environ.get("FRIDAY_MCP_API_TOKEN", "")
        self.url = url or os.environ.get("FRIDAY_MCP_URL", "")
        if not self.url and token:
            self.url = base + "?" + urllib.parse.urlencode({"api_token": token})
        self.timeout = timeout or float(os.environ.get("FRIDAY_MCP_TIMEOUT", "60"))
        self.endpoint: str | None = None
        self.error: Exception | None = None
        self.ready = threading.Event()
        self.ids = count(1)
        self.thread: threading.Thread | None = None

    def connect(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        if not self.url:
            raise RuntimeError("Configure FRIDAY_MCP_API_TOKEN in ~/.config/sunday/.env")
        self.thread = threading.Thread(target=self._read_sse, daemon=True)
        self.thread.start()

    def _read_sse(self) -> None:
        try:
            request = urllib.request.Request(self.url, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(request, timeout=None) as response:
                event = ""
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:") and event == "endpoint":
                        self.endpoint = urllib.parse.urljoin(self.url, line[5:].strip())
                        self.ready.set()
        except Exception as exc:
            self.error = exc
            self.ready.set()

    def request(self, method: str, params: dict | None = None) -> dict:
        self.connect()
        if not self.ready.wait(self.timeout):
            raise TimeoutError("Friday SSE endpoint discovery timed out")
        if self.error:
            raise RuntimeError(f"Friday SSE connection failed: {self.error}")
        message = {
            "jsonrpc": "2.0",
            "id": f"sunday-{next(self.ids)}",
            "method": method,
        }
        if params is not None:
            message["params"] = params
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(message).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8").strip()
        if not body:
            return {}
        payload = json.loads(body)
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", "Friday MCP request failed"))
        return payload.get("result", {})

    def tool(self, name: str, arguments: dict | None = None):
        result = self.request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        for block in result.get("content", []):
            if block.get("type") == "text":
                text = block.get("text", "null")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return result.get("structuredContent", result)


def resolve_user_from_tasks(tasks: list[dict]) -> dict:
    sets: list[set] = []
    profiles: dict[object, dict] = {}
    for task in tasks:
        assignees = task.get("responsaveis") or task.get("assignees") or []
        ids = {person.get("id") for person in assignees if person.get("id") is not None}
        if ids:
            sets.append(ids)
            profiles.update({person["id"]: person for person in assignees if person.get("id") is not None})
    if not sets:
        raise RuntimeError("Token-scoped tasks contain no assignee identity")
    candidates = set.intersection(*sets)
    if len(candidates) != 1:
        raise RuntimeError("Token did not resolve exactly one Friday user")
    return profiles[candidates.pop()]


class FridayAdapter(TaskManagerAdapter):
    def __init__(self, client: FridayMCPClient | None = None):
        self.client = client or FridayMCPClient()

    def authenticate(self) -> dict:
        tasks = self.client.tool("list_my_tasks", {})
        return {"authenticated": True, "task_count": len(tasks), "transport": "mcp-sse"}

    def get_current_user(self, workspace_id: int) -> dict:
        try:
            user = self.client.tool("get_current_user", {})
            if isinstance(user, dict) and user.get("id") is not None:
                return {**user, "identity_source": "get_current_user"}
        except RuntimeError:
            pass
        try:
            user = resolve_user_from_tasks(self.client.tool("list_my_tasks", {}))
            return {**user, "identity_source": "token-scoped list_my_tasks"}
        except RuntimeError:
            fallback = os.environ.get("FRIDAY_FALLBACK_ASSIGNEE_EMAIL", "").casefold()
            if not fallback:
                raise RuntimeError(
                    "Friday cannot resolve this taskless token. Configure "
                    "FRIDAY_FALLBACK_ASSIGNEE_EMAIL or expose get_current_user."
                )
            members = self.client.tool("list_workspace_members", {"workspace_id": workspace_id})
            matches = [member for member in members if str(member.get("email", "")).casefold() == fallback]
            if len(matches) != 1:
                raise RuntimeError("Friday fallback email did not resolve exactly one workspace member")
            return {**matches[0], "identity_source": "configured fallback email"}

    def get_task(self, task_ref: str, board_id: int | None = None) -> dict:
        parsed = urllib.parse.urlparse(str(task_ref))
        item_id = int(parsed.path.rstrip("/").split("/")[-1])
        tasks = self.client.tool("list_my_tasks", {})
        matches = [task for task in tasks if int(task.get("id", -1)) == item_id]
        if len(matches) == 1:
            return matches[0]
        if board_id:
            groups = self.client.tool("list_groups", {"board_id": board_id})
            for group in groups:
                for task in self.client.tool("list_items", {"group_id": group["id"]}):
                    if int(task.get("id", -1)) == item_id:
                        return task
        raise RuntimeError(f"Friday task not found on configured board: {task_ref}")

    def list_ready_tasks(
        self, label: str, board_id: int | None = None,
        completed_status: str = "",
    ) -> list[dict]:
        tasks = self.client.tool("list_my_tasks", {})
        if board_id is not None:
            tasks = [task for task in tasks if int(task.get("board_id", -1)) == board_id]
        if completed_status:
            tasks = [task for task in tasks if self._status_id(task) != str(completed_status)]
        if label:
            tasks = [task for task in tasks if label.casefold() in self._labels(task)]
        return tasks

    @staticmethod
    def _status_id(task: dict) -> str:
        status = task.get("status")
        if isinstance(status, dict):
            return str(status.get("id", ""))
        return str(status or "")

    @staticmethod
    def _labels(task: dict) -> set[str]:
        labels: set[str] = set()
        for key in ("labels", "tags", "etiquetas"):
            for value in task.get(key) or []:
                labels.add(str(value.get("name", value)) if isinstance(value, dict) else str(value))
        for column in task.get("columns") or []:
            if column.get("type") != "tags":
                continue
            formatted = column.get("formatted_value") or column.get("value") or []
            if not isinstance(formatted, list):
                formatted = [formatted]
            for value in formatted:
                labels.add(str(value.get("name", value.get("label", value))) if isinstance(value, dict) else str(value))
        return {label.casefold() for label in labels}

    def claim_task(self, task: dict, workspace_id: int, board_id: int, people_column: str = "") -> dict:
        user = self.get_current_user(workspace_id)
        members = self.client.tool("list_workspace_members", {"workspace_id": workspace_id})
        matches = [member for member in members if member.get("id") == user.get("id")]
        if len(matches) != 1:
            raise RuntimeError("Token-authenticated user is not a target workspace member")
        columns = self.client.tool("list_columns", {"board_id": board_id})
        people = [column for column in columns if column.get("type") == "people"]
        if people_column:
            people = [
                column for column in people
                if str(column.get("id")) == people_column
                or str(column.get("name", "")).casefold() == people_column.casefold()
            ]
        if len(people) != 1:
            raise RuntimeError("Configure one valid Friday people column")
        self.client.tool(
            "update_cell_value",
            {"item_id": int(task["id"]), "column_id": people[0]["id"], "value": str(user["id"])},
        )
        return {
            "assigned": True, "member_id": user["id"], "member_email": user.get("email"),
            "identity_source": user["identity_source"], "column_id": people[0]["id"],
        }

    def create_story(self, story: dict, board_id: int, group_id: int) -> dict:
        return self.client.tool(
            "create_item",
            {"group_id": group_id, "name": story["title"], "description": story["description"]},
        )

    def find_story(self, marker: str, group_id: int) -> dict | None:
        items = self.client.tool("list_items", {"group_id": group_id})
        matches = [
            item for item in items
            if marker in str(item.get("description") or item.get("descricao") or item.get("content") or "")
        ]
        if len(matches) > 1:
            raise RuntimeError(f"Friday contains duplicate items for {marker}")
        return matches[0] if matches else None

    def transition(self, item_id: int, group_id: int) -> dict:
        return self.client.tool("move_item", {"item_id": item_id, "target_group_id": group_id})

    def set_status(self, item_id: int, board_id: int, column: str, value: str) -> dict:
        columns = self.client.tool("list_columns", {"board_id": board_id})
        matches = [
            item for item in columns
            if item.get("type") == "status" and (
                str(item.get("id")) == str(column)
                or str(item.get("name", "")).casefold() == str(column).casefold()
            )
        ]
        if len(matches) != 1:
            raise RuntimeError("Configure one valid Friday status column")
        return self.client.tool(
            "update_cell_value",
            {"item_id": item_id, "column_id": matches[0]["id"], "value": str(value)},
        )

    def mark_ai(self, item_id: int, board_id: int, column: str) -> dict:
        columns = self.client.tool("list_columns", {"board_id": board_id})
        matches = [
            item for item in columns
            if item.get("type") == "checkbox" and (
                str(item.get("id")) == str(column)
                or str(item.get("name", "")).casefold() == str(column).casefold()
            )
        ]
        if len(matches) != 1:
            raise RuntimeError("Configure one valid Friday AI checkbox column")
        return self.client.tool(
            "update_cell_value",
            {"item_id": item_id, "column_id": matches[0]["id"], "value": "true"},
        )

    def comment(self, item_id: int, text: str) -> dict:
        return self.client.tool("add_comment", {"item_id": item_id, "content": text})

    def attach_pull_request(self, item_id: int, board_id: int, url: str, column: str = "") -> dict:
        columns = self.client.tool("list_columns", {"board_id": board_id})
        candidates = [
            item for item in columns
            if (column and (str(item.get("id")) == column or str(item.get("name", "")).casefold() == column.casefold()))
            or (not column and item.get("type") in {"link", "url"})
        ]
        if len(candidates) == 1:
            return self.client.tool(
                "update_cell_value", {"item_id": item_id, "column_id": candidates[0]["id"], "value": url}
            )
        return self.comment(item_id, f"Pull request: {url}")
