---
name: deliver-pull-request
description: Prepare, push, and open a pull request for completed development work, select main or homolog from task intent and repository evidence, and attach the verified PR URL to Friday. Use after implementation and validation are complete.
---

# Deliver a pull request

Read `references/branch-policy.md` before selecting the base.

1. Confirm clean scope and preserve unrelated changes.
2. Confirm all required checks passed.
3. Create or use a focused branch following repository conventions.
4. Commit only authorized files with an intentional message.
5. Resolve the base branch from task intent and repository evidence.
6. Push the branch and verify the remote ref.
7. Open a draft PR if review work remains. Otherwise open a ready PR.
8. Include summary, story links, validation, risks, and rollout notes.
9. Verify the PR URL and base branch from the hosting service.
10. Call Friday `list_columns` for the board.
11. Write the URL using `update_cell_value` when a clear link column exists.
12. Always add a concise `add_comment` containing the verified PR URL.
13. Move stories only to the existing review group.

Do not create a new Friday column implicitly.
Do not claim a PR exists before verifying its URL.
