#!/usr/bin/env python3
"""
Cost + reviewer-time ledger, hard stop.

Wraps every model call in the pipeline. Writes one JSON line per stage to
references/cost-ledger.jsonl: model tier, tokens in/out, cost_usd, items
processed/emitted. On the review stage, also logs estimated_review_minutes.

Enforces a hard budget cap per run — halts the pipeline mid-run if
cumulative cost_usd crosses the configured ceiling, and reports whatever
candidates were produced before stopping. Never silently overspends.

Also computes, per repository, the two derived metrics that gate whether
this Skill keeps running there:
  - acceptance_rate = promoted / reviewable
  - cost_per_promoted_candidate = (total model cost + reviewer minutes *
    configured hourly rate) / candidates promoted

TODO: implement the ledger writer
TODO: implement the hard budget cap / mid-run halt
TODO: implement the acceptance-rate and cost-per-promoted-candidate
      kill-switch check, gating future scheduled runs on this repo
"""

def main():
    raise NotImplementedError("See ../SKILL.md and the Economy section of "
                               "decision-recovery-skill-spec.md.")

if __name__ == "__main__":
    main()
