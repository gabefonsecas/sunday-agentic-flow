---
name: optimize-model-collaboration
description: Automatically route development work among remote models and subagents exposed by the active host. Use model-tier selection, semantic synthesis, critique, ranking, and independent verification for discovery, implementation, architecture, testing, and review. Never require the user to select models or invoke this skill explicitly.
---

# Optimize Sunday model collaboration

Read `references/strategy-matrix.md` before selecting a mode.

1. Inspect transitions using `sunday routes <run-id> --format markdown`.
2. Use Mermaid when visual flow helps.
3. Inspect full evidence using `sunday report <run-id>`.
4. Classify failures by phase, risk, and model.
5. Verify requested and observed model evidence.
6. Compare retry rate, confidence, duration, and validation.
7. Recommend the cheapest tier preserving acceptance quality.
8. Keep recommendations advisory.
9. Never alter routing policy automatically.

Never claim weight interpolation across unrelated model architectures.
Use semantic interpolation at response and decision layers only.
Use only authenticated hosts and configured providers.
Do not require local inference servers or separate model endpoints.
Never bypass Sunday for Friday, Git, or pull requests.
Never claim routing without a `route.completed` event.
