# Skill Spec: Decision Recovery

*Surfaces evidence of undocumented architectural decisions as non-authoritative
shadow candidates. BEARING standardizes the evidence boundary and candidate
format, not the scheduler or extraction platform.*

## Product boundary

Decision recovery reads available history—code, commits, reviews, tickets, or
testimony—and prepares evidence for human judgment. It never establishes that a
decision was made and never promotes inferred material into the authored graph.

BEARING supports, but does not mandate:

- opportunistic recovery during ordinary work;
- an explicit bounded manual pass using the shipped Skill;
- operator-owned scheduling through GitHub Actions, cron, or an agent runner;
- a compatible custom extractor; and
- formal scoring, evaluation, budgeting, and cost accounting.

There is no required cadence and no shipped background service. Recovery is not
a live PR gate.

## Three epistemic states

The architecture distinguishes:

1. **Authored decision:** accepted organizational knowledge in the decision
   graph.
2. **Shadow candidate:** evidence suggesting a decision may be recoverable.
3. **Rejected candidate:** reviewed evidence that should not be repeatedly
   surfaced without materially new support.

Confidence describes evidence quality, not organizational authority. A highly
corroborated shadow candidate remains non-authoritative until a human determines
its scope, present validity, lifecycle state, and EOCR function.

## Storage and purity

The installed plugin is read-only. Canonical tooling and schemas live under
`plugin/skills/decision-recovery/`; repository data lives in the workspace:

```text
<decisions.path>/shadow/
├── candidates.jsonl
└── rejected.jsonl

.bearing/
├── ledger/cost.jsonl
└── eval/{gold,dark,negative,escalation}/
```

Use `bearing schema candidate`, `bearing ledger`, and `bearing eval <set>` to
resolve paths. Plugin updates must not erase candidates, run history, or
evaluation fixtures.

## Candidate contract

The JSONL schema is EOCR-aware. A candidate records enough information for a
reviewer to understand:

- the implementation symbol or bounded subject;
- the possible Entry, Operations, Contract, or Rationale function;
- evidence sources and excerpts;
- uncertainty and any conflicting accounts;
- lifecycle and provenance needed to avoid silent overwrite; and
- whether the evidence overlaps a prior rejection.

Detailed confidence axes, corpus-version idempotency, reviewer-time estimates,
and cost rows are useful for repeatable batch programs. They are optional for an
opportunistic candidate unless the operator's chosen workflow requires them.
Every candidate must still satisfy the schema before it is committed.

## Shipped reference workflow

The `decision-recovery` Skill provides a bounded agent-executed workflow:

1. open the Recovery tally and write `.bearing/runs/recovery/` telemetry as
   archaeology proceeds (the App polls; the model is not the heartbeat);
2. choose relevant evidence and scope;
3. extract without inventing organizational intent;
4. cluster related evidence while preserving conflicts;
5. record confidence and provenance;
6. check rejected fingerprints;
7. append schema-valid shadow candidates;
8. run `bearing lint`;
9. complete the run and open Decision Review via `list_reviewable`.

This is a reasonable default, not the architecture of every deployment.
Operators may use another workflow if it preserves the candidate schema and
authority boundary.

## Candidate disposition

A shadow candidate may be committed alongside the work that exposed it or in a
separate focused change. Separate commits often make review clearer; same-change
commits can preserve useful context and reduce lost follow-up. A local stash is
acceptable as short-lived interruption management, not durable storage.

Commit placement does not change authority. Promotion is a separate human
workflow that may reject, revise, split, defer, or promote the evidence.

**BEARING permits one-click execution of a human promotion decision. It
forbids one-click substitution for that decision.** A UI or CLI **Promote**
action is valid when it carries human-determined scope, present validity,
authored lifecycle state, and EOCR function, then scaffolds the ADR and
updates the shadow queue. Auto-promoting because confidence is HIGH — or a
bare Approve that copies the candidate unchanged into Accepted EOCR — is not.

Operators clear the queue with `bearing review`, `bearing dispose`, or the
`bearing-mcp` stdio server (`open_recovery`, `report_recovery`,
`list_reviewable` / `review_candidate`). Hosts that cannot render MCP Apps
receive JSON fallback; Promote still requires human judgment fields.

## Optional operational controls

For teams running recovery repeatedly, BEARING provides building blocks rather
than a prescribed service:

- evidence reliability, authority, corroboration, specificity, and temporal
  relevance axes;
- gold, dark, negative, and escalation evaluation sets;
- model-tier configuration;
- cost, reviewer-time, and acceptance reporting;
- budgets and stop signals; and
- review waves.

These controls can improve repeatability. They are not required to start using
recovery, and their thresholds do not create organizational authority. Model
choice and scheduling remain operator facts.

## Hard enforcement boundary

A recovery signal may flag and route evidence for review. It must never block a
merge, regardless of confidence. Only structural failures such as a broken ADR
link, or a demonstrated violation of an accepted Contract, may block.

## Useful outcome

Recovery is useful when a reviewer receives honest, traceable evidence that
reduces the cost of deciding whether to document something. Completeness, a
weekly run, a target acceptance rate, or a particular cost model are not
framework success criteria.
