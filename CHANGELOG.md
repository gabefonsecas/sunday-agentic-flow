# Changelog

## Unreleased

## 1.0.2

- Fixed Codex JSONL parsing for escaped `SUNDAY_RESULT` and `SUNDAY_STORIES` payloads.
- Accepted valid Sunday markers followed by host metadata without weakening malformed-output checks.
- Allowed checksum-verified updates on GitHub CLI versions without the `attestation` command.

## 1.0.1

- Moved the WSL 2 release gate to an ephemeral GitHub-hosted Windows runner.
- Added release tag/version validation before artifact publication.

## 1.0.0

- Added per-run Git worktrees and scoped commits.
- Added expiring task leases, heartbeats, recovery, and SQLite backups.
- Added automatic Friday and GitHub effect reconciliation.
- Added resilient Friday SSE retries, timeouts, and safe shutdown.
- Added verified model probes with requested and observed evidence.
- Added release-based updates, checksums, provenance, and rollback.
- Added safe worktree cleanup and richer reliability reports.
- Added live smoke and WSL 2 release gates.
- Added live model-transition output and terminal, Markdown, Mermaid, and JSON route dashboards.
- Expanded Codex pools across GPT-5.4 mini, GPT-5.4, GPT-5.5, and GPT-5.6.
- Expanded Claude, Gemini, and Antigravity pools across economy through deep tiers.
- Added deterministic complexity classification before model selection.
- Marked Friday, Git, and GitHub effects explicitly as model-free operations.
- Added risk-aware routing and retry handling for host execution exceptions.
- Added AI-assisted first-run Friday configuration using only the token and repository context.
- Added strict live-catalog validation and atomic `config.toml` persistence.
- Scoped the watcher to all non-completed tasks assigned to the token user on the selected board.
- Changed the IA checkbox from an execution trigger into an audit marker set by Sunday.
- Added Friday status-column transitions while preserving legacy group-based workflows.
- Added the real Squad Mustafar status mapping to the configuration tutorial.
- Standardized the runtime on Python 3.11 or newer.
- Added conversational Friday task creation through Sunday skills.
- Added current Git repository inference and a reusable default Friday mapping.
- Added model-assisted task detailing, token-based assignment, and create-then-execute flow.
- Added durable, marker-based idempotency and partial-failure reconciliation for card creation.

- Renamed the product and all public calls to Sunday.
- Added a durable SQLite workflow state machine.
- Added resumable, idempotent Friday and GitHub effects.
- Added real headless model routing across supported hosts.
- Added Friday watcher execution using explicit labels.
- Added dynamic token identity and validated email fallback.
- Added transactional install, update, uninstall, and doctor commands.
- Added local telemetry, JSON reports, and Markdown reports.
- Added Linux, WSL, Windows x64, and macOS test coverage.
