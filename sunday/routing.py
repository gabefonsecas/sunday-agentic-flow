"""Deterministic model pools with evidence-based escalation."""

from dataclasses import dataclass
import re


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
    complexity: str = "normal"


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
            _candidate("economy", "gpt-5.4-mini", "low"),
            _candidate("fast", "gpt-5.4", "low"),
            _candidate("balanced", "gpt-5.6-terra", "medium"),
            _candidate("advanced", "gpt-5.5", "medium"),
            _candidate("deep", "gpt-5.6-sol", "high"),
        ),
        "implementation": (
            _candidate("economy", "gpt-5.4-mini", "medium"),
            _candidate("fast", "gpt-5.4", "medium"),
            _candidate("balanced", "gpt-5.6-terra", "high"),
            _candidate("advanced", "gpt-5.5", "high"),
            _candidate("deep", "gpt-5.6-sol", "xhigh"),
        ),
        "verification": (
            _candidate("economy", "gpt-5.4-mini", "low"),
            _candidate("fast", "gpt-5.4", "low"),
            _candidate("balanced", "gpt-5.6-terra", "medium"),
            _candidate("advanced", "gpt-5.5", "high"),
            _candidate("deep", "gpt-5.6-sol", "high"),
        ),
        "review": (
            _candidate("economy", "gpt-5.4-mini", "medium"),
            _candidate("fast", "gpt-5.4", "medium"),
            _candidate("balanced", "gpt-5.6-terra", "high"),
            _candidate("advanced", "gpt-5.5", "xhigh"),
            _candidate("deep", "gpt-5.6-sol", "max"),
        ),
    },
    "claude": {
        phase: (
            _candidate("economy", "claude-haiku-4-5", "medium"),
            _candidate("fast", "claude-sonnet-4-6", "medium"),
            _candidate("advanced", "claude-sonnet-5", "high"),
            _candidate("deep", "claude-opus-5", "max"),
        )
        for phase in AGENTS
    },
    "gemini": {
        "discovery": (
            _candidate("economy", "gemini-3.5-flash-low"),
            _candidate("fast", "gemini-3.5-flash-medium"),
            _candidate("balanced", "gemini-3.6-flash-low"),
            _candidate("advanced", "gemini-3.6-flash-high"),
            _candidate("deep", "gemini-3.1-pro-low"),
        ),
        "implementation": (
            _candidate("economy", "gemini-3.5-flash-medium"),
            _candidate("fast", "gemini-3.5-flash-high"),
            _candidate("balanced", "gemini-3.6-flash-medium"),
            _candidate("advanced", "gemini-3.6-flash-high"),
            _candidate("deep", "gemini-3.1-pro-high"),
        ),
        "verification": (
            _candidate("economy", "gemini-3.5-flash-low"),
            _candidate("fast", "gemini-3.5-flash-medium"),
            _candidate("balanced", "gemini-3.6-flash-low"),
            _candidate("advanced", "gemini-3.6-flash-high"),
            _candidate("deep", "gemini-3.1-pro-low"),
        ),
        "review": (
            _candidate("economy", "gemini-3.5-flash-high"),
            _candidate("fast", "gemini-3.6-flash-medium"),
            _candidate("balanced", "gemini-3.6-flash-high"),
            _candidate("advanced", "gemini-3.1-pro-low"),
            _candidate("deep", "gemini-3.1-pro-high"),
        ),
    },
}

SIMPLE_WORK = re.compile(
    r"\b(readme|changelog|docs?|documentation|documenta[cç][aã]o|typo|format|lint|"
    r"rename|renomear|comment|coment[aá]rio|label|etiqueta|metadata|copy|texto)\b",
    re.IGNORECASE,
)
COMPLEX_WORK = re.compile(
    r"\b(architecture|arquitetura|migration|migra[cç][aã]o|security|seguran[cç]a|auth|"
    r"distributed|distribu[ií]d[oa]|concurrency|concorr[eê]ncia|database|banco de dados|"
    r"payment|pagamento|performance|breaking|large refactor|refatora[cç][aã]o ampla)\b",
    re.IGNORECASE,
)


def classify_complexity(text: str) -> str:
    if COMPLEX_WORK.search(text):
        return "complex"
    if SIMPLE_WORK.search(text):
        return "simple"
    return "normal"
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

    def route(
        self, phase: str, attempt: int = 1, risk: str = "normal", complexity: str = "normal"
    ) -> Route:
        candidates = self.pool(phase)
        if complexity not in {"simple", "normal", "complex"}:
            raise ValueError(f"Unsupported complexity: {complexity}")
        normal_offset = 2 if phase in {"implementation", "review"} else 1
        complexity_offset = {
            "simple": 0,
            "normal": min(normal_offset, len(candidates) - 1),
            "complex": max(0, len(candidates) - 2),
        }[complexity]
        risk_offset = len(candidates) - 1 if risk == "critical" else (
            max(0, len(candidates) - 2) if risk == "high" else 0
        )
        start = max(complexity_offset, risk_offset)
        index = min(max(0, start + attempt - 1), len(candidates) - 1)
        selected = candidates[index]
        if risk_offset:
            reason = f"{risk} risk escalation"
        elif attempt > 1:
            reason = "retry escalation"
        else:
            reason = f"{complexity} complexity"
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
            complexity=complexity,
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
