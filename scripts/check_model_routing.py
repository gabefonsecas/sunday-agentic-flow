#!/usr/bin/env python3
"""Validate distinct remote-model profiles for every host adapter."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASES = {
    "discovery": "sunday-task-analyst",
    "implementation": "sunday-implementation-worker",
    "verification": "sunday-implementation-verifier",
    "review": "sunday-branch-reviewer",
}


def markdown_frontmatter(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"Missing frontmatter: {path}")
    values = {}
    for line in lines[1:]:
        if line == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_profile(host, stem):
    directory = ROOT / "adapters" / host / "agents"
    if host == "codex":
        data = tomllib.loads((directory / f"{stem}.toml").read_text(encoding="utf-8"))
        return {"model": data.get("model"), "effort": data.get("model_reasoning_effort")}
    data = markdown_frontmatter(directory / f"{stem}.md")
    return {"model": data.get("model"), "effort": data.get("effort")}


matrix = {}
valid = True
for host in ("codex", "claude", "gemini", "antigravity"):
    profiles = {phase: load_profile(host, stem) for phase, stem in PHASES.items()}
    distinct = {(profile["model"], profile["effort"]) for profile in profiles.values()}
    host_valid = all(profile["model"] for profile in profiles.values()) and len(distinct) >= 2
    matrix[host] = {"valid": host_valid, "phases": profiles}
    valid = valid and host_valid

print(json.dumps({"valid": valid, "hosts": matrix}, indent=2, ensure_ascii=False))
raise SystemExit(0 if valid else 1)
