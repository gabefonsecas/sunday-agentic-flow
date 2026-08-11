#!/usr/bin/env python3
"""Check or synchronize Sunday manifest versions."""

import argparse
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    ROOT / ".codex-plugin" / "plugin.json",
    ROOT / ".claude-plugin" / "plugin.json",
    ROOT / "gemini-extension.json",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    mismatches = []
    project_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if project_version != version:
        mismatches.append(f"pyproject.toml: {project_version} != {version}")
    for path in FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        current = data.get("version", "").split("+", 1)[0]
        if current != version:
            mismatches.append(f"{path}: {current} != {version}")
            if args.write:
                data["version"] = version
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if mismatches and not args.write:
        raise SystemExit("\n".join(mismatches))
    print(json.dumps({"version": version, "files": [str(path) for path in FILES], "synchronized": True}, indent=2))


if __name__ == "__main__":
    main()
