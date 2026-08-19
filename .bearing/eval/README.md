# Evaluation sets

Repository-specific evaluation content for `decision-recovery`. The **format** is documented generically in the Skill at `plugin/skills/decision-recovery/references/evaluation-sets.md`; the **content** lives here because it describes this repository.

This split is the read-only-plugin purity rule in practice. These sets used to live inside the Skill's `references/`, where every plugin update would have erased them.

- `gold/` — known decisions with known Anchors. Tests recall.
- `dark/` — undocumented areas independently investigated by a human first. Tests real-world recovery where no ground truth exists.
- `negative/` — historical chatter with no defensible decision behind it. Tests whether the pipeline manufactures fiction.

All three are checked before a new extractor version or model tier goes live. `bearing verify --evolve` reads the results and fails when the Negative Set hallucination rate exceeds the configured ceiling.

Each set holds a `cases.jsonl`. Add cases as they are found rather than trying to build a comprehensive suite up front — a Negative Set with five real cases is worth more than an empty one with a plan.
