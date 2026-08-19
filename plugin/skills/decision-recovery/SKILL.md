---
name: decision-recovery
description: Recover evidence of undocumented architectural decisions from commit history, PR descriptions, tickets, and code comments into a reviewable shadow graph of candidates. Use when auditing a legacy area for missing decision ancestry, running a scheduled BEARING recovery pass, or asked why code looks the way it does when no ADR exists. Never writes to the authored decision record directly.
metadata:
  bearing-role: retrospective-acquisition
  writes-to: shadow-graph
---

# Skill: Decision Recovery

## Context
Undocumented decisions accumulate as commit messages, PR descriptions, and
comments — but never as `@see ADR-XXX` annotations or entries in
docs/decisions/. This Skill recovers evidence of such decisions and routes
it to a human for judgment. It does not assert that a decision was made —
only that evidence suggesting one exists. It never writes to
docs/decisions/ or adds annotations directly.

## Trigger
Runs as a scheduled *agent* session (weekly is a policy, not a shipped
cron) against a bounded scope. Never a live PR check. Never triggered
per-commit. There is no `extract.py`: this Skill is agent-executed.

## Pipeline (bounded, non-recursive)

The stages are judgment. The CLI validates the result. Follow
`references/agent-procedure.md` for the mechanical steps.

1. EXTRACT (cheap-tier, decision-archaeologist): using git log, `gh`,
   and code comments, scan the scoped corpus once. For each code symbol
   with no existing Anchor, extract candidate evidence tagged with its
   EOCR function. Runs once per item per corpus version. Do not invoke
   any Skill `scripts/` — there are none.

2. RESOLVE (mid-tier, decision-archaeologist, candidates only): cluster
   evidence referring to the same underlying decision. If evidence
   conflicts, do NOT reconcile it into one confident answer — emit a
   "conflicting evidence" candidate with all sources attached and
   confidence capped at LOW. Check docs/decisions/shadow/rejected.jsonl
   before emitting — suppress by default if evidence substantially
   overlaps a prior rejection fingerprint.

3. SCORE (mid-tier): compute all five evidence axes (reliability,
   authority, corroboration, specificity, temporal relevance) per source,
   and a collapsed top-line confidence. Store the full breakdown
   regardless of whether it's surfaced by default.

4. QUEUE: append candidates to docs/decisions/shadow/candidates.jsonl
   matching `bearing schema candidate`. Then run `bearing lint`.
   Reviewable candidates are those with confidence MEDIUM or higher, OR
   any LOW candidate meeting an exception below. Append a cost row to
   the path printed by `bearing ledger`.

## Instructions for the Agent
1. Never write directly to docs/decisions/ or add a code annotation.
   Output is always a candidate in the shadow graph, never a commit.
2. Never claim a decision "was made." Claim only that evidence exists
   suggesting one may have been.
3. Idempotency key is `symbol + source-corpus-version + extractor-version`
   — NOT symbol alone. Unchanged evidence is never reprocessed. New
   evidence makes a symbol eligible for reconsideration even if a prior
   candidate exists; a candidate whose evidence base materially changed
   since scoring moves to lifecycle state Stale rather than being
   silently overwritten.
4. If resolution produces conflicting evidence, surface the conflict;
   never resolve it by selecting one side.
5. Stop the run and report partial results if the budget cap is reached
   before the scope completes.

## Escalation Rules (LOW-confidence handling)
Default: LOW-confidence candidates are retained in the ledger but NOT
surfaced to the review queue.

Exceptions — a LOW candidate IS surfaced when:
- it conflicts with an existing accepted ADR, regardless of its own
  confidence; or
- the subject is flagged load-bearing or high-impact (payment path, auth
  boundary, or code already carrying a HIGH-severity Contract).

## Model Tiering (Contract)
- Extraction MUST use the cheap tier.
- Resolution and scoring MAY use the mid/frontier tier, but only on the
  candidate set already narrowed by extraction.

## PR-Time Signal Boundary (hard constraint)
A recovery signal MUST NOT block a merge, under any confidence score.
Only structural enforcement ("the referenced ADR doesn't exist") or
known-Contract enforcement ("this violates accepted Contract C-17") may
block. A recovery signal may only flag and route to review.

## Success Criteria
- Every Reviewable candidate carries: EOCR-tagged summary, collapsed
  confidence, full axis breakdown on request, source excerpts, temporal
  scope, and an idempotency key tied to corpus version.
- No candidate is reprocessed against unchanged evidence.
- Run cost and estimated reviewer time are both logged before any
  candidate is surfaced.
- No recovery signal blocks a merge under any circumstances.
