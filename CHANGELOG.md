# Changelog

## Unreleased

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
