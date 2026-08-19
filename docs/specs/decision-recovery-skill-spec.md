# Skill Spec: Decision Recovery

`plugin/skills/decision-recovery/`

*Recovers evidence of latent, undocumented organizational intent from legacy code, commits, and tickets — preserving its provenance and uncertainty, and routing it across an explicit human authority boundary before it can participate in the Decision Graph.*

*Supersedes the earlier "Decision Backfill" draft. Renamed deliberately: this Skill does not manufacture missing documentation. It asks whether evidence exists that undocumented intent shaped an implementation — and sometimes the honest answer is no.*

---

## What this Skill is and isn't

**Is:** a background process that reads legacy code, commits, PRs, and tickets, and surfaces evidence — with its reliability, authority, and age all preserved separately — for a human to judge.

**Is not:** a live PR reviewer, a source of truth, a recursive or self-invoking agent, something that writes to `docs/decisions/` on its own, or a system that determines whether a decision was actually made. It determines whether evidence *of* a decision exists. Those are different claims, and the schema below is built to keep them different.

The design constraint everything serves: **the shadow graph of recovered evidence stays separate from the authored Decision Graph until a human deliberately crosses that boundary — and crossing it is a judgment, not a click.**

```
Shadow Graph                              Decision Graph
Evidence → Candidate → Corroboration  │   Authored EOCR Knowledge → Lifecycle
   → Human Judgment                   │      → Anchors → Contracts → Execution
                                       │
                          authority boundary
```

*A note on scope:* this document treats **Recover** as a capability this Skill performs, not as a claim about the core Decision-System vocabulary (`Discover → Anchor → Constrain → Execute → Verify → Evolve`). Whether Recover deserves to sit as a peer stage in that sequence, or is better understood as a bridge operation that feeds into Discover and Anchor once evidence clears the authority boundary, is an open question for the main document — this spec doesn't resolve it, and doesn't need to in order to be built.

### Three epistemic states, not two

The main document's Projection section already establishes that a generated file doesn't independently acquire authority — it derives its authority from the canonical source it was generated from. Recovery is a second, distinct application of that same principle, and naming it explicitly is what keeps this Skill from reading as a separate mechanism bolted onto the architecture rather than a natural extension of it:

- **Authored knowledge** — written by a human, or by an agent under direct review — is *potentially authoritative*. It carries organizational weight once accepted.
- **Generated projection** — a `.cursor/`, `.codex/`, or similar runtime-native file — is *derived from authority*. It has no standing of its own; it inherits whatever the canonical source it was rendered from already had.
- **Inferred knowledge** — anything this Skill produces — is *evidence about possible authority*. It doesn't derive authority from anything, and it doesn't inherit any either. It has to earn it, explicitly, by crossing the human review boundary.

Three different claims, three different standings. The candidate schema throughout this spec exists specifically to keep the third from ever being mistaken for the first.

---

## Directory structure

This Skill ships inside the plugin. Its *output* — the shadow graph — does not, and neither does any other file written at runtime. See "Where the shadow graph actually lives" and "The purity rule" below.

```
plugin/skills/decision-recovery/
├── README.md                             # maintenance model, kept current automatically
├── SKILL.md                              # this Skill's instruction set
├── schemas/
│   ├── candidate.schema.json             # resolved by `bearing schema candidate`
│   └── evidence.schema.json
├── scripts/
│   ├── extract.py                        # stage 1 — cheap-tier, bulk
│   ├── resolve.py                        # stage 2 — mid-tier, clustering + conflict detection
│   ├── score.py                          # stage 3 — mid-tier, axis scoring (not a single scalar)
│   └── budget-tracker.py                 # cost + reviewer-time ledger, hard stop
├── subagents/
│   ├── decision-archaeologist.md         # canonical; runs extraction and resolution
│   └── decision-recovery-reviewer.md     # canonical; prepares — never makes — the promotion judgment
└── references/
    ├── evaluation-sets.md                # documents the format; the sets themselves live in the workspace
    └── cost-ledger-format.md             # documents the ledger; the ledger itself lives in the workspace
```

### The purity rule

