# Mandatory host dispatch

Model routing uses separate subagent contexts.
It does not change the primary conversation model in place.

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
| Codex | `agentic_task_analyst` | `agentic_implementation_worker` | `agentic_implementation_verifier` | `agentic_branch_reviewer` |
| Claude | `agentic-task-analyst` | `agentic-implementation-worker` | `agentic-implementation-verifier` | `agentic-branch-reviewer` |
| Gemini | `agentic-task-analyst` | `agentic-implementation-worker` | `agentic-implementation-verifier` | `agentic-branch-reviewer` |
| Antigravity | `agentic-task-analyst` | `agentic-implementation-worker` | `agentic-implementation-verifier` | `agentic-branch-reviewer` |

## Host mechanisms

- Codex: spawn the named custom agent.
- Claude: call the named Agent subagent.
- Gemini: call the named subagent tool.
- Antigravity: call `invoke_subagent` with the named agent.

Do not merely mention an agent in prose.
Invoke the host's subagent mechanism and consume its result.

## Route ledger

Record one entry per phase:

```text
phase | requested agent | requested tier | actual model if reported | outcome
```

Never invent the actual model.
Use `not reported by host` when unavailable.

## Degraded mode

If the host lacks subagents, continue with the primary model.
Mark every skipped transition as degraded.
Never claim successful model routing in degraded mode.
