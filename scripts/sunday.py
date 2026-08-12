#!/usr/bin/env python3.11
"""Source-checkout launcher for Sunday."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sunday.cli import main


if __name__ == "__main__":
    main()
