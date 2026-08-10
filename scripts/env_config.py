#!/usr/bin/env python3
"""Load private plugin configuration without external dependencies."""

import os
from pathlib import Path


def default_env_path():
    override = os.environ.get("AGENTIC_DEV_FLOW_ENV_FILE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "agentic-dev-flow" / ".env"
    return Path.home() / ".config" / "agentic-dev-flow" / ".env"


def load_env():
    candidates = [
        default_env_path(),
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
        return path
    return None
