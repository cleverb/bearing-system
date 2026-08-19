# Skill Spec: Decision Interview

`plugin/skills/decision-interview/`

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

This Skill ships inside the plugin. Its output — candidates and transcripts — goes to the shadow graph, the same location Decision Recovery writes to. See that spec's "Where the shadow graph actually lives" for the full reasoning; it isn't repeated here since the two Skills share one shadow graph, not two.

```
plugin/skills/decision-interview/
├── README.md
├── SKILL.md
├── scripts/
│   └── update-disclosure-index.py   # regenerates the disclosure index on promotion
├── subagents/
│   └── decision-interviewer.md      # canonical; conducts the interview, applies the deletion test
└── references/
    └── transcript-handling.md       # where transcripts go, and the retention policy
```

### Resolving the shared schema

No separate schema directory: this Skill validates against `decision-recovery`'s `candidate.schema.json` and `evidence.schema.json`. How it *reaches* them is not incidental.

An earlier draft used a relative path — `../decision-recovery/schemas/candidate.schema.json`. That reads perfectly naturally in a monorepo checkout and is a path a conforming client is **required to refuse**: Agent Plugins v1.0.0 §4.1.3 states that a filesystem-resolved path must remain within the resolved plugin root, and clients must reject package paths that resolve outside it. Since Cursor and Claude Code both copy the plugin into a versioned cache, the reference would also simply not resolve.

Packaging BEARING as a *single* plugin removes the cross-plugin problem, but not the `../` problem — the two skills are still sibling directories. So the schema is resolved through the CLI:

```bash
bearing schema candidate   # prints an absolute path inside the resolved plugin root
bearing schema evidence
```

This works identically whether BEARING is installed from a marketplace, vendored into `.agents/skills/`, or run from a checkout, and it is enforced: the packaging suite fails on any `../` reference that escapes a skill directory, so the shortcut cannot come back by accident. <!-- bearing:ignore-paths: the vendored path exists only when `bearing vendor` has run -->

### Where transcripts live, and for how long

Transcripts are **evidence**, so they inherit the shadow graph's standing — non-authoritative on their own — and they live with it, at `<decisions.path>/shadow/transcripts/`. Not in the plugin's `references/`: the plugin is read-only and is replaced on update, so a transcript written there is a named person's testimony scheduled for silent deletion.

Retention is a repository policy, set as `interview.transcripts.retention`, because organizations differ on this for legitimate reasons rather than technical ones:

| Value | Behaviour | For |
| --- | --- | --- |
| `committed` | Transcripts are committed alongside the shadow graph | Audit contexts where the chain from testimony to record must be reconstructible |
| `local` | Written to a gitignored subdirectory | Organizations that will not commit a named individual's testimony to a shared repository |
| `none` | Discarded once the candidate is written | Where the candidate's `evidence_excerpt` is considered sufficient record |

Under `none` the candidate still records that an interview occurred, who was asked, and the excerpt — what is discarded is the surrounding conversation, not the provenance. A candidate whose origin cannot be reconstructed at all would be inference wearing testimony's authority, which is the one thing this spec exists to prevent.

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

The disclosure index lives with the corpus it's compiled from, not in the plugin — same reasoning as the shadow graph: this is decision content, not Skill tooling. It's generated deterministically from the decision records' front matter and never hand-maintained, but it's worth being precise that this isn't a Projection in the technical sense used elsewhere in this architecture — there's no runtime format divergence being bridged, no `.cursor/` vs `.codex/` split, just one tool-agnostic index compiled from one corpus. It's structured to be loaded the way Agent Skills already are, though: a compact index up front (id, one-line trigger, EOCR function, lifecycle state, scope), full ADR body pulled only when the trigger matches the current task. Any agent already comfortable with Skill-style progressive disclosure needs no second mental model to use it.

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

Because the index is loaded on every task, it is held to a token ceiling (`verify.index_token_budget`). `bearing index` fails when the estimate exceeds it. An always-loaded file that grows without bound silently reverses the framework's value: at some size, the cost of carrying the index exceeds the cost of the rework it prevents, and nothing in the system would otherwise notice that point being crossed.

---

## What this deliberately reuses rather than reinvents

The evidence schema, the five confidence axes, the cost ledger, the acceptance-rate and cost-per-promoted-candidate metrics, and the Gold/Dark/Negative evaluation sets all carry over unchanged from Decision Recovery — the ledger at `.bearing/ledger/cost.jsonl` and the sets at `.bearing/eval/`, per that spec's purity rule. Interview transcripts can even be added to the Dark Set over time — a live, authority-checked interview is close to the best available ground truth for "what does a knowledgeable human believe can defensibly be recovered here," which is exactly what the Dark Set is for. Under `retention: none` that particular option is given up, which is a real cost of that setting and worth stating rather than discovering later.

Interview duration is logged exactly, and one thing it inherits is the reporting policy: it is minutes until a reviewer rate is configured, and never converted to a dollar figure on BEARING's initiative.
