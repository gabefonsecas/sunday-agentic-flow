---
name: execute-managed-story
description: Implement a Friday-managed development story inside a repository while obeying project instructions, preserving user changes, running proportionate validation, and synchronizing card state. Use when a specific story or Friday item is ready for coding.
---

# Execute a managed story

1. Fetch or confirm the Friday item and acceptance criteria.
2. Resolve the board's groups and current item location.
3. Move the item to the existing in-progress group.
4. Recheck scoped project instructions for intended files.
5. Implement the smallest coherent change.
6. Add or update tests covering changed behavior.
7. Run focused checks, then broader required checks.
8. Inspect the final diff for unrelated changes and secrets.
9. Add a Friday comment using `references/progress-comments.md`.
10. Move the item to the review-ready group only after checks pass.

If checks fail, keep the item in progress. Record the failure and evidence.
Never discard or overwrite unrelated user modifications.
Never mark completion based only on code generation.
