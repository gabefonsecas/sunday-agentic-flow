# Strategy matrix

## Remote tiers

### Fast

Use for repository mapping, searches, summaries, and decomposition.
Prefer a fast or economical model offered by the host.

### Balanced

Use for implementation, focused fixes, tests, and documentation.
Prefer the host's general coding model or balanced tier.

### Deep

Use for architecture, security, migrations, ambiguous defects, and final review.
Prefer the strongest reasoning model or highest supported effort.

## Collaboration modes

### Route

Assign each bounded unit directly to its suitable tier.

### Cascade

Let a fast model draft. Let balanced or deep verify.

### Debate

Create independent proposals using different remote models.
The primary agent selects using repository evidence.

### Judge

Provide multiple candidates to a deep reviewer.
The primary agent verifies and selects or synthesizes.

### Ensemble review

Use independent agents for review. Keep only verified findings.

## Optimization loop

Record task class, chosen tier, validation outcome, and corrected errors.
Prefer the cheapest tier preserving acceptance quality.
Never use self-reported confidence as the only routing signal.

## Host pools

- Codex discovery and verification progress through Luna, Terra, and Sol.
- Codex implementation progresses through Terra and two Sol efforts.
- Codex review progresses through Terra, Sol xhigh, and Sol max.
- Claude Code progresses through Haiku, Sonnet, and Opus.
- Gemini discovery progresses through Flash-Lite, Flash, and Auto.
- Gemini implementation and verification progress through Flash, Auto, and Pro.
- Gemini review progresses through Auto, Pro, and Gemini 3 Pro.
- Antigravity uses the Gemini pool through its native command or Gemini fallback.

The runtime owns exact selection and retries.
Do not replace these pools inside a host prompt.

Use `sunday_task_analyst` on Codex for discovery.
Use `sunday_implementation_worker` for bounded coding.
Use `sunday_implementation_verifier` after implementation.
Use `sunday_branch_reviewer` before delivery completion.

Other hosts expose the same names with hyphens.
Sunday invokes them through its headless runtime.

If a candidate is unavailable, record failure and escalate.
Never silently inherit an unverified session model.
