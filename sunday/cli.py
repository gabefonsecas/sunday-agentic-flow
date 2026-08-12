"""Sunday command-line interface."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

from sunday.config import config_path, load_settings
from sunday.diagnostics import doctor
from sunday.engine import SundayEngine
from sunday.installation import check_update, install, rollback, uninstall, update
from sunday.reporting import write_report
from sunday.state import RunStore
from sunday.visual import live_route_line, render_routes
from sunday.worktrees import cleanup_worktrees


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="sunday", description="Deterministic agentic development orchestration")
    root.add_argument("--config", type=Path, help="Configuration TOML path")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("install", help="Install Sunday globally")
    upgrade = commands.add_parser("update", help="Update or roll back Sunday")
    update_mode = upgrade.add_mutually_exclusive_group()
    update_mode.add_argument("--check", action="store_true", help="Check releases without changing files")
    update_mode.add_argument(
        "--rollback", nargs="?", const="", metavar="VERSION",
        help="Restore the previous or selected installed version",
    )
    commands.add_parser("uninstall", help="Remove managed Sunday files")
    health = commands.add_parser("doctor", help="Validate the complete environment")
    health.add_argument("--network", action="store_true")
    health.add_argument(
        "--models", action="store_true",
        help="Probe every configured model using read-only executions",
    )
    run = commands.add_parser("run", help="Execute one Friday task")
    run.add_argument("task")
    run.add_argument("--project")
    run.add_argument("--host", default="auto", choices=("auto", "codex", "claude", "gemini", "antigravity"))
    create = commands.add_parser("create", help="Create agentically detailed Friday tasks")
    create.add_argument("request")
    create.add_argument("--project")
    create.add_argument("--host", default="auto", choices=("auto", "codex", "claude", "gemini", "antigravity"))
    create.add_argument("--count", type=int, default=1)
    create.add_argument("--execute", action="store_true", help="Start the first created task")
    create.add_argument("--no-assign", action="store_true", help="Leave created tasks unassigned")
    create.add_argument("--allow-duplicate", action="store_true")
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
    status.add_argument("--visual", action="store_true", help="Show the model route timeline")
    status.add_argument("--json", action="store_true", help="Output raw JSON format")
    routes = commands.add_parser("routes", help="Show visual model transitions")
    routes.add_argument("run_id", nargs="?")
    routes.add_argument(
        "--format", choices=("terminal", "markdown", "mermaid", "json"), default="terminal"
    )
    review = commands.add_parser("review", help="Run an independent branch or PR review")
    review.add_argument("reference")
    review.add_argument("--project")
    review.add_argument("--host", default="auto", choices=("auto", "codex", "claude", "gemini", "antigravity"))
    report = commands.add_parser("report", help="Export an auditable run report")
    report.add_argument("run_id")
    report.add_argument("--format", choices=("json", "markdown"), default="markdown")
    report.add_argument("--output", type=Path)
    cleanup = commands.add_parser("cleanup", help="Remove eligible completed worktrees")
    cleanup.add_argument("--run-id")
    cleanup.add_argument("--older-than", type=int, metavar="DAYS")
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


def _format_run_status(store: RunStore, run_id: str) -> str:
    run = store.get(run_id)
    events = store.events(run_id)
    meta = run.metadata or {}
    title = meta.get("title") or f"Task {run.task_ref}"
    task_id = meta.get("task_id") or run.task_ref
    branch = meta.get("branch") or "N/A"
    pr = meta.get("pull_request") or {}
    pr_url = pr.get("url") if isinstance(pr, dict) else None

    last_error = None
    for event in reversed(events):
        p = event.get("payload") or {}
        if isinstance(p, dict):
            err = p.get("error") or p.get("reason")
            if err:
                last_error = str(err)
                break

    state_str = run.state.upper()
    if run.resume_state and run.state == "paused":
        state_str += f" (Resume target: {run.resume_state})"

    lines = [
        "=" * 70,
        f"  SUNDAY RUN STATUS: {run.id[:8]} ({run.id})",
        "=" * 70,
        f"  Task:          #{task_id} - {title}",
        f"  Project:       {run.project or 'N/A'}",
        f"  Host:          {run.host or 'N/A'}",
        f"  State:         {state_str}",
        f"  Branch:        {branch}",
        f"  Pull Request:  {pr_url or 'Not created'}",
        f"  Created At:    {run.created_at}",
        f"  Updated At:    {run.updated_at}",
    ]

    if last_error:
        lines.extend([
            "-" * 70,
            "  [!] Blocked / Pause Reason:",
            f"      {last_error}",
        ])
        if "SAML" in last_error or "Resource protected" in last_error or "gh auth" in last_error:
            lines.extend([
                "",
                "  [->] Action Required:",
                "      1. Authorize SAML SSO in your browser using the link above.",
                f"      2. Resume execution: sunday resume {run.id[:8]}",
            ])
        elif run.state == "paused":
            lines.extend([
                "",
                "  [->] Action Required:",
                f"      Resume execution: sunday resume {run.id[:8]}",
            ])

    lines.extend(["=" * 70, ""])
    return "\n".join(lines)


def _format_runs_table(runs: list) -> str:
    if not runs:
        return "No Sunday runs found.\n"
    lines = [
        "=" * 85,
        f"{'ID':<10} {'TASK':<8} {'PROJECT':<12} {'HOST':<8} {'STATE':<12} {'PR':<25}",
        "=" * 85,
    ]
    for r in runs:
        meta = r.metadata or {}
        pr = meta.get("pull_request") or {}
        pr_url = str(pr.get("url") if isinstance(pr, dict) and pr.get("url") else "-")
        if len(pr_url) > 25:
            pr_url = pr_url[:22] + "..."
        r_id = str(r.id or "")[:8]
        project_str = str(r.project or "-")
        host_str = str(r.host or "-")
        state_str = str(r.state or "-")
        task_str = str(meta.get("task_id") or r.task_ref or "-")
        lines.append(
            f"{r_id:<10} {task_str:<8} {project_str:<12} {host_str:<8} {state_str:<12} {pr_url:<25}"
        )
    lines.extend(["=" * 85, ""])
    return "\n".join(lines)


def _progress(kind: str, payload: dict) -> None:
    if not os.environ.get("SUNDAY_NO_PROGRESS"):
        print(live_route_line(kind, payload), file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "install":
        _json(install())
        return
    if args.command == "update":
        if args.check:
            _json(check_update())
        elif args.rollback is not None:
            _json(rollback(args.rollback or None))
        else:
            _json(update())
        return
    if args.command == "uninstall":
        _json(uninstall())
        return
    if args.command == "doctor":
        result = doctor(args.network, args.models)
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
    store = RunStore(
        lease_seconds=settings.lease_ttl_seconds,
        heartbeat_seconds=settings.lease_heartbeat_seconds,
    )
    engine = SundayEngine(settings, store=store, progress=_progress)
    if args.command == "routes":
        run_id = args.run_id
        if not run_id:
            recent = store.list(limit=1)
            if not recent:
                raise RuntimeError("No Sunday runs found")
            run_id = recent[0].id
        print(render_routes(store, run_id, args.format), end="")
        return
    if args.command == "status":
        if args.visual:
            run_id = args.run_id
            if not run_id:
                recent = store.list(limit=1)
                if not recent:
                    raise RuntimeError("No Sunday runs found")
                run_id = recent[0].id
            print(render_routes(store, run_id), end="")
            return
        if args.json:
            _json(_run_dict(store.get(args.run_id)) if args.run_id else [_run_dict(run) for run in store.list()])
        elif args.run_id:
            print(_format_run_status(store, args.run_id))
        else:
            print(_format_runs_table(store.list()))
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
    if args.command == "cleanup":
        older_than = args.older_than
        if older_than is None and not args.run_id:
            older_than = settings.completed_worktree_retention_days
        _json(cleanup_worktrees(store, args.run_id, older_than))
        return
    if args.command == "resume":
        run = store.get(args.run_id)
        project = settings.project_for(run.project)
        if args.retry_uncertain:
            store.retry_effects(run.id)
        _json(_run_dict(engine.resume(run.id, project, args.approve)))
        return
    project = settings.project_for(getattr(args, "project", None))
    if args.command in {"create", "run", "watch"}:
        from sunday.autoconfig import AutoConfigurationService, needs_configuration
        if needs_configuration(project):
            request = (
                args.request if args.command == "create"
                else f"Execute existing Friday task {args.task}" if args.command == "run"
                else "Watch this project's ready Friday development tasks"
            )
            project = AutoConfigurationService(settings).configure(
                project.repository, request, args.host, args.config or config_path()
            )
    if args.command == "create":
        from sunday.task_creation import TaskCreationService
        service = TaskCreationService(settings, store=store)
        result = service.create(
            args.request, project, args.host, args.count,
            assign=not args.no_assign, allow_duplicate=args.allow_duplicate,
        )
        if args.execute:
            engine.tasks = service.tasks
            run = engine.start(str(result["tasks"][0]["id"]), project, args.host)
            result["run"] = _run_dict(run)
        _json(result)
        return
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
            for task in adapter.list_ready_tasks(
                project.ready_label, int(project.board_id),
                str(project.states.get("completed", "")),
            ):
                reference = str(task["id"])
                previous = store.latest_for_task(reference)
                if previous and previous.state in {"completed", "paused", "failed"}:
                    continue
                try:
                    _json(_run_dict(engine.start(reference, project, args.host)))
                except RuntimeError as exc:
                    print(f"Sunday watcher skipped {reference}: {exc}", file=sys.stderr)
            if args.once:
                return
            time.sleep(settings.watcher_interval)
