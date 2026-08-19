# Evaluation sets: format and obligations

This document is generic reference material. **The sets themselves do not live here** — they live in the workspace at `.bearing/eval/{gold,dark,negative,escalation}/`, because their content is specific to the repository under evaluation and this directory is replaced wholesale on every plugin update.

Locate them with `bearing eval <set>` rather than assuming a relative path.

## Why three sets and not one

Precision and recall against well-annotated code tests only whether the pipeline can rediscover decisions that are already documented. That is necessary but carries a selection bias: well-annotated code is usually easier to reason about than the undocumented legacy code this Skill actually targets.

- **Gold Set** — known decisions with known Anchors. Tests recall against ground truth.
- **Dark Set** — undocumented legacy areas, independently investigated by knowledgeable humans who record what they believe can defensibly be recovered *before* seeing pipeline output. Tests real-world recovery quality where no ground truth exists to check against directly. Promoted interview transcripts are good material to add here over time: a live, authority-checked interview is close to the best available ground truth for what a knowledgeable human believes can defensibly be recovered.
- **Negative Set** — code with historical chatter (comments, commit noise) but no defensible organizational decision behind it. Tests the pipeline's propensity to manufacture a plausible-sounding decision where none existed.

The Negative Set is the one that matters most for trust. The risk is not only missing real decisions; it is inventing fictional ones that read just as convincingly as real ones. A pipeline that scores well on Gold and badly on Negative is worse than no pipeline, because it produces confident fiction that a reviewer has to disprove.

## Entry format

One JSON object per line in `cases.jsonl` inside each set directory.

```json
{
  "case_id": "gold-0001",
  "subject": "src/payments/gateway.py::PaymentGateway.retryPolicy",
  "expects": "decision",
  "expected_eocr_function": "Contract",
  "expected_anchor": "docs/decisions/0031-retry-ceiling.md",
  "notes": "documented in ADR-031; pipeline should rediscover from commit history alone"
}
```

- `expects` is `"decision"` for Gold and Dark, and `"no_decision"` for every Negative Set case. The Negative Set is scored on how often the pipeline emits a Reviewable candidate where `expects` is `"no_decision"`.
- `expected_anchor` is omitted for Dark Set cases — there is no ground-truth ADR, only a human's recorded judgment in `notes`.

## Obligation before shipping a change

All three sets are checked before a new extractor version or model tier goes live, not just the Gold Set. `bearing verify --evolve` reads the most recent evaluation results from the ledger and fails when the Negative Set hallucination rate exceeds `verify.negative_set_hallucination_rate_max`.
