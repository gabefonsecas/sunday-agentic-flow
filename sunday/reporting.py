"""Auditable JSON and Markdown run reports."""

import json
from pathlib import Path

from sunday import __version__
from sunday.paths import config_dir
from sunday.state import RunStore
from sunday.routing import ModelRouter


def report_data(store: RunStore, run_id: str) -> dict:
    run = store.get(run_id)
    events = store.events(run_id)
    outcomes = [event["payload"] for event in events if event["kind"] == "route.completed"]
    effects = store.effects(run_id) if hasattr(store, "effects") else []
    try:
        lease = store.lease_status(run_id)
    except Exception:
        lease = None
    manifest_path = config_dir() / "install-manifest.json"
    installation = {"version": __version__, "manifest": str(manifest_path)}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            installation.update({
                "version": manifest.get("version", __version__),
                "release": manifest.get("plugin_root"),
            })
        except (OSError, json.JSONDecodeError):
            installation["manifest_error"] = "invalid"
    retries = max(0, len(outcomes) - len({item.get("phase") for item in outcomes}))
    reconciled = [
        event for event in events if event["kind"] == "effect.reconciled"
    ]
    return {
        "run": {
            "id": run.id, "task_ref": run.task_ref, "project": run.project,
            "host": run.host, "state": run.state, "created_at": run.created_at,
            "updated_at": run.updated_at, "metadata": run.metadata,
            "worktree": run.worktree_path,
        },
        "events": events,
        "effects": effects,
        "lease": lease,
        "reliability": {
            "model_retries": retries,
            "reconciled_effects": len(reconciled),
            "uncertain_effects": [
                item.get("effect_key") for item in effects
                if item.get("status") != "completed"
            ],
        },
        "installation": installation,
        "routing_recommendation": ModelRouter(run.host).recommendation(outcomes),
    }


def markdown_report(data: dict) -> str:
    run = data["run"]
    routes = [event for event in data["events"] if event["kind"] == "route.completed"]
    lines = [
        f"# Sunday run {run['id']}", "", f"- Task: `{run['task_ref']}`",
        f"- Project: `{run['project']}`", f"- Host: `{run['host']}`",
        f"- State: `{run['state']}`",
        f"- Worktree: `{run.get('worktree') or 'not created'}`",
        f"- Sunday version: `{data['installation']['version']}`",
        f"- Model retries: `{data['reliability']['model_retries']}`",
        f"- Reconciled effects: `{data['reliability']['reconciled_effects']}`",
        "", "## Route ledger", "",
        "| Phase | Agent | Requested | Observed | Verification | Accepted | Duration |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for event in routes:
        route = event["payload"]
        lines.append(
            f"| {route.get('phase')} | {route.get('agent')} | {route.get('model')} | "
            f"{route.get('observed_model') or 'not reported'} | "
            f"{route.get('verification_status') or ('confirmed' if route.get('model_verified') else 'unknown')} | "
            f"{route.get('accepted')} | "
            f"{route.get('duration_seconds')}s |"
        )
    lines.extend(["", "## External effects", ""])
    for effect in data.get("effects", []):
        lines.append(
            f"- `{effect.get('effect_key')}`: `{effect.get('status')}`"
        )
    lines.extend(["", "## Events", ""])
    for event in data["events"]:
        lines.append(f"- `{event['timestamp']}` `{event['kind']}` `{event.get('phase') or ''}`")
    return "\n".join(lines) + "\n"


def write_report(store: RunStore, run_id: str, destination: Path, format_name: str) -> Path:
    data = report_data(store, run_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if format_name == "json":
        destination.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        destination.write_text(markdown_report(data), encoding="utf-8")
    return destination
