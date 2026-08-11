---
name: sunday-development-task
description: Start or inspect deterministic Sunday development runs from Friday tasks. Use implicitly for features, bugs, refactors, maintenance, migrations, reviews, and delivery work requiring repository discovery, stories, implementation, verification, pull requests, or Friday synchronization across Codex, Claude, Gemini, or Antigravity.
---

# Run a Sunday development task

Use the Sunday runtime as workflow authority.
Do not reproduce its state machine manually.

1. Read `references/operating-contract.md`.
2. Read `references/host-dispatch.md` when route evidence matters.
3. Infer the target project from the nearest Git root in the current directory.
4. Let Sunday perform AI-assisted Friday configuration automatically on the first execution.
5. Never ask the user to discover workspace, board, group, column, or status IDs manually.
6. If the user has no Friday item yet, invoke `sunday create "<request>"` internally.
7. Add `--execute` when the user asks to create and start the work.
8. If the user supplied an existing Friday item ID or URL, invoke `sunday run <item>` internally.
9. Run `sunday doctor` internally when environment health is unknown.
10. Report Friday item IDs, the returned run ID, and current state.
11. Use `sunday status <run-id>` for structured status requests.
12. Use `sunday routes <run-id> --format markdown` for model status requests.
13. Use Mermaid when the host can render diagrams.
14. Use `sunday resume <run-id>` after recoverable failures.
15. Require explicit approval before passing `--approve`.
16. Require reconciliation before `--retry-uncertain`.

Never make the user translate a natural-language request into Sunday CLI syntax.

Never bypass Sunday for model dispatch, Friday transitions, Git publication,
or pull request delivery. Sunday owns idempotency and evidence.
