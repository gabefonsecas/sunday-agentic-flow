"""Cross-platform paths owned by Sunday."""

import os
from pathlib import Path


def _is_windows() -> bool:
    return os.name == "nt"


def config_dir() -> Path:
    override = os.environ.get("SUNDAY_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if _is_windows() and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "sunday"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "sunday"


def state_dir() -> Path:
    override = os.environ.get("SUNDAY_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if _is_windows() and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "sunday"
    return (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        / "sunday"
    )


def data_dir() -> Path:
    """Return Sunday's user-global, non-configuration data directory."""
    override = os.environ.get("SUNDAY_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if _is_windows() and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "sunday"
    return (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "sunday"
    )


def installation_dir() -> Path:
    """Return the root containing versioned Sunday installations."""
    override = os.environ.get("SUNDAY_INSTALL_DIR")
    return Path(override).expanduser().resolve() if override else data_dir().resolve()


def releases_dir() -> Path:
    return installation_dir() / "releases"


def bin_dir() -> Path:
    override = os.environ.get("SUNDAY_BIN_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if _is_windows() and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "sunday" / "bin"
    return Path.home() / ".local" / "bin"


def database_path() -> Path:
    return state_dir() / "sunday.db"
