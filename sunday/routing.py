"""Deterministic model routing with evidence-based escalation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Route:
    phase: str
    host: str
    agent: str
    tier: str
    model: str
    effort: str | None
    attempt: int = 1


PROFILES = {
    "codex": {
        "discovery": ("sunday-task-analyst", "fast", "gpt-5.6-terra", "medium"),
        "implementation": ("sunday-implementation-worker", "balanced", "gpt-5.6-sol", "high"),
        "verification": ("sunday-implementation-verifier", "balanced", "gpt-5.6-terra", "high"),
        "review": ("sunday-branch-reviewer", "deep", "gpt-5.6-sol", "xhigh"),
    },
    "claude": {
        "discovery": ("sunday-task-analyst", "fast", "haiku", "medium"),
        "implementation": ("sunday-implementation-worker", "balanced", "sonnet", "high"),
        "verification": ("sunday-implementation-verifier", "balanced", "sonnet", "high"),
        "review": ("sunday-branch-reviewer", "deep", "opus", "xhigh"),
    },
    "gemini": {
        "discovery": ("sunday-task-analyst", "fast", "flash", None),
        "implementation": ("sunday-implementation-worker", "balanced", "pro", None),
        "verification": ("sunday-implementation-verifier", "balanced", "pro", None),
        "review": ("sunday-branch-reviewer", "deep", "pro", None),
    },
    "antigravity": {
        "discovery": ("sunday-task-analyst", "fast", "flash", None),
        "implementation": ("sunday-implementation-worker", "balanced", "pro", None),
        "verification": ("sunday-implementation-verifier", "balanced", "pro", None),
        "review": ("sunday-branch-reviewer", "deep", "pro", None),
    },
}


class ModelRouter:
    def __init__(self, host: str):
        if host not in PROFILES:
            raise ValueError(f"Unsupported host: {host}")
        self.host = host

    def route(self, phase: str, attempt: int = 1, risk: str = "normal") -> Route:
        if phase not in PROFILES[self.host]:
            raise ValueError(f"Unsupported routed phase: {phase}")
        agent, tier, model, effort = PROFILES[self.host][phase]
        if attempt > 1 or risk in {"high", "critical"}:
            agent, tier, model, effort = PROFILES[self.host]["review"]
            agent = PROFILES[self.host][phase][0]
        return Route(phase, self.host, agent, tier, model, effort, attempt)

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
