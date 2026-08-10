---
name: write-and-publish-stories
description: Turn vague software work into small executable stories and publish them into Friday. Use when a feature, bug, refactor, or maintenance request lacks acceptance criteria, decomposition, dependencies, validation evidence, or task cards.
---

# Write and publish stories

Read `references/story-template.md` before publishing.

1. Use the project context and original request as inputs.
2. Separate observable outcomes from implementation choices.
3. State assumptions only when they are reversible.
4. Split work into independently verifiable stories.
5. Include acceptance criteria, exclusions, dependencies, risks, and checks.
6. Call Friday `list_workspaces`, `list_boards`, and `list_groups`.
7. Reuse the requested board and intake group.
8. Call `create_item` once per approved story.
9. Record returned item IDs and preserve dependency order.
10. Resolve the configured assignee before execution begins.
11. Add cross-links through `add_comment` when useful.

Story publication does not imply active execution.
Call `assign_configured_user` only when a story enters execution.

Do not create workspaces, boards, groups, or columns implicitly.
Do not publish duplicate cards. Search existing group items first.
If the target board remains ambiguous, stop before `create_item`.
