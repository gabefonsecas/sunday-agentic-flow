#!/usr/bin/env python3
"""Report installed hosts, Friday configuration, and model adapters."""

import json
import os
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import load_env

env_path = load_env()

result = {
    "platform": platform.platform(),
    "architecture": platform.machine(),
    "hosts": {name: shutil.which(name) for name in ("codex", "claude", "gemini", "agy")},
    "python": shutil.which("python") or shutil.which("python3"),
    "environment_file": str(env_path) if env_path else None,
    "friday_configured": bool(os.environ.get("FRIDAY_MCP_API_TOKEN") or os.environ.get("FRIDAY_MCP_URL")),
    "friday_identity": {
        "source": "FRIDAY_MCP_API_TOKEN via token-scoped list_my_tasks",
        "column": os.environ.get("FRIDAY_ASSIGNEE_COLUMN") or "automatic single people column",
    },
    "agents": {
        "codex": str(Path.home() / ".codex" / "agents"),
        "claude": str(Path.home() / ".claude" / "agents"),
        "gemini": str(Path.home() / ".gemini" / "agents"),
        "antigravity": str(Path.home() / ".gemini" / "config" / "agents"),
    },
}
print(json.dumps(result, indent=2, ensure_ascii=False))
