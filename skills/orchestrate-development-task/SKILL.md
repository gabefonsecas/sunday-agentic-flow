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
2. Discover the repository through the `discover-project-context` workflow.
3. Resolve the Friday workspace, board, groups, and relevant columns.
4. Convert the request into stories through `write-and-publish-stories`.
5. Order stories by dependencies and risk.
6. Execute each story through `execute-managed-story`.
7. Deliver one coherent PR through `deliver-pull-request`.
8. Run `review-branch` before declaring completion.
9. Synchronize final evidence and PR link with Friday.

## Control rules

- Treat current repository files as implementation truth.
- Treat Friday as workflow-state truth.
- Read every applicable instruction file before editing.
- Use read-only discovery before external mutations.
- Never invent IDs, group meanings, column IDs, checks, or URLs.
- Keep card state aligned with actual work state.
- Request direction only when a decision changes product scope.
- Stop before destructive administration or ambiguous publication.

## Model collaboration

Use `optimize-model-collaboration` automatically for discovery, implementation,
verification, architecture, and review. Route each bounded role to a suitable
remote model exposed by the active host. The primary agent owns external state,
final synthesis, and all user-visible decisions.

## Completion contract

Finish only when implementation, relevant checks, review, pushed branch, PR,
and Friday updates are verified. Report residual risks explicitly.
