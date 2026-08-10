---
name: review-branch
description: Review a branch or pull request against its base for correctness, regressions, security, maintainability, tests, and repository rules. Use for pre-merge review, branch audits, PR review, or independent verification, with optional Friday publication when a linked item exists.
---

# Review a branch

1. Read `references/review-protocol.md`.
2. Identify head, base, merge base, task intent, and linked Friday items.
3. Read applicable project instructions.
4. Inspect the complete diff and affected call paths.
5. Run targeted checks when they materially verify findings.
6. Use a deep remote reviewer for an independent pass.
7. Verify every candidate finding against current code.
8. Report actionable findings first, ordered by severity.
9. Include exact file and line locations.
10. Publish a concise Friday comment only when requested or already linked.

Review is read-only by default. Do not implement fixes unless asked.
Do not report style preferences as defects.
If no findings exist, state that and list remaining test gaps.
