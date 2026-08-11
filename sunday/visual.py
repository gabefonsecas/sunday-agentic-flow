"""Visual route timelines for terminal, Markdown, and Mermaid."""

from __future__ import annotations

import json

from sunday.routing import ModelRouter
from sunday.state import RunStore

ROUTED_PHASES = ("discovery", "implementation", "verification", "review")
PHASE_LABELS = {
    "discovery": "Discovery",
    "implementation": "Implementation",
    "verification": "Verification",
    "review": "Review",
}


def route_data(store: RunStore, run_id: str) -> dict:
    run = store.get(run_id)
    events = store.events(run_id)
    rows = []
    for phase in ROUTED_PHASES:
        started = [
            event["payload"] for event in events
            if event["kind"] == "route.started" and event["phase"] == phase
        ]
        completed = [
            event["payload"] for event in events
            if event["kind"] == "route.completed" and event["phase"] == phase
        ]
        accepted = next((entry for entry in reversed(completed) if entry.get("accepted")), None)
        active = len(started) > len(completed)
        if accepted:
            status = "completed"
        elif active:
            status = "active"
        elif completed:
            status = "failed"
        else:
            status = "pending"
        router = ModelRouter(run.host)
        pool = [candidate.model for candidate in router.pool(phase)]
        used = [entry.get("model", "unknown") for entry in completed]
        if active:
            used.append(started[-1].get("model", "unknown"))
        rows.append({
            "phase": phase,
            "label": PHASE_LABELS[phase],
            "status": status,
            "used": used,
            "selected": accepted.get("observed_model") or accepted.get("model") if accepted else None,
            "pool": pool,
            "attempts": len(completed),
            "duration_seconds": round(sum(float(entry.get("duration_seconds") or 0) for entry in completed), 3),
        })
    return {
        "run_id": run.id,
        "task_ref": run.task_ref,
        "host": run.host,
        "state": run.state,
        "phases": rows,
    }


def terminal_routes(data: dict) -> str:
    markers = {"completed": "[OK]", "active": "[>>]", "failed": "[!!]", "pending": "[--]"}
    lines = [
        f"Sunday {data['run_id']}  host={data['host']}  state={data['state']}",
        "",
    ]
    for phase in data["phases"]:
        used = " -> ".join(phase["used"]) or "not started"
        pool = " -> ".join(phase["pool"])
        lines.append(f"{markers[phase['status']]} {phase['label']}")
        lines.append(f"     used: {used}")
        lines.append(f"     pool: {pool}")
    return "\n".join(lines)


def markdown_routes(data: dict) -> str:
    lines = [
        f"## Sunday route {data['run_id']}", "",
        f"Host: `{data['host']}`. State: `{data['state']}`.", "",
        "| Status | Phase | Used transition | Available pool |",
        "| --- | --- | --- | --- |",
    ]
    for phase in data["phases"]:
        used = " → ".join(f"`{model}`" for model in phase["used"]) or "Not started"
        pool = " → ".join(f"`{model}`" for model in phase["pool"])
        lines.append(f"| {phase['status']} | {phase['label']} | {used} | {pool} |")
    return "\n".join(lines) + "\n"


def mermaid_routes(data: dict) -> str:
    lines = ["flowchart LR"]
    previous = None
    for index, phase in enumerate(data["phases"]):
        models = " → ".join(phase["used"]) or "not started"
        node = f"p{index}"
        label = f"{phase['label']}<br/>{phase['status']}<br/>{models}".replace('"', "'")
        lines.append(f'    {node}["{label}"]')
        if previous:
            lines.append(f"    {previous} --> {node}")
        previous = node
    return "```mermaid\n" + "\n".join(lines) + "\n```\n"


def render_routes(store: RunStore, run_id: str, format_name: str = "terminal") -> str:
    data = route_data(store, run_id)
    if format_name == "json":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if format_name == "markdown":
        return markdown_routes(data)
    if format_name == "mermaid":
        return mermaid_routes(data)
    return terminal_routes(data) + "\n"


def live_route_line(kind: str, payload: dict) -> str:
    phase = PHASE_LABELS.get(str(payload.get("phase")), str(payload.get("phase", "route")))
    model = payload.get("observed_model") or payload.get("model", "unknown")
    position = f"{payload.get('pool_position', '?')}/{payload.get('pool_size', '?')}"
    if kind == "route.started":
        return f"[>>] {phase}: {model}  pool={position}  reason={payload.get('reason', 'phase default')}"
    marker = "[OK]" if payload.get("accepted") else "[!!]"
    duration = payload.get("duration_seconds", 0)
    return f"{marker} {phase}: {model}  duration={duration}s  accepted={bool(payload.get('accepted'))}"
