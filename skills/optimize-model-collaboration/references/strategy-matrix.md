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

## Host mappings

- Codex: discovery uses `gpt-5.6-terra`; implementation uses `gpt-5.6-sol`; verification returns to `gpt-5.6-terra`; deep review uses `gpt-5.6-sol` with `xhigh` effort.
- Claude Code: fast uses `haiku`; balanced uses `sonnet`; deep uses `opus`.
- Gemini CLI: fast uses Gemini Flash; balanced and deep use Gemini Pro.
- Antigravity: fast uses `flash`; balanced and deep use `pro`.

Use `agentic_task_analyst` on Codex for discovery.
Use `agentic_implementation_worker` for bounded coding.
Use `agentic_implementation_verifier` after implementation.
Use `agentic_branch_reviewer` before delivery completion.

Other hosts expose the same names with hyphens.
Invoke them automatically when their descriptions match.

If a configured model is unavailable, inherit the session model.
