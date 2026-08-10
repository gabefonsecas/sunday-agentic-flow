#!/usr/bin/env python3
"""Install host adapters without modifying project repositories."""

import json
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()

if os.name == "nt" and os.environ.get("APPDATA"):
    config_dir = Path(os.environ["APPDATA"]) / "agentic-dev-flow"
else:
    config_dir = HOME / ".config" / "agentic-dev-flow"
config_dir.mkdir(parents=True, exist_ok=True)
config_file = config_dir / ".env"
if not config_file.exists():
    source_env = ROOT / ".env"
    source = source_env if source_env.exists() else ROOT / ".env.example"
    shutil.copy2(source, config_file)


def link(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() and target.resolve() == source.resolve():
        return
    if target.exists() or target.is_symlink():
        raise SystemExit(f"Refusing to replace existing path: {target}")
    if os.name == "nt":
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        return
    target.symlink_to(source, target_is_directory=source.is_dir())


def install_managed_file(source, target):
    """Install a namespaced adapter file owned by this plugin."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def ensure_codex_marketplace():
    marketplace = HOME / ".agents" / "plugins" / "marketplace.json"
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    if marketplace.exists():
        data = json.loads(marketplace.read_text(encoding="utf-8"))
    else:
        data = {"name": "personal", "interface": {"displayName": "Personal"}, "plugins": []}
    plugins = data.setdefault("plugins", [])
    if not any(item.get("name") == "agentic-dev-flow" for item in plugins):
        plugins.append(
            {
                "name": "agentic-dev-flow",
                "source": {"source": "local", "path": "./plugins/agentic-dev-flow"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Developer Tools",
            }
        )
        marketplace.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return marketplace


def install_antigravity_plugin():
    target = HOME / ".gemini" / "config" / "plugins" / "agentic-dev-flow"
    if os.name != "nt":
        link(ROOT, target)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        ROOT,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".env", "__pycache__", "*.pyc"),
    )
    for obsolete in (
        target / "scripts" / "local_model_mcp.py",
        target / "scripts" / "run_mlx_server.sh",
        target / "scripts" / "run_ollama.sh",
        target / "scripts" / "run_local_model.ps1",
    ):
        if obsolete.exists():
            obsolete.unlink()
    return target


bin_dir = HOME / ".local" / "bin"
bin_dir.mkdir(parents=True, exist_ok=True)
launchers = {}
for command_name, script_name in (("agentic-friday-mcp", "friday_mcp_proxy.py"),):
    if os.name == "nt":
        launcher = bin_dir / f"{command_name}.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{ROOT / "scripts" / script_name}" %*\r\n',
            encoding="utf-8",
        )
    else:
        launcher = bin_dir / command_name
        link(ROOT / "scripts" / script_name, launcher)
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    launchers[command_name] = launcher

antigravity_plugin = install_antigravity_plugin()

adapter_targets = {
    "codex": HOME / ".codex" / "agents",
    "claude": HOME / ".claude" / "agents",
    "gemini": HOME / ".gemini" / "agents",
    "antigravity": HOME / ".gemini" / "config" / "agents",
}
installed_agents = {}
for host, target_dir in adapter_targets.items():
    source_dir = ROOT / "adapters" / host / "agents"
    installed_agents[host] = []
    for source in sorted(source_dir.iterdir()):
        target = target_dir / source.name
        install_managed_file(source, target)
        installed_agents[host].append(str(target))

marketplace = ensure_codex_marketplace()

summary = {
    "plugin_root": str(ROOT),
    "friday_command": str(launchers["agentic-friday-mcp"]),
    "antigravity_plugin": str(antigravity_plugin),
    "codex_marketplace": str(marketplace),
    "environment_file": str(config_file),
    "installed_agents": installed_agents,
    "claude_session_command": f"claude --plugin-dir {ROOT}",
    "gemini_link_command": f"gemini extensions link {ROOT}",
    "windows_note": "Add %USERPROFILE%\\.local\\bin to the user PATH." if os.name == "nt" else None,
}
print(json.dumps(summary, indent=2, ensure_ascii=False))
