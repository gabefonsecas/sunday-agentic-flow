---
name: optimize-model-collaboration
description: Automatically route development work among remote models and subagents exposed by the active host. Use model-tier selection, semantic synthesis, critique, ranking, and independent verification for discovery, implementation, architecture, testing, and review. Never require the user to select models or invoke this skill explicitly.
---

# Optimize model collaboration

Read `references/strategy-matrix.md` before selecting a mode.

1. Classify each bounded unit by risk, ambiguity, context, and verifiability.
2. Choose the cheapest remote tier that preserves required quality.
3. Invoke the fast task analyst for discovery.
4. Consume its result before planning.
5. Invoke the balanced implementation worker for coding.
6. Consume its result before verification.
7. Invoke the independent implementation verifier.
8. Invoke the deep branch reviewer before completion.
9. Give every subagent only required context and permissions.
10. Record every invocation in the route ledger.
11. Verify delegated output using repository files, tests, and tools.
12. Let the primary agent synthesize decisions and mutate external state.

Never claim weight interpolation across unrelated model architectures.
Use semantic interpolation at response and decision layers only.
Use only models already authenticated through the active host.
Do not require local inference servers or separate model endpoints.
Never delegate Friday changes, pushes, or PR publication blindly.
Never claim routing when no specialist was actually invoked.
