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

- Codex progresses through GPT-5.4 mini, GPT-5.4, GPT-5.6 Terra, GPT-5.5, and GPT-5.6 Sol.
- Claude progresses through Haiku 4.5, Sonnet 4.6, Sonnet 5, and Opus 5.
- Gemini progresses through Gemini 3.5 Flash (Low/Medium/High), Gemini 3.6 Flash (Low/Medium/High), and Gemini 3.1 Pro (Low/High).
- Antigravity uses the Gemini pool through its native command or Gemini fallback.

Classify simple documentation and text work as `simple`.
Classify ordinary feature and defect work as `normal`.
Classify architecture, security, migration, database, and concurrency work as `complex`.
Start high-risk work at the advanced tier.
Escalate one candidate after every rejected attempt.

Friday, Git, and GitHub effects are deterministic adapters.
Never allocate model inference for those effects.

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
