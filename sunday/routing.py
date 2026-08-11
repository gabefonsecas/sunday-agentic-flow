"""Deterministic model pools with evidence-based escalation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    tier: str
    model: str
    effort: str | None = None


@dataclass(frozen=True, slots=True)
class Route:
    phase: str
    host: str
    agent: str
    tier: str
    model: str
    effort: str | None
    attempt: int = 1
    pool_position: int = 1
    pool_size: int = 1
    reason: str = "phase default"


AGENTS = {
    "discovery": "sunday-task-analyst",
    "implementation": "sunday-implementation-worker",
    "verification": "sunday-implementation-verifier",
    "review": "sunday-branch-reviewer",
}


def _candidate(tier: str, model: str, effort: str | None = None) -> ModelCandidate:
    return ModelCandidate(tier, model, effort)


MODEL_POOLS = {
    "codex": {
        "discovery": (
            _candidate("fast", "gpt-5.6-luna", "low"),
            _candidate("balanced", "gpt-5.6-terra", "medium"),
            _candidate("deep", "gpt-5.6-sol", "high"),
        ),
        "implementation": (
            _candidate("balanced", "gpt-5.6-terra", "high"),
            _candidate("deep", "gpt-5.6-sol", "high"),
            _candidate("deep", "gpt-5.6-sol", "xhigh"),
        ),
        "verification": (
            _candidate("fast", "gpt-5.6-luna", "medium"),
            _candidate("balanced", "gpt-5.6-terra", "high"),
            _candidate("deep", "gpt-5.6-sol", "high"),
        ),
        "review": (
            _candidate("balanced", "gpt-5.6-terra", "high"),
            _candidate("deep", "gpt-5.6-sol", "xhigh"),
            _candidate("deep", "gpt-5.6-sol", "max"),
        ),
    },
    "claude": {
        phase: (
            _candidate("fast", "haiku", "medium"),
            _candidate("balanced", "sonnet", "high"),
            _candidate("deep", "opus", "max"),
        )
        for phase in AGENTS
    },
    "gemini": {
        "discovery": (
            _candidate("fast", "flash-lite"),
            _candidate("balanced", "flash"),
            _candidate("adaptive", "auto"),
        ),
        "implementation": (
            _candidate("fast", "flash"),
            _candidate("adaptive", "auto"),
            _candidate("deep", "pro"),
        ),
        "verification": (
            _candidate("fast", "flash"),
            _candidate("adaptive", "auto"),
            _candidate("deep", "pro"),
        ),
        "review": (
            _candidate("adaptive", "auto"),
            _candidate("deep", "pro"),
            _candidate("deep", "gemini-3-pro-preview"),
        ),
    },
}
MODEL_POOLS["antigravity"] = {
    phase: tuple(candidates) for phase, candidates in MODEL_POOLS["gemini"].items()
}

# Compatibility view for integrations reading the old single-profile matrix.
PROFILES = {
    host: {
        phase: (AGENTS[phase], candidates[0].tier, candidates[0].model, candidates[0].effort)
        for phase, candidates in phases.items()
    }
    for host, phases in MODEL_POOLS.items()
}


class ModelRouter:
    def __init__(self, host: str):
        if host not in MODEL_POOLS:
            raise ValueError(f"Unsupported host: {host}")
        self.host = host

    def pool(self, phase: str) -> tuple[ModelCandidate, ...]:
        if phase not in MODEL_POOLS[self.host]:
            raise ValueError(f"Unsupported routed phase: {phase}")
        return MODEL_POOLS[self.host][phase]

    def route(self, phase: str, attempt: int = 1, risk: str = "normal") -> Route:
        candidates = self.pool(phase)
        risk_offset = 2 if risk == "critical" else 1 if risk == "high" else 0
        index = min(max(0, attempt - 1 + risk_offset), len(candidates) - 1)
        selected = candidates[index]
        if risk_offset:
            reason = f"{risk} risk escalation"
        elif attempt > 1:
            reason = "retry escalation"
        else:
            reason = "phase default"
        return Route(
            phase=phase,
            host=self.host,
            agent=AGENTS[phase],
            tier=selected.tier,
            model=selected.model,
            effort=selected.effort,
            attempt=attempt,
            pool_position=index + 1,
            pool_size=len(candidates),
            reason=reason,
        )

    def recommendation(self, outcomes: list[dict]) -> dict:
        failures = sum(1 for outcome in outcomes if not outcome.get("success", False))
        retries = sum(max(0, int(outcome.get("attempt", 1)) - 1) for outcome in outcomes)
        return {
            "sample_size": len(outcomes),
            "failure_rate": failures / len(outcomes) if outcomes else 0.0,
            "retries": retries,
            "recommendation": "review routing policy" if failures or retries else "keep current policy",
            "automatic_policy_change": False,
        }
