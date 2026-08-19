# Skill Spec: Decision Interview

`.agents/skills/decision-interview/`

*The live counterpart to Decision Recovery. Where Recovery mines historical evidence in batch, Interview elicits testimony from a human in the moment an agent hits real ambiguity — structured, EOCR-tagged, and pressure-tested before it's allowed to become a candidate decision.*

---

## Why this isn't a new schema

The most important design decision in this spec is what it *doesn't* introduce: a second shadow graph. A Decision Interview produces exactly the same candidate object Decision Recovery does — same `candidate.schema.json`, same five evidence axes, same lifecycle states, same promotion boundary, same cost ledger. The only thing that changes is `evidence_source`, which gets a new value: `live_interview` instead of `commit_message`, `pr_description`, and so on.

This matters beyond tidiness. It means the two Skills can disagree, corroborate, or contradict each other on the same subject inside one graph — a live interview answer can directly confirm or override a low-confidence archaeological candidate, because they're the same kind of object competing on the same evidence axes, not two separate systems that need reconciling after the fact.

## What changes because the evidence is live

Three things are true of interview testimony that aren't true of mined evidence, and the spec is built around each:

1. **Reliability is usually high, authority is not automatic.** A person answering in real time, engaged with the actual ambiguity, produces high-reliability evidence almost by default. But that says nothing about whether they had standing to make the call — a live answer from someone guessing is still just a well-reliable guess. Authority has to be asked, not assumed.

2. **It can be pressure-tested on the spot.** Archaeology can't interrogate a six-month-old commit message. An interview can ask a follow-up. This is the deletion test's whole reason for existing here and not in Recovery.

3. **The cost is exact, not estimated.** Decision Recovery has to approximate reviewer minutes after the fact. An interview knows precisely how long it took, because the person experienced it in real time.

---

## Directory structure

This Skill's tooling lives under `.agents/`, same as any Skill. Its output — candidates — goes to `docs/decisions/shadow/`, the same location Decision Recovery writes to. See that spec's "Where the shadow graph actually lives" for the full reasoning; it isn't repeated here since the two Skills share one shadow graph, not two.

```
.agents/skills/decision-interview/
├── README.md
├── SKILL.md
├── scripts/
│   └── update-disclosure-index.py   # regenerates docs/decisions/index.json on promotion
├── subagents/
│   └── decision-interviewer.md      # conducts the interview, applies the deletion test
└── references/
    └── interview-transcripts/       # retained for audit; not authoritative on their own
```

No separate schema directory — it imports `decision-recovery`'s `schemas/candidate.schema.json` and `evidence.schema.json` directly.

## SKILL.md

