# Shadow graph — nothing in this folder is authoritative

Machine-inferred candidate decisions, produced by `decision-recovery` and `decision-interview`. A candidate here is a claim about *evidence*, not a decision.

The distinction is the whole reason this directory exists rather than the candidates being written one level up. A recovered candidate reflects what the historical record suggests. A decision reflects what the organization decided. Those are different things, and conflating them would let inference acquire authority nobody granted it.

## Rules

- **No `@see` annotation may point here.** Checked by `bearing lint`, not merely requested.
- **No inference in this directory may block a merge**, at any confidence level. A confidence score describes evidence quality; it says nothing about organizational authority. Only structural enforcement or an accepted Contract may block.
- **Promotion out of here is always a human decision**, and that decision determines scope, current validity, and lifecycle state. It is not a check that the summary read correctly.

## Files

- `candidates.jsonl` — one candidate per line. Schema: `bearing schema candidate`.
- `rejected.jsonl` — the rejection ledger. **Append-only, and never pruned.**
- `{{transcripts_dir}}/` — interview transcripts, the evidence behind live-elicited candidates.

## Why rejections are kept forever

A rejected candidate that vanishes gets rediscovered by the next recovery pass and re-litigated by whoever reviews it next. Keeping the fingerprint is what makes rejection durable, and it is why the ledger is committed rather than treated as run state: the trend matters across contributors and across CI, not on one laptop.

`bearing verify --evolve` fails if a rejected fingerprint reappears as a surfaced candidate.

## Lifecycle states

`Detected` → `Reviewable` → `Promoted` | `Rejected` | `Stale`

Only `Reviewable` candidates reach a human, and only those meeting the surfacing bar: MEDIUM confidence or higher, plus two deliberate exceptions — a candidate that contradicts an accepted record, and one on a subject already flagged load-bearing. Both are worth a human's attention even on weak evidence, because a contradiction with authored knowledge is informative regardless of how confident the inference is.
