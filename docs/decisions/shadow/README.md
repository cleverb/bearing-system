# Shadow Graph — nothing in this folder is authoritative

This directory holds machine-inferred candidate decisions produced by `decision-recovery` (batch archaeology over commits, PRs, and tickets) and `decision-interview` (live elicitation). Both Skills write into the same two files here.

**Nothing here is a decision.** It's evidence *about* a possible decision, with its confidence, provenance, and uncertainty preserved. A candidate becomes real only when a human promotes it — at which point it becomes a numbered `.md` file somewhere in the authored `docs/decisions/` tree, with a real `@see` annotation in the code it governs.

No `@see` annotation should ever point into this folder. That's enforced by lint, not just stated here — see the Enforcement section of `/BEARING.md`.

## Files

- **`candidates.jsonl`** — one candidate per line (lifecycle updates rewrite the matching line). Each line is one candidate: subject, candidate relation/object, EOCR function, evidence with its five axes (reliability, organizational authority, corroboration, specificity, temporal relevance), a collapsed confidence, and a lifecycle state (`Detected → Corroborated → Reviewable → Promoted / Rejected / Insufficient Evidence / Stale`).
- **`rejected.jsonl`** — append-only. Rejection fingerprints, checked by `decision-recovery`'s resolution stage before a new candidate is emitted, so a human's "no, that's not a real decision" isn't re-litigated by a later run clustering slightly different evidence.

## Reviewing candidates

Candidates at `Reviewable` that meet the surfacing bar are what a human clears from this queue.

**BEARING permits one-click execution of a human promotion decision. It forbids one-click substitution for that decision.**

Promotion is a human workflow that may **reject, revise (edit), split, defer, or promote** the evidence. The human must determine **scope, present validity, authored lifecycle state, and EOCR function**. Confidence never substitutes for that judgment.

What that does *not* require: typing an ADR by hand to prove judgment occurred. After you review the evidence and submit those fields — via `bearing review`, `bearing dispose`, or Cursor MCP elicitation (`bearing-mcp`) — the system may scaffold the ADR, update this queue, and rebuild the index.

What it *does* forbid: treating `confidence: HIGH` as license to copy the candidate unchanged into an Accepted record.

Use:

- `bearing review` — list or interactively dispose surfaced candidates
- `bearing dispose --id … --action Promote --still-valid 1 --eocr … --scope …` — non-interactive execution of an already-made judgment
- MCP tool `review_candidate` (stdio server `bearing-mcp`) — same disposition form inside Cursor
