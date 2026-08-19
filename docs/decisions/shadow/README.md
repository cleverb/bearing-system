# Shadow Graph — nothing in this folder is authoritative

This directory holds machine-inferred candidate decisions produced by `decision-recovery` (batch archaeology over commits, PRs, and tickets) and `decision-interview` (live elicitation). Both Skills write into the same two files here.

**Nothing here is a decision.** It's evidence *about* a possible decision, with its confidence, provenance, and uncertainty preserved. A candidate becomes real only when a human promotes it — at which point it becomes a numbered `.md` file one directory up, in `docs/decisions/`, with a real `@see` annotation in the code it governs.

No `@see` annotation should ever point into this folder. That's enforced by lint, not just stated here — see the Enforcement section of `/BEARING.md`.

## Files

- **`candidates.jsonl`** — append-only. Each line is one candidate: subject, candidate relation/object, EOCR function, evidence with its five axes (reliability, organizational authority, corroboration, specificity, temporal relevance), a collapsed confidence, and a lifecycle state (`Detected → Corroborated → Reviewable → Promoted / Rejected / Insufficient Evidence / Stale`).
- **`rejected.jsonl`** — append-only. Rejection fingerprints, checked by `decision-recovery`'s resolution stage before a new candidate is emitted, so a human's "no, that's not a real decision" isn't re-litigated by a later run clustering slightly different evidence.

## Reviewing candidates

Candidates at `Reviewable` are what a human clears from this queue — see `.agents/skills/decision-recovery/SKILL.md` and `.agents/skills/decision-interview/SKILL.md` for the full promotion lifecycle. Promotion means initiating an authored decision-recovery workflow, not clicking approve on a summary: scope, current validity, and lifecycle state are all determined by the human, not inferred by the model.
