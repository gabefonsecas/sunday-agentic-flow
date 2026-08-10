#!/usr/bin/env python3
"""Run the Sunday environment doctor."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sunday.diagnostics import doctor


if __name__ == "__main__":
    result = doctor("--network" in sys.argv)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["healthy"] else 1)