**Nothing writes inside the plugin at runtime.** Both Cursor and Claude Code *copy* a plugin into a versioned cache and replace that copy on update, so a file written inside the installation is a file scheduled for silent deletion. An earlier draft of this spec put the cost ledger and all three evaluation sets in `references/`; on the first plugin update, a repository would have lost its entire run history and its ground-truth corpus, and the kill switch would have quietly reset to "not enough history."

So the split is by lifetime, not by subject:

| Kind | Lives in | Why |
| --- | --- | --- |
| Instructions, schemas, scripts, templates, canonical subagents | the plugin, read-only | Ships with a version; identical for every repository |
| Cost ledger, evaluation sets, price-book corrections, run state | `.bearing/` in the workspace | Accumulates over time; specific to this repository |
| Candidates, rejections, transcripts, the disclosure index | the decisions directory | Decision content — the repository's knowledge, not BEARING's |

The same rule is what makes `bearing uninstall` honest: everything BEARING generated can be removed without touching anything a human wrote or a run measured. It is verified rather than promised — the packaging suite makes the plugin tree read-only and runs a full pipeline against it, and CI installs from a git ref into an unrelated directory and asserts the tree is byte-identical afterwards.

The same reasoning forbids `../` paths between skills. Agent Plugins v1.0.0 §4.1.3 requires a client to reject any package path resolving outside the plugin root, so `decision-interview` cannot reach `../decision-recovery/schemas/candidate.schema.json` — it asks the CLI (`bearing schema candidate`), which resolves from the plugin root and therefore works whether BEARING is installed, vendored, or run from a checkout.

## Where the shadow graph actually lives

The shadow graph, the disclosure index, and the rejection ledger are decision *content* — evidence about the same repository `docs/decisions/` already documents — not Skill tooling. They live there, not under `.agents/`:

```
docs/decisions/                # or docs/adr/ — whatever this repository already uses
├── README.md                  # documents the index and shadow/ below; states plainly what's authoritative
├── index.json                 # generated from the .md files in this directory — regenerated, never hand-edited
├── 0001-....md                # authored ADRs — the only authoritative content at this level
├── 0002-....md
└── shadow/
    ├── README.md              # first line: nothing in this folder is authoritative
    ├── candidates.jsonl       # shadow graph — written by decision-recovery AND decision-interview
    ├── rejected.jsonl         # rejection fingerprints, checked at resolution to prevent re-litigation
    └── transcripts/           # interview evidence, inheriting the shadow graph's standing
```

The directory name is a repository fact, resolved from `decisions.path`, and `bearing init` **detects** it rather than imposing one. A repository already using `docs/adr/` keeps `docs/adr/`; BEARING never renames or migrates an existing corpus, because demanding a bulk move before the tool does anything useful is the same adoption friction the retrospective path exists to avoid. Every path above derives from that one setting, and nothing in the implementation hardcodes `docs/decisions` — which is checked by a test, since a single hardcoded default is enough to make the whole setting a fiction.

Three things do the actual work of keeping this separation real rather than just a naming convention, since the single most repeated invariant in this whole architecture — inference stays a candidate graph, the authored graph stays authored — is exactly what a careless placement here could quietly undermine:

- **Format is a genre signal.** Authored decisions are `.md`, meant to be read as prose. Shadow content is `.jsonl`, structured data meant to be queried. Nobody mistakes a ledger line for a written decision record the way they might mistake one markdown file sitting next to another.
- **A folder boundary, not just a filename convention.** `shadow/` sits one level below `docs/decisions/`, so a directory listing at the top level shows only authored decisions plus one clearly-named subfolder — candidates are never interleaved with real ADRs.
- **Enforcement extends to check it.** The same linter that validates `@see` links now also asserts that no Anchor ever points into `docs/decisions/shadow/`. That closes the gap between the README saying this isn't authoritative and the system actually verifying it can't be treated as such.

The Skill's own operational data — the cost ledger, the Gold/Dark/Negative eval sets — is the Skill monitoring itself rather than knowledge about the repository, so it does not belong with the decisions corpus. It does not belong inside the plugin either, per the purity rule above. It lives in `.bearing/`:

