#!/usr/bin/env python3
"""Install Sunday from a source checkout."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sunday.installation import install


if __name__ == "__main__":
    print(json.dumps(install(), indent=2, ensure_ascii=False))
