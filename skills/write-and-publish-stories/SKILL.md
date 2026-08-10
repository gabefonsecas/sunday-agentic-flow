---
name: write-and-publish-stories
description: Create agentically detailed Friday tasks from natural-language requests. Use whenever the user says "Sunday, crie uma tarefa", asks to create a card or stories in Friday, or wants a vague feature, bug, refactor, or maintenance request registered for the current repository.
---

# Write and publish stories

Read `references/story-template.md` before publishing.
Treat the user's current working directory as the target project unless they explicitly name another one.
Do not ask the user to run or copy a Sunday command.

1. Preserve the complete natural-language request.
2. Infer the project from the nearest Git root in the current directory.
3. Invoke `sunday create "<request>"` internally.
4. Add `--count N` when the user requests an exact number of tasks.
5. Add `--execute` when the user asks to create and start the work.
6. Add `--no-assign` only when the user explicitly asks to leave it unassigned.
7. Report the created Friday item IDs, titles, inferred project, assignment, and run ID when present.

Sunday reads repository instructions, asks its task analyst to enrich vague requirements,
publishes idempotently, and assigns the cards to the user resolved from the Friday token.
Do not reproduce those steps manually when the Sunday runtime is available.

Do not create workspaces, boards, groups, or columns implicitly.
Do not pass `--allow-duplicate` without an explicit request for another copy.
Only ask a question when multiple configured Friday mappings fit the same repository.
