#!/usr/bin/env python3
"""Bridge legacy remote MCP SSE into portable MCP stdio."""

import json
import os
import sys
import threading
import urllib.parse
import urllib.request
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
endpoint = None
endpoint_ready = threading.Event()
startup_error = None


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


threading.Thread(target=read_sse, daemon=True).start()

for line in sys.stdin:
    message = None
    try:
        message = json.loads(line)
        response = post(message)
        if response is not None and message.get("id") is not None:
            emit(response)
    except Exception as exc:
        request_id = message.get("id") if isinstance(message, dict) else None
        emit({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}})
