# Shadow graph — nothing in this folder is authoritative

Machine-inferred candidate decisions, produced by `decision-recovery` and `decision-interview`. A candidate here is a claim about *evidence*, not a decision.

The distinction is the whole reason this reserved subtree exists rather than candidates being written among authored records. A recovered candidate reflects what the historical record suggests. A decision reflects what the organization decided. Those are different things, and conflating them would let inference acquire authority nobody granted it.

## Rules

- **No `@see` annotation may point here.** Checked by `bearing lint`, not merely requested.
- **No inference in this directory may block a merge**, at any confidence level. A confidence score describes evidence quality; it says nothing about organizational authority. Only structural enforcement or an accepted Contract may block.
- **Promotion out of here is always a human decision**, and that decision determines scope, present validity, lifecycle state, and EOCR function. It is not a check that the summary read correctly.
- **One-click execution of that judgment is allowed** (`bearing review` / `bearing dispose` / MCP `review_candidate`). **Ceremonial confidence-approve is not.** Promote requires the human fields; scaffolding the ADR afterward is mechanical.

## Files

- `candidates.jsonl` — one candidate per line. Schema: `bearing schema candidate`.
- `rejected.jsonl` — the rejection ledger. **Append-only, and never pruned.**
- `{{transcripts_dir}}/` — interview transcripts, the evidence behind live-elicited candidates.

## Why rejections are kept forever

A rejected candidate that vanishes gets rediscovered by the next recovery pass and re-litigated by whoever reviews it next. Keeping the fingerprint is what makes rejection durable, and it is why the ledger is committed rather than treated as run state: the trend matters across contributors and across CI, not on one laptop.

`bearing verify --evolve` fails if a rejected fingerprint reappears as a surfaced candidate.

## Lifecycle states

`Detected` → `Corroborated` → `Reviewable` → `Promoted` | `Rejected` | `Insufficient Evidence` | `Stale`

Only surfaced candidates reach a human (MEDIUM confidence or higher, plus two deliberate exceptions — a candidate that contradicts an accepted record, and one on a subject already flagged load-bearing). Clear them with reject, revise, split, defer, or promote — never by auto-promoting from confidence alone.
