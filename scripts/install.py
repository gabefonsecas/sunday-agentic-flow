#!/usr/bin/env python3
"""Install Sunday from a source checkout."""

import json
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    raise SystemExit(
        f"Sunday requires Python 3.11 or newer; found {sys.version.split()[0]}."
    )

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sunday.installation import install


if __name__ == "__main__":
    development = "--development" in sys.argv[1:]
    print(json.dumps(install(development=development), indent=2, ensure_ascii=False))
