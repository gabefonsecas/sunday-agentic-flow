# Security policy

## Secrets

Store credentials only in `~/.config/sunday/.env`.
Sunday redacts secret values from events and reports.
Never commit `.env` files or authenticated Friday URLs.

## High-risk operations

Sunday pauses before production, destructive migration, secret, and deployment work.
Merge and deployment remain outside automatic execution.

## Reporting

Report vulnerabilities privately to the repository owner.
Include affected version, reproduction steps, and impact.
Do not include active credentials in reports.
