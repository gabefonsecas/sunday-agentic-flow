---
name: optimize-model-collaboration
description: Automatically route development work among remote models and subagents exposed by the active host. Use model-tier selection, semantic synthesis, critique, ranking, and independent verification for discovery, implementation, architecture, testing, and review. Never require the user to select models or invoke this skill explicitly.
---

# Optimize model collaboration

Read `references/strategy-matrix.md` before selecting a mode.

1. Classify each bounded unit by risk, ambiguity, context, and verifiability.
2. Choose the cheapest remote tier that preserves required quality.
3. Delegate discovery and summarization to the fast tier.
4. Delegate implementation and focused tests to the balanced tier.
5. Delegate architecture, security, and final review to the deep tier.
6. Give every subagent only the required context and permissions.
7. Require structured evidence and explicit uncertainty.
8. Verify delegated output using repository files, tests, and tools.
9. Let the primary agent synthesize decisions and mutate external state.

Never claim weight interpolation across unrelated model architectures.
Use semantic interpolation at response and decision layers only.
Use only models already authenticated through the active host.
Do not require local inference servers or separate model endpoints.
Never delegate Friday changes, pushes, or PR publication blindly.