```
.bearing/
├── ledger/cost.jsonl          # append-only run history — Skill self-monitoring
├── pricing.json               # price-book corrections, merged over the packaged defaults
└── eval/
    ├── gold/                  # known decisions, known Anchors — tests recall
    ├── dark/                  # undocumented legacy, independently investigated — tests real recovery
    ├── negative/              # historical chatter with no defensible decision — tests hallucination rate
    └── escalation/            # cases whose correct answer is known — tests ESCALATE recall
```

These are per-repository by nature, which is the second reason they cannot ship in the plugin: a Dark Set is only meaningful against the legacy code it was investigated in, and a cost ledger from someone else's repository tells you nothing about yours.

## The candidate schema is EOCR-aware, not Rationale-shaped

The earlier draft's extraction output — `(source_excerpt, inferred_rationale, source_type, source_ref)` — quietly assumed all recovered evidence is Rationale. It isn't. A commit can just as easily reveal a Contract ("never call this concurrently") or Operations ("run migration X before enabling Y") as a rationale for a design choice.

```json
{
  "candidate_id": "cand-2026-08-16-0431",
  "subject": "PaymentGateway.retryPolicy",
  "candidate_relation": "governed_by",
  "candidate_object": "unclear — retry ceiling appears deliberate, no formal record found",
  "candidate_eocr_function": "Contract",
  "temporal_scope": "evidence dated 2024-03 through 2024-11; applicability to current code unconfirmed",
  "evidence": [
    {
      "evidence_source": "commit_message",
      "evidence_excerpt": "cap retries at 3, more than that trips the vendor's rate limiter",
      "evidence_reliability": "HIGH",
      "organizational_authority": "UNKNOWN",
      "corroboration": "MEDIUM",
      "specificity": "HIGH",
      "temporal_relevance": "HISTORICAL"
    },
    {
      "evidence_source": "pr_description",
      "evidence_excerpt": "matches what payments team asked for after the incident",
      "evidence_reliability": "MEDIUM",
      "organizational_authority": "MEDIUM",
      "corroboration": "MEDIUM",
      "specificity": "MEDIUM",
      "temporal_relevance": "HISTORICAL"
    }
  ],
  "confidence": "MEDIUM",
  "confidence_breakdown_available": true,
  "lifecycle_state": "Corroborated",
  "idempotency_key": "PaymentGateway.retryPolicy::corpus-v14::extractor-v3"
}
```

**Confidence stays a single collapsed value in the queue by default — the five axes underneath it are computed and stored, not discarded.** This is a deliberate compromise, not an oversight: fully exploding five visible axes per candidate would reintroduce the complexity the review queue is specifically designed to avoid (see "Comprehensibility" in the prior spec). So the top-line `confidence` is what a reviewer sees first; the breakdown is one click away, and is surfaced automatically — not optionally — whenever a candidate has conflicting evidence or is contested, since that's exactly the case where "the model is confident Bob said this" and "the model has no basis for knowing whether Bob had authority to say it" stop being the same claim.

The five axes, computed at the `score` stage and never collapsed into each other silently:

- **Evidence reliability** — how directly does this artifact support the inferred proposition?
- **Organizational authority** — did whoever produced this have standing to establish the decision?
- **Corroboration** — how many independent sources support it?
- **Specificity** — how unambiguous is the statement?
- **Temporal relevance** — does the evidence still appear to apply, or is it historical?

## SKILL.md

