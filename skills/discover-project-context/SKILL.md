---
name: discover-project-context
description: Discover a software project's operative context before planning or editing. Use when entering any unfamiliar repository, interpreting a vague development request, locating nested agent instructions, identifying architecture and test commands, or determining Git and pull request conventions.
---

# Discover project context

Produce an evidence-backed project brief before edits.

1. Resolve the repository root and current Git state.
2. Find `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, nested instruction files,
   project configuration, and contribution guidance.
3. Read root instructions, then nearer scoped instructions.
4. Inventory languages, package managers, entry points, tests, linting,
   formatting, build commands, CI, database migrations, and deployment files.
5. Inspect nearby implementation and tests matching the request.
6. Identify dirty files and preserve unrelated user changes.
7. Inspect branches, remotes, default branch, and evidence for `homolog`.
8. Return the brief defined in `references/context-brief.md`.

Do not edit files, create branches, or update Friday during discovery.
Do not infer commands when repository configuration can verify them.
