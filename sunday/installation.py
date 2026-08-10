"""Transactional installation lifecycle for Sunday."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory

from sunday import __version__
from sunday.config import DEFAULT_CONFIG
from sunday.paths import bin_dir, config_dir

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_NAME = "sunday-agentic-flow"


def _hash(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


@contextmanager
def transaction():
    backups: list[tuple[Path, Path | None]] = []
    with TemporaryDirectory(prefix="sunday-install-") as temp:
        directory = Path(temp)

        def prepare(target: Path) -> None:
            if any(item[0] == target for item in backups):
                return
            if target.exists() or target.is_symlink():
                backup = directory / str(len(backups))
                if target.is_symlink():
                    backup.symlink_to(os.readlink(target))
                elif target.is_dir():
                    shutil.copytree(target, backup)
                else:
                    shutil.copy2(target, backup)
                backups.append((target, backup))
            else:
                backups.append((target, None))

        try:
            yield prepare
        except Exception:
            for target, backup in reversed(backups):
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                elif target.exists() or target.is_symlink():
                    target.unlink()
                if backup:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if backup.is_symlink():
                        target.symlink_to(os.readlink(backup))
                    elif backup.is_dir():
                        shutil.copytree(backup, target)
                    else:
                        shutil.copy2(backup, target)
            raise


def _copy(source: Path, target: Path, prepare) -> None:
    prepare(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()
    shutil.copy2(source, target)


def _link(source: Path, target: Path, prepare) -> None:
    prepare(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()
    if os.name == "nt":
        shutil.copytree(source, target)
    else:
        target.symlink_to(source, target_is_directory=True)


def _launcher(name: str, script: str, prepare) -> Path:
    target = bin_dir() / (f"{name}.cmd" if os.name == "nt" else name)
    prepare(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        content = f'@echo off\r\n"{sys.executable}" "{ROOT / "scripts" / script}" %*\r\n'
    else:
        content = f'#!/bin/sh\nexec "{sys.executable}" "{ROOT / "scripts" / script}" "$@"\n'
    target.write_text(content, encoding="utf-8", newline="")
    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return target


def _marketplace(prepare) -> Path:
    path = Path.home() / ".agents" / "plugins" / "marketplace.json"
    prepare(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "name": "personal", "interface": {"displayName": "Personal"}, "plugins": []
    }
    entry = {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }
    data["plugins"] = [item for item in data.setdefault("plugins", []) if item.get("name") != PLUGIN_NAME]
    data["plugins"].append(entry)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def install() -> dict:
    installed: list[Path] = []
    with transaction() as prepare:
        config_dir().mkdir(parents=True, exist_ok=True)
        env = config_dir() / ".env"
        if not env.exists():
            _copy(ROOT / ".env.example", env, prepare)
            if os.name != "nt":
                env.chmod(0o600)
        config = config_dir() / "config.toml"
        if not config.exists():
            prepare(config)
            config.write_text(DEFAULT_CONFIG, encoding="utf-8")
        installed.extend([_launcher("sunday", "sunday.py", prepare), _launcher("sunday-friday-mcp", "friday_mcp_proxy.py", prepare)])
        plugin_source = Path.home() / ".agents" / "plugins" / "plugins" / PLUGIN_NAME
        _link(ROOT, plugin_source, prepare)
        installed.append(plugin_source)
        antigravity = Path.home() / ".gemini" / "config" / "plugins" / PLUGIN_NAME
        _link(ROOT, antigravity, prepare)
        installed.append(antigravity)
        targets = {
            "codex": Path.home() / ".codex" / "agents",
            "claude": Path.home() / ".claude" / "agents",
            "gemini": Path.home() / ".gemini" / "agents",
            "antigravity": Path.home() / ".gemini" / "config" / "agents",
        }
        agents: dict[str, list[str]] = {}
        for host, directory in targets.items():
            agents[host] = []
            for source in sorted((ROOT / "adapters" / host / "agents").iterdir()):
                target = directory / source.name
                _copy(source, target, prepare)
                installed.append(target)
                agents[host].append(str(target))
        marketplace = _marketplace(prepare)
        installed.append(marketplace)
        manifest = config_dir() / "install-manifest.json"
        prepare(manifest)
        manifest.write_text(json.dumps({
            "version": __version__, "plugin_root": str(ROOT),
            "paths": [{"path": str(path), "sha256": _hash(path)} for path in installed],
        }, indent=2) + "\n", encoding="utf-8")
    return {
        "installed": True, "version": __version__, "plugin": PLUGIN_NAME,
        "environment": str(config_dir() / ".env"), "configuration": str(config_dir() / "config.toml"),
        "commands": ["sunday", "sunday-friday-mcp"], "agents": agents,
    }


def uninstall() -> dict:
    manifest = config_dir() / "install-manifest.json"
    if not manifest.is_file():
        return {"uninstalled": False, "reason": "install manifest not found"}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    removed: list[str] = []
    preserved: list[str] = []
    for item in reversed(data.get("paths", [])):
        path = Path(item["path"])
        if path.name == "marketplace.json":
            if path.is_file():
                market = json.loads(path.read_text(encoding="utf-8"))
                market["plugins"] = [entry for entry in market.get("plugins", []) if entry.get("name") != PLUGIN_NAME]
                path.write_text(json.dumps(market, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                removed.append(str(path) + " entry")
            continue
        if path.is_symlink():
            path.unlink()
            removed.append(str(path))
        elif path.is_dir():
            shutil.rmtree(path)
            removed.append(str(path))
        elif path.is_file() and (not item.get("sha256") or _hash(path) == item["sha256"]):
            path.unlink()
            removed.append(str(path))
        elif path.exists():
            preserved.append(str(path))
    manifest.unlink(missing_ok=True)
    return {"uninstalled": True, "removed": removed, "preserved_modified": preserved}


def update() -> dict:
    if not (ROOT / ".git").is_dir():
        raise RuntimeError("Sunday update requires a Git checkout")
    result = subprocess.run(
        ["git", "pull", "--ff-only"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    installed = install()
    return {"updated": True, "git": result.stdout.strip(), **installed}
