#!/usr/bin/env python3
"""Bridge legacy remote MCP SSE into portable MCP stdio."""

import json
import os
import sys
import threading
import urllib.parse
import urllib.request
from itertools import count
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import load_env

load_env()

FRIDAY_BASE_URL = os.environ.get(
    "FRIDAY_MCP_BASE_URL",
    "https://friday.eletromidia.com.br/api/mcp_sse.php",
)
FRIDAY_TOKEN = os.environ.get("FRIDAY_MCP_API_TOKEN", "")
REMOTE_URL = os.environ.get("FRIDAY_MCP_URL", "")
if not REMOTE_URL and FRIDAY_TOKEN:
    REMOTE_URL = FRIDAY_BASE_URL + "?" + urllib.parse.urlencode({"api_token": FRIDAY_TOKEN})
TIMEOUT = float(os.environ.get("FRIDAY_MCP_TIMEOUT", "60"))
ASSIGNEE_EMAIL = os.environ.get("FRIDAY_ASSIGNEE_EMAIL", "").strip()
ASSIGNEE_COLUMN = os.environ.get("FRIDAY_ASSIGNEE_COLUMN", "").strip()
endpoint = None
endpoint_ready = threading.Event()
startup_error = None
internal_ids = count(1)

ASSIGN_TOOL = {
    "name": "assign_configured_user",
    "description": (
        "Assign the Friday user configured by FRIDAY_ASSIGNEE_EMAIL to an item. "
        "Call this immediately when implementation starts."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "workspace_id": {"type": "integer"},
            "board_id": {"type": "integer"},
            "item_id": {"type": "integer"},
        },
        "required": ["workspace_id", "board_id", "item_id"],
    },
}


def emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read_sse():
    global endpoint, startup_error
    try:
        if not REMOTE_URL:
            raise RuntimeError("Configure FRIDAY_MCP_API_TOKEN in the private .env file")
        request = urllib.request.Request(REMOTE_URL, headers={"Accept": "text/event-stream"})
        with urllib.request.urlopen(request, timeout=None) as response:
            current_event = None
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:") and current_event == "endpoint":
                    endpoint = urllib.parse.urljoin(REMOTE_URL, line[5:].strip())
                    endpoint_ready.set()
    except Exception as exc:
        startup_error = exc
        endpoint_ready.set()


def post(message):
    if not endpoint_ready.wait(TIMEOUT):
        raise TimeoutError("Friday SSE endpoint discovery timed out")
    if startup_error is not None:
        raise RuntimeError(f"Friday SSE connection failed: {startup_error}")
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(message).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read().decode("utf-8").strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def parse_tool_content(response):
    if not response or "error" in response:
        message = (
            response.get("error", {}).get("message", "Friday tool call failed")
            if response
            else "Friday returned no response"
        )
        raise RuntimeError(message)
    blocks = response.get("result", {}).get("content", [])
    for block in blocks:
        if block.get("type") == "text":
            return json.loads(block.get("text", "null"))
    raise RuntimeError("Friday tool response did not contain JSON text")


def call_remote_tool(name, arguments, post_fn=post):
    response = post_fn(
        {
            "jsonrpc": "2.0",
            "id": f"agentic-dev-flow-{next(internal_ids)}",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    return parse_tool_content(response)


def select_people_column(columns):
    people = [column for column in columns if column.get("type") == "people"]
    if ASSIGNEE_COLUMN:
        configured = [
            column
            for column in people
            if str(column.get("id")) == ASSIGNEE_COLUMN
            or str(column.get("name", "")).casefold() == ASSIGNEE_COLUMN.casefold()
        ]
        if len(configured) == 1:
            return configured[0]
        raise RuntimeError("FRIDAY_ASSIGNEE_COLUMN did not match one people column")
    if len(people) != 1:
        raise RuntimeError("Board must have exactly one people column or configure FRIDAY_ASSIGNEE_COLUMN")
    return people[0]


def assign_configured_user(arguments, post_fn=post):
    if not ASSIGNEE_EMAIL:
        raise RuntimeError("Configure FRIDAY_ASSIGNEE_EMAIL in the private .env file")
    workspace_id = arguments["workspace_id"]
    board_id = arguments["board_id"]
    item_id = arguments["item_id"]
    members = call_remote_tool("list_workspace_members", {"workspace_id": workspace_id}, post_fn)
    matches = [
        member
        for member in members
        if str(member.get("email", "")).casefold() == ASSIGNEE_EMAIL.casefold()
    ]
    if len(matches) != 1:
        raise RuntimeError("FRIDAY_ASSIGNEE_EMAIL did not match exactly one workspace member")
    columns = call_remote_tool("list_columns", {"board_id": board_id}, post_fn)
    column = select_people_column(columns)
    member = matches[0]
    call_remote_tool(
        "update_cell_value",
        {"item_id": item_id, "column_id": column["id"], "value": str(member["id"])},
        post_fn,
    )
    return {
        "assigned": True,
        "item_id": item_id,
        "column_id": column["id"],
        "member_id": member["id"],
        "member_email": member["email"],
    }


def handle_message(message, post_fn=post):
    method = message.get("method")
    if method == "tools/call" and message.get("params", {}).get("name") == ASSIGN_TOOL["name"]:
        result = assign_configured_user(message["params"].get("arguments", {}), post_fn)
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
        }
    response = post_fn(message)
    if method == "tools/list" and response and "result" in response:
        tools = response["result"].setdefault("tools", [])
        if not any(tool.get("name") == ASSIGN_TOOL["name"] for tool in tools):
            tools.append(ASSIGN_TOOL)
    return response


def main():
    threading.Thread(target=read_sse, daemon=True).start()
    for line in sys.stdin:
        message = None
        try:
            message = json.loads(line)
            response = handle_message(message)
            if response is not None and message.get("id") is not None:
                emit(response)
        except Exception as exc:
            request_id = message.get("id") if isinstance(message, dict) else None
            emit({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}})


if __name__ == "__main__":
    main()
