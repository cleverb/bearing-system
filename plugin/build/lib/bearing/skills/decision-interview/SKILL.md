---
name: decision-interview
description: Conduct a structured, pressure-tested interview with a human at the moment an agent hits genuine architectural ambiguity, and record the answer as a candidate decision. Use when intent is missing or ambiguous and you cannot proceed safely without asking, or when a human asks to resolve and document a decision. Applies the deletion test and an explicit authority check before anything is recorded.
metadata:
  bearing-role: live-acquisition
  writes-to: shadow-graph
---

# Skill: Decision Interview

## Context
Some decisions never get written down because nobody asks about them until
an agent hits real ambiguity mid-task. This Skill conducts a structured,
live interview at exactly that moment, and writes a candidate to the same
docs/decisions/shadow/candidates.jsonl decision-recovery writes to — tagged
evidence_source: live_interview, EOCR-tagged by the interviewee directly,
and pressure-tested before it's allowed to proceed.

## Trigger
Fires on either:
- an agent hitting a genuine escalation point per AGENTS.md — ambiguous
  intent, no Anchor, and it cannot proceed safely without asking; or
- a direct human request to resolve and document a decision.

Never fires speculatively. This is the structured form of "stop and ask a
human" that already exists as a constitutional rule in AGENTS.md — not a
new behavior layered on top of it.

## Pipeline

1. ELICIT: ask targeted questions to surface what decision is actually
   being made, and why. Capture the raw answer as evidence_excerpt,
   evidence_source: live_interview.

2. DELETION TEST (required, not optional): ask directly — "if this
   constraint were removed, what breaks?" If the interviewee cannot name a
   defensible, specific consequence, the candidate is capped: it may still
   be recorded as Rationale but MUST NOT be tagged as a Contract.

3. EOCR TAG: the interviewee explicitly commits to a candidate_eocr_function
   (Entry / Operations / Contract / Rationale) — asked directly, not
   inferred from phrasing.

4. AUTHORITY CHECK (required): ask directly whether the interviewee has
   standing to make this call, or whether it needs corroboration from
   someone else before it's binding. Never assume HIGH organizational
   authority just because the testimony was clear and confident.

5. CONFLICT CHECK: check the candidate against existing accepted Contracts.
   If it conflicts, stop and surface it directly — "this appears to
   disagree with ADR-014, is this meant to supersede it, or is there a
   misunderstanding here?" Never silently prefer the new answer.

6. FAST-TRACKED LIFECYCLE ENTRY: enters at Reviewable directly, skipping
   Detected and Corroborated — live, authority-checked testimony is
   stronger evidence than a single mined source. Does NOT skip promotion
   review; a human still determines scope, lifecycle state, and Anchor
   placement.

7. INDEX ON PROMOTION: if promoted, the question that triggered the
   interview becomes the docs/decisions/index.json trigger phrase — the
   most accurate available summary of when this decision matters, since
   it's the actual situation that required it. Run `bearing index`; do
   not invoke a Skill script.

## Escalation Rules
- Deletion test with no defensible answer → cap at Rationale, never
  Contract, regardless of confidence in how it was stated.
- Authority check uncertain → proceed to Reviewable flagged
  organizational_authority: UNKNOWN; a human reviewer decides if that's
  sufficient or if corroboration is still needed.
- Unresolved conflict with an accepted Contract → queue as Reviewable with
  the conflict explicitly attached, never auto-resolved.

## Cost Tracking
Interview duration is logged exactly (interview_duration_minutes), not
estimated, to the same cost ledger decision-recovery uses, under
evidence_source: live_interview — so cost-per-promoted-candidate stays
comparable across both acquisition modes.
