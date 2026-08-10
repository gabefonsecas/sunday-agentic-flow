# Operating contract

## Required state sequence

`intake -> understood -> planned -> published -> in progress -> validated -> PR open -> reviewed`

Map these semantic states onto existing Friday groups. Never create or rename
groups unless explicitly requested.

## Evidence ledger

Keep these facts during execution:

- Request and resolved scope.
- Repository root and applicable instruction files.
- Friday workspace, board, group, item, and column IDs.
- Configured assignee email, resolved member ID, and assignment result.
- Branch name, base branch, and commit SHA.
- Commands run and their outcomes.
- PR URL and final Friday changes.
- Model route entries for discovery, implementation, verification, and review.

## Assignment gate

When a story enters execution, call `assign_configured_user` with its
workspace, board, and item IDs. Do not begin implementation before the tool
returns `assigned: true`. Never guess a user or people-column ID.

## Model route gate

Each required phase uses a new host subagent.
Record the requested tier and observed outcome.
Do not claim a transition without an invoked specialist result.

## Recovery

If a step fails, preserve the current card state. Add a concise Friday comment
with the failure, evidence, and next safe action. Never move a failed story to
the completed group.