```markdown
# Skill: Decision Recovery

## Context
Undocumented decisions accumulate as commit messages, PR descriptions, and
comments — but never as `@see ADR-XXX` annotations or entries in
docs/decisions/. This Skill recovers evidence of such decisions and routes
it to a human for judgment. It does not assert that a decision was made —
only that evidence suggesting one exists. It never writes to
docs/decisions/ or adds annotations directly.

## Trigger
Runs as a scheduled batch job (default: weekly) against a bounded scope.
Never a live PR check. Never triggered per-commit.

## Pipeline (bounded, non-recursive)

1. EXTRACT (Haiku-tier, decision-archaeologist): scan the scoped corpus
   once. For each code symbol with no existing Anchor, extract candidate
   evidence tagged with its EOCR function (Entry / Operations / Contract /
   Rationale) — not assumed to be Rationale by default. Runs once per item
   per corpus version. No self-invocation.

2. RESOLVE (Sonnet-tier, decision-archaeologist, candidates only): cluster
   evidence referring to the same underlying decision. If evidence
   conflicts, do NOT reconcile it into one confident answer — emit a
   "conflicting evidence" candidate with all sources attached and
   confidence capped at LOW.

3. SCORE (Sonnet-tier): compute all five evidence axes (reliability,
   authority, corroboration, specificity, temporal relevance) per source,
   and a collapsed top-line confidence for the queue. Store the full
   breakdown regardless of whether it's surfaced by default.

4. QUEUE: candidates are written to docs/decisions/shadow/candidates.jsonl
   and enter lifecycle state Detected, then Corroborated once resolution
   completes. Reviewable candidates are those with confidence MEDIUM or
   higher, OR any LOW candidate meeting an exception below.

## Instructions for the Agent
1. Never write directly to docs/decisions/ or add a code annotation.
   Output is always a candidate in the shadow graph, never a commit.
2. Never claim a decision "was made." Claim only that evidence exists
   suggesting one may have been. Preserve that distinction in every
   candidate summary.
3. Idempotency key is `symbol + source-corpus-version + extractor-version`
   — NOT symbol alone. Unchanged evidence is never reprocessed. New
   evidence (new corpus version) or a changed extractor makes a symbol
   eligible for reconsideration, even if a prior candidate exists. A
   candidate whose evidence base has materially changed since it was
   scored moves to lifecycle state Stale rather than being silently
   overwritten.
4. If resolution produces conflicting evidence, surface the conflict;
   never resolve it by selecting one side.
5. Stop the run and report partial results if the budget cap is reached
   before the scope completes.

## Escalation Rules (LOW-confidence handling)
Default: LOW-confidence candidates are retained in the ledger but NOT
surfaced to the review queue. This is the default specifically to protect
the queue-noise objective — most LOW candidates are exactly the kind of
weak, single-source evidence nobody should spend review time on.

Exceptions — a LOW candidate IS surfaced when:
- it conflicts with an existing accepted ADR, regardless of its own
  confidence, because a contradiction with authored knowledge is itself
  informative even when the new evidence is weak; or
- the subject is flagged load-bearing or high-impact (e.g. touches a
  payment path, an auth boundary, or code already carrying a HIGH-severity
  Contract), where even weak evidence of an undocumented constraint is
  worth a human's attention.

## Model Tiering (Contract)
- Extraction MUST use the cheap tier.
- Resolution and scoring MAY use the mid/frontier tier, but only on the
  candidate set already narrowed by extraction.

Which model fills each role is an operator choice, configured per role in
`models`. The Contract is machine-enforced against the price book, so
configuration cannot silently void it: `bearing doctor` rejects a config
that puts a frontier model on extraction, and rejects a model the price
book has never heard of rather than assuming it is cheap.

## PR-Time Signal Boundary (hard constraint)
If this Skill's output ever feeds a PR-time check, the rule is not
negotiable per-repository: a recovery signal MUST NOT block a merge, under
any confidence score.

Blocking authority belongs only to mechanisms checking against something
already authoritative:
- structural enforcement — "the referenced ADR doesn't exist" — MAY block.
- known-Contract enforcement — "this violates accepted Contract C-17" —
  MAY block.
- a recovery signal — "this change appears to lack decision ancestry;
  confidence 0.87" — MUST only flag and route to review, regardless of how
  high that confidence is.

The reasoning is not caution for its own sake: a confidence score is a
statement about evidence, not a statement of organizational authority. If
an organization later decides a specific high-confidence recovery check
should gate merges, that decision has to be made and written down as an
actual Contract — the gate's authority then comes from that Contract, not
from the model's score. The model's confidence is never itself the source
of blocking power.

## Success Criteria
- Every Reviewable candidate carries: EOCR-tagged summary, collapsed
  confidence, full axis breakdown on request, source excerpts, temporal
  scope, and an idempotency key tied to corpus version.
- No candidate is reprocessed against unchanged evidence.
- Run cost and estimated reviewer time are both logged before any
  candidate is surfaced.
- No recovery signal blocks a merge under any circumstances; only
  structural or known-Contract enforcement may block.
```

## Promotion is a lifecycle, not a button

