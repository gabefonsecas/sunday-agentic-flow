"""Sunday deterministic development orchestration."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

try:
    __version__ = version("sunday-agentic-flow")
except PackageNotFoundError:
    __version__ = (Path(__file__).resolve().parent.parent / "VERSION").read_text(
        encoding="utf-8"
    ).strip()
