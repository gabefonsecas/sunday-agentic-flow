---
name: orchestrate-development-task
description: Automatically orchestrate every actionable software development request from sparse requirements through repository discovery, Friday story publication, implementation, validation, pull request delivery, review, and Friday synchronization. Trigger implicitly for features, bugs, refactors, maintenance, migrations, and delivery work across Codex, Claude Code, Gemini CLI, or Google Antigravity. The user never needs to name this skill or provide a workflow prompt.
---

# Orchestrate a development task

Own the workflow until its authorized outcome is verified.
Start automatically when the user describes development work.
Do not require a skill name, template, or orchestration prompt.

## Workflow

1. Read `references/operating-contract.md`.
2. Read `references/host-dispatch.md`.
3. Dispatch the configured task analyst before planning.
4. Resolve the Friday workspace, board, groups, and relevant columns.
5. Convert the request into stories through `write-and-publish-stories`.
6. Order stories by dependencies and risk.
7. Dispatch the configured implementation worker for each coding unit.
8. Execute each story through `execute-managed-story`.
9. Dispatch the configured implementation verifier after code changes.
10. Deliver one coherent PR through `deliver-pull-request`.
11. Dispatch the configured branch reviewer before completion.
12. Run `review-branch` using the independent review result.
13. Synchronize final evidence and PR link with Friday.

## Control rules

- Treat current repository files as implementation truth.
- Treat Friday as workflow-state truth.
- Read every applicable instruction file before editing.
- Use read-only discovery before external mutations.
- Never invent IDs, group meanings, column IDs, checks, or URLs.
- Keep card state aligned with actual work state.
- Assign the configured Friday user when execution begins.
- Request direction only when a decision changes product scope.
- Stop before destructive administration or ambiguous publication.

## Model collaboration

Use `optimize-model-collaboration` automatically for every managed task.
The four dispatch phases are mandatory when subagents are available.
Each phase must use a fresh specialist context.
Do not replace dispatch with silent primary-model reasoning.
Record requested agent, tier, and reported model in the route ledger.
If dispatch is unavailable, record degraded mode explicitly.
The primary agent owns external state and final synthesis.

## Completion contract

Finish only when implementation, relevant checks, review, pushed branch, PR,
and Friday updates are verified. Report residual risks explicitly.