The earlier draft described review as "click promote-to-ADR or discard." That understates what the human is actually being asked to do, and risks the review becoming ceremonial approval of a well-written summary rather than a real judgment.

```
Detected → Corroborated → Reviewable → Promoted
                                     ↘ Rejected
                                     ↘ Insufficient Evidence
                       (any state) → Stale   (evidence base changed)
```

Promotion is not `candidate → ADR`. It's `candidate → initiate an authored decision-recovery workflow`, in which the reviewer (human, or a `decision-recovery-reviewer` subagent that prepares but never finalizes the judgment) is answering questions the pipeline cannot:

- Is this rationale still valid, or purely historical?
- Is the resulting Contract still authoritative, and what scope does it actually govern?
- Is this a record of a past decision, or does it need to become a current one?
- What lifecycle state should the resulting ADR enter — `Proposed`, or straight to `Accepted` if the evidence is strong enough to just be documenting an existing, unchallenged norm?
- Which implementation should actually carry the `@see` Anchor?

A candidate reaching `Promoted` means a human made that determination — not that they agreed the summary was accurate.

### Rejection needs its own suppression, not just idempotency

The idempotency key (`symbol + source-corpus-version + extractor-version`) stops *extraction* from reprocessing unchanged evidence. It does not, by itself, stop *resolution* from re-deriving something a human already looked at and rejected — a later run, clustering a slightly different mix of evidence after a corpus update, can land on essentially the same candidate the rejection was meant to close out. Idempotency and rejection are solving two different problems and need two different mechanisms.

A `Rejected` candidate therefore carries its own suppression record, checked at resolution time, not just extraction time:

- `rejection_reason` (free text, why a human determined this wasn't a real decision, or wasn't one worth documenting)
- `rejected_evidence_fingerprint` (a hash or signature of the evidence set that produced the rejected candidate)

Resolution checks new clusters against docs/decisions/shadow/rejected.jsonl before emitting a new candidate. If a new cluster's evidence substantially overlaps a rejected fingerprint, it is suppressed by default — logged, not surfaced — unless the new run introduces evidence the fingerprint doesn't cover, in which case it's allowed through as a genuinely new candidate rather than a resurfaced old one. This is what actually keeps a human's "no, that's not a real decision" from being re-litigated by the pipeline every few weeks.

## Evaluation: three sets, not one

Precision/recall against well-annotated code (the original **Gold Set**) tests whether the pipeline can rediscover decisions that are already documented — necessary, but it has a selection bias: well-annotated code is usually easier to reason about than the genuinely undocumented legacy code this Skill actually targets.

- **Gold Set** — known decisions, known Anchors. Tests recall against ground truth.
- **Dark Set** — undocumented legacy areas, independently investigated by knowledgeable humans who record what they believe can defensibly be recovered, compared against the pipeline's output. Tests real-world recovery quality where there is no ground truth to check against directly.
- **Negative Set** — code with historical chatter (comments, commit noise) but no defensible organizational decision behind it. Tests the pipeline's propensity to manufacture a plausible-sounding decision where none existed. This is the set that matters most for trust: the risk isn't only missing real decisions, it's inventing fictional ones that read just as convincingly.

All three are checked before a new extractor version or model tier goes live, not just the Gold Set.

They live in `.bearing/eval/` in the workspace, and they start out empty. `bearing verify` reports an absent set as a **skip carrying its reason**, never as a pass — a conformance suite that reports green because it had nothing to measure is worse than one that fails, because it actively misinforms. The skip names the file to create and what belongs in it.

---

## Economy: cost, and the cost that actually dominates

### A price is a dated fact, not a constant

The ledger records **tokens**, not dollars. Dollars are derived at report time from a dated price book, because a cost figure computed against last year's prices and stored as a number is indistinguishable from a current one.

`.bearing/pricing.json` is merged per model over the packaged `pricing.default.json`, so a repository can correct one price without restating the book and silently losing the rest. Every entry carries `tier`, `as_of`, and a `source` URL. Every figure BEARING reports names the price-book version that produced it, and a book older than `cost.price_book_max_age_days` is reported as stale *in the report*, next to the number, rather than warned about somewhere a reader will not be looking.

