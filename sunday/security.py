"""Secret loading and redaction."""

import os
import re
from pathlib import Path
from typing import Mapping

from .paths import config_dir

SECRET_KEYS = (
    "TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL",
    "AUTHORIZATION", "COOKIE", "SESSION",
)
QUERY_SECRET = re.compile(r"([?&](?:api_token|token|key)=)[^&\s]+", re.IGNORECASE)


def env_path() -> Path:
    override = os.environ.get("SUNDAY_ENV_FILE")
    return Path(override).expanduser() if override else config_dir() / ".env"


def load_env(path: Path | None = None) -> Path | None:
    selected = path or env_path()
    if not selected.is_file():
        return None
    for raw_line in selected.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)
    return selected


def redact(value: object, environment: Mapping[str, str] | None = None) -> object:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(part in key.upper() for part in SECRET_KEYS) else redact(item, environment)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, environment) for item in value]
    if not isinstance(value, str):
        return value
    result = QUERY_SECRET.sub(r"\1[REDACTED]", value)
    for key, secret in (environment or os.environ).items():
        if secret and len(secret) >= 8 and any(part in key.upper() for part in SECRET_KEYS):
            result = result.replace(secret, "[REDACTED]")
    return result
