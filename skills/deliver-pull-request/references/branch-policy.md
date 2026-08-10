# Base branch policy

Use `homolog` when the request explicitly targets staging, homologation,
pre-production validation, or an established repository flow through that
branch.

Use `main` when the request explicitly targets production, a hotfix flow,
the repository has no `homolog`, or repository guidance defines `main` as the
normal integration branch.

If both branches exist and task intent is unclear, inspect recent merged PRs
and contribution guidance. Ask before publication when evidence still conflicts.

PR bodies must contain:

- Outcome summary.
- Friday item IDs.
- Important implementation choices.
- Validation commands and results.
- Known risks and follow-up work.
