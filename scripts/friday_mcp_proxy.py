#!/usr/bin/env python3
"""Source-checkout launcher for the Sunday Friday bridge."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sunday.friday_proxy import main


if __name__ == "__main__":
    main()
