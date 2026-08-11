# Sunday host dispatch

Sunday launches separate headless host contexts.
The runtime selects each model explicitly.

## Required phases

1. Discovery: dispatch the task analyst before planning.
2. Implementation: dispatch the implementation worker after story approval.
3. Verification: dispatch the implementation verifier after changes.
4. Review: dispatch the branch reviewer before delivery completion.

Never reuse one subagent context across these phases.
Wait for each required result before crossing its phase gate.

## Agent names

| Host | Discovery | Implementation | Verification | Review |
| --- | --- | --- | --- | --- |
| Codex | `sunday_task_analyst` | `sunday_implementation_worker` | `sunday_implementation_verifier` | `sunday_branch_reviewer` |
| Claude | `sunday-task-analyst` | `sunday-implementation-worker` | `sunday-implementation-verifier` | `sunday-branch-reviewer` |
| Gemini | `sunday-task-analyst` | `sunday-implementation-worker` | `sunday-implementation-verifier` | `sunday-branch-reviewer` |
| Antigravity | `sunday-task-analyst` | `sunday-implementation-worker` | `sunday-implementation-verifier` | `sunday-branch-reviewer` |

## Runtime mechanisms

- Codex: `codex exec` with explicit model and sandbox.
- Claude: `claude --print` with explicit model and effort.
- Gemini: headless CLI with explicit model and JSON output.
- Antigravity: configured headless command and explicit tier.

Do not merely mention an agent in prose.
Invoke the host's subagent mechanism and consume its result.

## Route ledger

Record one entry per phase:

```text
phase | requested agent | requested tier | actual model if reported | outcome
```

Never invent the actual model.
Use `not reported by host` when unavailable.

Sunday rejects unavailable hosts and unverified mandatory routes.
Cross-provider fallback requires explicit configuration.