A model with no price is excluded from the total and named, never estimated. A silently omitted term makes a total look complete when it is not.

```json
{"run_id": "2026-08-16-weekly", "stage": "extract", "model": "claude-haiku-4.5",
 "items_processed": 4200, "input_tokens": 3810000, "output_tokens": 214000,
 "token_source": "measured", "candidates_emitted": 340}
{"run_id": "2026-08-16-weekly", "stage": "resolve", "model": "claude-sonnet-4.5",
 "items_processed": 340, "input_tokens": 611000, "output_tokens": 88000,
 "token_source": "estimated", "candidates_emitted": 118}
{"run_id": "2026-08-16-weekly", "stage": "score", "model": "claude-sonnet-4.5",
 "items_processed": 118, "input_tokens": 240000, "output_tokens": 41000,
 "token_source": "measured", "candidates_queued": 61}
{"run_id": "2026-08-16-weekly", "stage": "review", "reviewer": "human",
 "candidates_reviewed": 61, "candidates_promoted": 9,
 "estimated_review_minutes": 87}
```

### Two cost classes, reported differently on purpose

**Model cost** is small and reasonably precise. Each row is marked `measured` or `estimated`; an estimated row widens the reported band by `cost.token_estimate_uncertainty`, so the output is a `low / expected / high` range rather than a point value implying precision the input never had. A total is marked estimated if any contributing row was, because a sum is only as measured as its weakest term.

**Human review cost** dominates, and is the least knowable. It is reported in **minutes**. `cost.reviewer_rate_usd_per_hour` ships unset, and while it is unset BEARING never converts minutes to dollars — inventing an hourly figure for a senior engineer's attention would make the total look most precise exactly where it is least defensible. Supplying a rate is an explicit opt-in.

Every cost report carries a caveat block stating what the numbers ignore: prompt caching, batch discounts, committed-use pricing, and any negotiated rate, all of which move real spend materially. The block's central point is that **the paired delta** between a baseline run and a BEARING run on the same ticket under the same price book is the deliverable, because pricing error is largely common-mode and mostly cancels in a difference while not cancelling at all in an absolute total.

### The metrics that decide whether this keeps running

Two derived metrics, and together they answer the "does this justify itself" question more honestly than either alone:

**Acceptance rate** (promoted ÷ reviewable) — the original signal, kept, but now understood as necessary and not sufficient. A repo generating 100 trivial candidates at 30% acceptance and a repo generating 5 candidates at 20% acceptance where the one hit is a previously undocumented security constraint are not the same kind of system, even at similar rates.

**Cost per promoted candidate** (total model cost + `estimated_review_minutes` × the configured reviewer rate, divided by candidates promoted) — this is the metric that actually catches the case acceptance rate alone misses. It doesn't require an elaborate ROI engine; it's arithmetic over fields already in the ledger. The point isn't precision — it's making the dominant cost (a senior engineer's review time, not Haiku tokens) visible in the same number that decides whether the Skill keeps running on a given repository.

Because review time is the dominant term, this metric is **withheld entirely** when no reviewer rate is configured. That is deliberate rather than a gap: computing it from tokens alone would report the small half and present it as the whole, which is more misleading than reporting nothing and saying why.

The kill switch triggers on a sustained rise in cost-per-promoted-candidate over a trailing window of runs, not on raw acceptance rate alone.

### Waves, not one queue

The hard per-run budget cap stops a runaway. It does nothing about the *review* budget, which is the one that actually gets exceeded. So candidates are surfaced in waves sized by the tighter of `review.wave_size` and what `review.budget_minutes_per_session` can absorb at `review.seconds_per_candidate_estimate` each, and `bearing lint` warns when the queue exceeds one wave. A queue larger than one person clears in the declared budget does not get reviewed carefully; it gets rubber-stamped, which converts the authority boundary into a formality while leaving every metric looking healthy.

---

## What carried over unchanged from the prior draft

Worth stating plainly, since most of the spec's actual safety architecture wasn't in question: the bounded, non-recursive pipeline structure; the prohibition on treating a prior run's candidates as new evidence; keeping this entirely out of the PR review loop by default; and the hard per-run budget cap. None of the feedback touched these, and none of the changes above alter them.
