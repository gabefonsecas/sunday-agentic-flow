# Changelog

## Unreleased

- Added AI-assisted first-run Friday configuration using only the token and repository context.
- Added strict live-catalog validation and atomic `config.toml` persistence.
- Scoped the watcher to all non-completed tasks assigned to the token user on the selected board.
- Changed the IA checkbox from an execution trigger into an audit marker set by Sunday.
- Added Friday status-column transitions while preserving legacy group-based workflows.
- Added the real Squad Mustafar status mapping to the configuration tutorial.
- Added Python 3.10 and Ubuntu 22.04/WSL compatibility through `tomli`.
- Replaced the missing `tomllib` traceback with an actionable installer diagnostic.
- Added conversational Friday task creation through Sunday skills.
- Added current Git repository inference and a reusable default Friday mapping.
- Added model-assisted task detailing, token-based assignment, and create-then-execute flow.
- Added durable, marker-based idempotency and partial-failure reconciliation for card creation.

## 1.0.0

- Renamed the product and all public calls to Sunday.
- Added a durable SQLite workflow state machine.
- Added resumable, idempotent Friday and GitHub effects.
- Added real headless model routing across supported hosts.
- Added Friday watcher execution using explicit labels.
- Added dynamic token identity and validated email fallback.
- Added transactional install, update, uninstall, and doctor commands.
- Added local telemetry, JSON reports, and Markdown reports.
- Added Linux, WSL, Windows x64, and macOS test coverage.
