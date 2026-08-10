---
name: sunday-development-task
description: Start or inspect deterministic Sunday development runs from Friday tasks. Use implicitly for features, bugs, refactors, maintenance, migrations, reviews, and delivery work requiring repository discovery, stories, implementation, verification, pull requests, or Friday synchronization across Codex, Claude, Gemini, or Antigravity.
---

# Run a Sunday development task

Use the Sunday runtime as workflow authority.
Do not reproduce its state machine manually.

1. Read `references/operating-contract.md`.
2. Read `references/host-dispatch.md` when route evidence matters.
3. Resolve the Friday item ID or URL.
4. Run `sunday doctor` when environment health is unknown.
5. Run `sunday run <item> --project <name>`.
6. Report the returned run ID and current state.
7. Use `sunday status <run-id>` for status requests.
8. Use `sunday resume <run-id>` after recoverable failures.
9. Require explicit approval before passing `--approve`.
10. Require reconciliation before `--retry-uncertain`.

Never bypass Sunday for model dispatch, Friday transitions, Git publication,
or pull request delivery. Sunday owns idempotency and evidence.
