"""Auditable JSON and Markdown run reports."""

import json
from pathlib import Path

from sunday.state import RunStore
from sunday.routing import ModelRouter


def report_data(store: RunStore, run_id: str) -> dict:
    run = store.get(run_id)
    events = store.events(run_id)
    outcomes = [event["payload"] for event in events if event["kind"] == "route.completed"]
    return {
        "run": {
            "id": run.id, "task_ref": run.task_ref, "project": run.project,
            "host": run.host, "state": run.state, "created_at": run.created_at,
            "updated_at": run.updated_at, "metadata": run.metadata,
        },
        "events": events,
        "routing_recommendation": ModelRouter(run.host).recommendation(outcomes),
    }


def markdown_report(data: dict) -> str:
    run = data["run"]
    routes = [event for event in data["events"] if event["kind"] == "route.completed"]
    lines = [
        f"# Sunday run {run['id']}", "", f"- Task: `{run['task_ref']}`",
        f"- Project: `{run['project']}`", f"- Host: `{run['host']}`",
        f"- State: `{run['state']}`", "", "## Route ledger", "",
        "| Phase | Agent | Requested | Observed | Accepted | Duration |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for event in routes:
        route = event["payload"]
        lines.append(
            f"| {route.get('phase')} | {route.get('agent')} | {route.get('model')} | "
            f"{route.get('observed_model') or 'not reported'} | {route.get('accepted')} | "
            f"{route.get('duration_seconds')}s |"
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