```markdown
# Skill: Decision Interview

## Context
Some decisions never get written down because nobody asks about them until
an agent hits real ambiguity mid-task. This Skill conducts a structured,
live interview at exactly that moment, and writes a candidate to the same
docs/decisions/shadow/candidates.jsonl Decision Recovery writes to — tagged
evidence_source: live_interview, EOCR-tagged by the interviewee directly,
and pressure-tested before it's allowed to proceed.

## Trigger
Fires on either:
- an agent hitting a genuine escalation point per AGENTS.md — ambiguous
  intent, no Anchor, and it cannot proceed safely without asking; or
- a direct human request to resolve and document a decision.

Never fires speculatively. This is the structured form of "stop and ask a
human" that already exists as a constitutional rule — not a new behavior
layered on top of it.

## Pipeline

1. ELICIT: ask targeted questions to surface what decision is actually
   being made, and why. Capture the raw answer as evidence_excerpt,
   evidence_source: live_interview.

2. DELETION TEST (required, not optional): ask directly — "if this
   constraint were removed, what breaks?" If the interviewee cannot name a
   defensible, specific consequence, the candidate is capped: it may still
   be recorded as Rationale (useful context) but MUST NOT be tagged as a
   Contract. A constraint nobody can justify under direct question is not
   a rule, whatever form it takes when written down.

3. EOCR TAG: the interviewee explicitly commits to a candidate_eocr_function
   (Entry / Operations / Contract / Rationale) — asked directly, not
   inferred from phrasing. This is the one thing an interview can do that
   archaeology cannot: make the human own the normative weight in the
   moment, rather than have it guessed at later from a code comment.

4. AUTHORITY CHECK (required): ask directly whether the interviewee has
   standing to make this call, or whether it needs to be corroborated by
   someone else before it's binding. Set organizational_authority on the
   evidence entry from the answer — never assume HIGH just because the
   testimony itself was clear and confident.

5. CONFLICT CHECK: check the candidate against existing accepted Contracts
   in the Decision Graph. If it conflicts, stop and surface it directly to
   the interviewee — "this appears to disagree with ADR-014, is this
   meant to supersede it, or is there a misunderstanding here?" Never
   silently prefer the new answer over the old one.

6. FAST-TRACKED LIFECYCLE ENTRY: because live, pressure-tested,
   authority-checked testimony is stronger evidence than a single mined
   source, an interview candidate enters the lifecycle at Reviewable
   directly — skipping Detected and Corroborated, which exist in Recovery
   to compensate for evidence that can't be cross-examined. It does NOT
   skip promotion review. A human still determines scope, lifecycle state,
   and which implementation gets the Anchor — the same authority boundary
   Decision Recovery enforces, just entered from a stronger starting point.

7. INDEX ON PROMOTION: if promoted, the question that triggered the
   interview becomes the disclosure-index trigger phrase for the resulting
   decision — it is definitionally the most accurate one-line summary of
   when this decision matters, since it's the actual situation that
   required it.

## Escalation Rules
- If the deletion test produces no defensible answer, cap at Rationale —
  do not proceed to Contract regardless of how confidently it was stated.
- If the authority check comes back uncertain, the candidate proceeds to
  Reviewable but flagged organizational_authority: UNKNOWN — a human
  reviewer decides whether that's sufficient or whether corroboration is
  still needed before promotion.
- If a conflict with an accepted Contract can't be resolved in the
  interview itself, the candidate is queued as Reviewable with the
  conflict explicitly attached, not auto-resolved either direction.

## Cost Tracking
Interview duration is logged exactly (interview_duration_minutes), not
estimated, and written to the same cost ledger Decision Recovery uses —
under evidence_source: live_interview, so cost-per-promoted-candidate stays
comparable across both acquisition modes.
```

---

## Feeding the progressive-disclosure index

`docs/decisions/index.json` lives with the corpus it's compiled from, not under `.agents/` — same reasoning as the shadow graph: this is decision content, not Skill tooling. It's generated deterministically from `docs/decisions/*.md` front matter and never hand-maintained, but it's worth being precise that this isn't a Projection in the technical sense used elsewhere in this architecture — there's no runtime format divergence being bridged, no `.cursor/` vs `.codex/` split, just one tool-agnostic index compiled from one corpus. It's structured to be loaded the way Agent Skills already are, though: a compact index up front (id, one-line trigger, EOCR function, lifecycle state, scope), full ADR body pulled only when the trigger matches the current task. Any agent already comfortable with Skill-style progressive disclosure needs no second mental model to use it.

```json
{
  "id": "ADR-031",
  "trigger": "touching PaymentGateway retry logic or rate-limit handling",
  "eocr_function": "Contract",
  "lifecycle_state": "Accepted",
  "scope": "src/payments/**",
  "source": "docs/decisions/0031-retry-ceiling.md"
}
```

Both Decision Recovery and Decision Interview write to this index on promotion — Recovery's entries carry a trigger phrase composed after the fact from the evidence; Interview's entries carry the trigger phrase for free, since the question that prompted the interview *is* the trigger.

Contracts are indexed for near-always visibility (the index entry itself is cheap enough to sit in working context at session start); Rationale stays fully lazy-loaded, pulled only when an Anchor fires or a trigger phrase matches — the category-specific disclosure policy this index exists to support, which a single flat file can't express.

---

## What this deliberately reuses rather than reinvents

The evidence schema, the five confidence axes, the cost ledger, the acceptance-rate and cost-per-promoted-candidate metrics, and the Gold/Dark/Negative evaluation sets all carry over unchanged from Decision Recovery. Interview transcripts can even be added to the Dark Set over time — a live, authority-checked interview is close to the best available ground truth for "what does a knowledgeable human believe can defensibly be recovered here," which is exactly what the Dark Set is for.
