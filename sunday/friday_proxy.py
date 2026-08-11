"""MCP stdio bridge for Friday plus Sunday composite tools."""

import json
import os
import sys

from sunday.adapters.friday import FridayAdapter, FridayMCPClient
from sunday.security import load_env

load_env()

ASSIGN_TOOL = {
    "name": "assign_authenticated_user",
    "description": "Resolve the Friday user from the active token and assign that user to an item.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "workspace_id": {"type": "integer"},
            "board_id": {"type": "integer"},
            "item_id": {"type": "integer"},
            "people_column": {"type": "string"},
        },
        "required": ["workspace_id", "board_id", "item_id"],
    },
}


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_message(message: dict, client: FridayMCPClient) -> dict:
    method = message.get("method")
    params = message.get("params", {})
    if method == "tools/call" and params.get("name") == ASSIGN_TOOL["name"]:
        arguments = params.get("arguments", {})
        adapter = FridayAdapter(client)
        result = adapter.claim_task(
            {"id": arguments["item_id"]},
            arguments["workspace_id"],
            arguments["board_id"],
            arguments.get("people_column") or os.environ.get("FRIDAY_ASSIGNEE_COLUMN", ""),
        )
        return {
            "jsonrpc": "2.0", "id": message.get("id"),
            "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
        }
    response = client.request(method, params if params else None)
    if method == "tools/list":
        tools = response.setdefault("tools", [])
        if not any(tool.get("name") == ASSIGN_TOOL["name"] for tool in tools):
            tools.append(ASSIGN_TOOL)
    return {"jsonrpc": "2.0", "id": message.get("id"), "result": response}


def main() -> None:
    client = FridayMCPClient()
    for line in sys.stdin:
        message = None
        try:
            message = json.loads(line)
            response = handle_message(message, client)
            if message.get("id") is not None:
                emit(response)
        except Exception as exc:
            request_id = message.get("id") if isinstance(message, dict) else None
            emit({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}})


if __name__ == "__main__":
    main()
