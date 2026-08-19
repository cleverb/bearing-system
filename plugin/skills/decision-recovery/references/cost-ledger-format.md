# Cost ledger: format and location

The ledger is append-only JSONL at **`.bearing/ledger/cost.jsonl` in the workspace**, not in this directory.

That location is a correction, not a preference. An earlier draft of the Recovery spec placed the ledger at `references/cost-ledger.jsonl` inside this Skill. Two things break under that placement:

1. Plugin directories are replaced wholesale on update, so every upgrade would silently erase the repository's entire cost history.
2. The ledger is per-repository run history — it is knowledge about the repository, not about the Skill — and the kill switch depends on trends across many runs and many contributors.

Resolve it with `bearing ledger` rather than assuming a relative path.

## Row shapes

One row per pipeline stage per run. `stage` discriminates the shape.

```json
{"run_id": "2026-08-16-weekly", "stage": "extract", "model": "claude-haiku-4.5",
 "tier": "cheap", "items_processed": 4200, "input_tokens": 2100000,
 "output_tokens": 84000, "token_source": "measured",
 "cost_usd": 1.02, "candidates_emitted": 340, "price_book_version": "2026-08-01"}
{"run_id": "2026-08-16-weekly", "stage": "review", "reviewer": "human",
 "candidates_reviewed": 61, "candidates_promoted": 9, "estimated_review_minutes": 87}
```

`token_source` is required on every model stage and must be `"measured"` or `"estimated"`. A cost figure derived from estimated tokens is reported with a range and marked as estimated everywhere it appears; a figure that cannot state its provenance is not reportable.

## The two derived metrics

- **Acceptance rate** — promoted divided by reviewable. Necessary but not sufficient: a repository producing 100 trivial candidates at 30% acceptance and one producing 5 candidates at 20% acceptance where the single hit is an undocumented security constraint are not the same kind of system.
- **Cost per promoted candidate** — total model cost plus `estimated_review_minutes` valued at the configured reviewer rate, divided by candidates promoted. This is the metric that catches what acceptance rate alone misses, because it puts the dominant cost — a senior engineer's review time, not cheap-tier tokens — into the same number that decides whether the Skill keeps running.

The kill switch triggers on a sustained rise in cost per promoted candidate over `verify.cost_per_promoted_trailing_window` runs, not on raw acceptance rate.

When `cost.reviewer_rate_usd_per_hour` is unset — which is the default — review cost is reported in minutes and never converted to dollars. See `bearing report --help`.
