# Operating contract

## Required state sequence

`intake -> discovery -> stories -> publication -> implementation -> verification -> review -> pull_request -> completed`

Map semantic states onto a Friday status column when `status_column` is configured.
Use group movement only for legacy boards whose groups represent workflow states.
Never create or rename groups, columns, or status options unless explicitly requested.

## Evidence ledger

Keep these facts during execution:

- Request and resolved scope.
- Repository root and applicable instruction files.
- Friday workspace, board, group, item, and column IDs.
- Token-resolved assignee email, member ID, and assignment result.
- Branch name, base branch, and commit SHA.
- Commands run and their outcomes.
- PR URL and final Friday changes.
- Model route entries for discovery, implementation, verification, and review.

## Assignment gate

Sunday resolves identity from the token before implementation.
No fixed Friday user ID is permitted.

## First-run configuration gate

Use the discovery model to select a mapping from the live Friday catalog and current repository.
Validate every selected workspace, board, group, column, and status option before persisting it.
Never require manual ID discovery when a token and supported host are available.

## Model route gate

Each required phase uses a new headless host execution.
Record the requested tier and observed outcome.
Do not claim a transition without an invoked specialist result.

## Recovery

Sunday pauses recoverable failures and preserves evidence.
Uncertain effects require explicit reconciliation before retry.
