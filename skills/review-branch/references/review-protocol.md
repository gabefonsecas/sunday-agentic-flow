# Review protocol

## Severity

- P0: Immediate destructive, security, or availability impact.
- P1: Likely production failure or serious regression.
- P2: Real defect with bounded impact.
- P3: Minor correctness or maintainability issue.

## Finding standard

Each finding needs:

- Severity and concise title.
- Exact file and tight line range.
- Triggering inputs or execution path.
- Concrete impact.
- Why existing validation misses it.
- Minimal repair direction.

Reject findings that depend on unsupported assumptions.

## Review surfaces

Check behavior, error handling, authorization, secrets, concurrency, data
migrations, compatibility, observability, performance, accessibility, and tests
when applicable.
