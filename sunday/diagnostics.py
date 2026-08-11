"""Installation and runtime health checks."""

import os
import shutil
import subprocess
import sys

from sunday import __version__
from sunday.adapters.base import ModelExecution
from sunday.adapters.hosts import CommandHostAdapter
from sunday.config import config_path, load_settings
from sunday.paths import database_path
from sunday.security import env_path, load_env
from sunday.routing import AGENTS, MODEL_POOLS


def _command(command: list[str]) -> dict:
    executable = shutil.which(command[0])
    if not executable:
        return {"available": False, "path": None, "healthy": False}
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "available": True, "path": executable, "healthy": result.returncode == 0,
        "output": (result.stdout or result.stderr).strip()[-1000:],
    }


def _probe_models(hosts: dict[str, dict]) -> tuple[dict[str, list[dict]], dict]:
    checks: dict[str, list[dict]] = {}
    counts = {status: 0 for status in ("confirmed", "requested_only", "mismatched", "unavailable")}
    for name, health in hosts.items():
        if not health["available"] or health.get("fallback"):
            continue
        adapter = CommandHostAdapter(name)
        checks[name] = []
        for model in adapter.discover_models():
            try:
                execution = adapter.probe_model(model)
            except Exception as exc:
                execution = ModelExecution(
                    requested_model=model,
                    observed_model=None,
                    verification_status="unavailable",
                    verification_evidence={"exception": type(exc).__name__},
                    exit_code=1,
                    duration=0,
                    output=str(exc),
                )
            checks[name].append(execution.as_dict())
            counts[execution.verification_status] += 1
    total = sum(counts.values())
    summary = {
        "total": total,
        "counts": counts,
        "healthy": total > 0 and counts["confirmed"] == total,
    }
    return checks, summary


def doctor(network: bool = False, models: bool = False) -> dict:
    loaded = load_env()
    settings = load_settings()
    selected_env = env_path()
    permissions = None
    if selected_env.exists() and os.name != "nt":
        permissions = oct(selected_env.stat().st_mode & 0o777)
    hosts = {
        name: _command([binary, "--version"])
        for name, binary in (("codex", "codex"), ("claude", "claude"), ("gemini", "gemini"), ("antigravity", "agy"))
    }
    if not hosts["antigravity"]["available"] and hosts["gemini"]["available"]:
        hosts["antigravity"] = {**hosts["gemini"], "fallback": "gemini"}
    result = {
        "sunday": {"version": __version__, "python": sys.version.split()[0], "supported_python": sys.version_info >= (3, 11)},
        "paths": {
            "config": str(config_path()), "config_exists": config_path().is_file(),
            "environment": str(selected_env), "environment_loaded": str(loaded) if loaded else None,
            "environment_permissions": permissions, "database": str(database_path()),
        },
        "friday": {
            "configured": bool(os.environ.get("FRIDAY_MCP_API_TOKEN") or os.environ.get("FRIDAY_MCP_URL")),
            "fallback_email": bool(os.environ.get("FRIDAY_FALLBACK_ASSIGNEE_EMAIL")),
        },
        "github": _command(["gh", "auth", "status"]),
        "git": _command(["git", "--version"]),
        "hosts": hosts,
        "routing": {
            host: {
                phase: {
                    "agent": AGENTS[phase],
                    "pool": [
                        {"tier": candidate.tier, "model": candidate.model, "effort": candidate.effort}
                        for candidate in candidates
                    ],
                }
                for phase, candidates in phases.items()
            }
            for host, phases in MODEL_POOLS.items()
        },
        "projects": {
            name: {"repository": str(project.repository), "exists": project.repository.is_dir()}
            for name, project in settings.projects.items()
        },
    }
    if network and result["friday"]["configured"]:
        try:
            from sunday.adapters.friday import FridayAdapter
            result["friday"]["connection"] = FridayAdapter().authenticate()
        except Exception as exc:
            result["friday"]["connection"] = {"authenticated": False, "error": str(exc)}
    if models:
        checks, summary = _probe_models(hosts)
        result["models"] = checks
        result["model_verification"] = summary
    result["healthy"] = (
        result["sunday"]["supported_python"] and result["git"]["healthy"]
        and any(host["healthy"] for host in hosts.values())
        and result["paths"]["config_exists"] and result["friday"]["configured"]
    )
    if models:
        result["healthy"] = result["healthy"] and result["model_verification"]["healthy"]
    return result
