"""Sunday command-line interface."""

import argparse
import json
from pathlib import Path
import sys
import time

from sunday.config import load_settings
from sunday.diagnostics import doctor
from sunday.engine import SundayEngine
from sunday.installation import install, uninstall, update
from sunday.reporting import write_report
from sunday.state import RunStore


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="sunday", description="Deterministic agentic development orchestration")
    root.add_argument("--config", type=Path, help="Configuration TOML path")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("install", help="Install Sunday globally")
    commands.add_parser("update", help="Update and reinstall Sunday")
    commands.add_parser("uninstall", help="Remove managed Sunday files")
    health = commands.add_parser("doctor", help="Validate the complete environment")
    health.add_argument("--network", action="store_true")
    run = commands.add_parser("run", help="Execute one Friday task")
    run.add_argument("task")
    run.add_argument("--project")
    run.add_argument("--host", default="auto", choices=("auto", "codex", "claude", "gemini", "antigravity"))
    watch = commands.add_parser("watch", help="Watch labeled Friday tasks")
    watch.add_argument("--project")
    watch.add_argument("--host", default="auto", choices=("auto", "codex", "claude", "gemini", "antigravity"))
    watch.add_argument("--once", action="store_true")
    resume = commands.add_parser("resume", help="Resume a paused run")
    resume.add_argument("run_id")
    resume.add_argument("--approve", action="store_true", help="Approve the recorded high-risk gate")
    resume.add_argument("--retry-uncertain", action="store_true", help="Retry effects after manual reconciliation")
    fail = commands.add_parser("fail", help="Close a paused run as failed")
    fail.add_argument("run_id")
    fail.add_argument("--reason", required=True)
    status = commands.add_parser("status", help="Show recent or selected runs")
    status.add_argument("run_id", nargs="?")
    review = commands.add_parser("review", help="Run an independent branch or PR review")
    review.add_argument("reference")
    review.add_argument("--project")
    review.add_argument("--host", default="auto", choices=("auto", "codex", "claude", "gemini", "antigravity"))
    report = commands.add_parser("report", help="Export an auditable run report")
    report.add_argument("run_id")
    report.add_argument("--format", choices=("json", "markdown"), default="markdown")
    report.add_argument("--output", type=Path)
    friday = commands.add_parser("friday", help="Inspect Friday configuration data")
    friday.add_argument("--workspace", type=int)
    friday.add_argument("--board", type=int)
    friday.add_argument("--my-tasks", action="store_true")
    return root


def _run_dict(run) -> dict:
    return {
        "id": run.id, "task_ref": run.task_ref, "project": run.project,
        "host": run.host, "state": run.state, "resume_state": run.resume_state,
        "created_at": run.created_at, "updated_at": run.updated_at,
        "pull_request": run.metadata.get("pull_request"),
    }


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "install":
        _json(install())
        return
    if args.command == "update":
        _json(update())
        return
    if args.command == "uninstall":
        _json(uninstall())
        return
    if args.command == "doctor":
        result = doctor(args.network)
        _json(result)
        raise SystemExit(0 if result["healthy"] else 1)
    if args.command == "friday":
        from sunday.adapters.friday import FridayMCPClient
        client = FridayMCPClient()
        result = {"workspaces": client.tool("list_workspaces", {})}
        if args.workspace:
            result["boards"] = client.tool("list_boards", {"workspace_id": args.workspace})
        if args.board:
            result["groups"] = client.tool("list_groups", {"board_id": args.board})
            result["columns"] = client.tool("list_columns", {"board_id": args.board})
        if args.my_tasks:
            result["my_tasks"] = client.tool("list_my_tasks", {})
        _json(result)
        return
    settings = load_settings(args.config)
    store = RunStore()
    engine = SundayEngine(settings, store=store)
    if args.command == "status":
        _json(_run_dict(store.get(args.run_id)) if args.run_id else [_run_dict(run) for run in store.list()])
        return
    if args.command == "fail":
        run = store.get(args.run_id)
        if run.state != "paused":
            raise RuntimeError("Only paused runs can be closed as failed")
        _json(_run_dict(store.transition(run.id, "failed", {"reason": args.reason})))
        return
    if args.command == "report":
        if args.output:
            destination = args.output
        else:
            suffix = "json" if args.format == "json" else "md"
            destination = Path.cwd() / f"sunday-report-{args.run_id}.{suffix}"
        _json({"report": str(write_report(store, args.run_id, destination, args.format))})
        return
    if args.command == "resume":
        run = store.get(args.run_id)
        project = settings.project_for(run.project)
        if args.retry_uncertain:
            store.retry_effects(run.id)
        _json(_run_dict(engine.resume(run.id, project, args.approve)))
        return
    project = settings.project_for(getattr(args, "project", None))
    if args.command == "run":
        _json(_run_dict(engine.start(args.task, project, args.host)))
        return
    if args.command == "review":
        _json(_run_dict(engine.review_only(args.reference, project, args.host)))
        return
    if args.command == "watch":
        from sunday.adapters.friday import FridayAdapter
        adapter = FridayAdapter()
        engine.tasks = adapter
        while True:
            for task in adapter.list_ready_tasks(project.ready_label):
                reference = str(task["id"])
                previous = store.latest_for_task(reference)
                if previous and previous.state in {"completed", "paused"}:
                    continue
                try:
                    _json(_run_dict(engine.start(reference, project, args.host)))
                except RuntimeError as exc:
                    print(f"Sunday watcher skipped {reference}: {exc}", file=sys.stderr)
            if args.once:
                return
            time.sleep(settings.watcher_interval)
