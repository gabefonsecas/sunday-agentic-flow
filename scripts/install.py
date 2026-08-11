#!/usr/bin/env python3
"""Install Sunday from a source checkout."""

import json
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit(
        f"Sunday requires Python 3.10 or newer; found {sys.version.split()[0]}."
    )

if sys.version_info < (3, 11):
    try:
        import tomli  # noqa: F401
    except ModuleNotFoundError:
        raise SystemExit(
            "Sunday detected Python 3.10 without TOML support. "
            "On Ubuntu/WSL run: sudo apt update && sudo apt install -y python3-tomli"
        ) from None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sunday.installation import install


if __name__ == "__main__":
    print(json.dumps(install(), indent=2, ensure_ascii=False))
