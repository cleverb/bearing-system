# Skill Spec: Decision Onboarding

`.agents/skills/decision-onboarding/`

*Primes a repository for BEARING. Not a new mechanism — a bounded, sequenced composition of `decision-recovery` and `decision-interview`, run once per repository, that produces one reviewable branch and a frozen baseline to test it against.*

---

## What this Skill is and isn't

**Is:** a one-time (per repository) orchestration that scaffolds the structure, runs a deliberately *scoped* recovery pass, conducts a small number of seed interviews, promotes a small number of Anchors, and hands off to normal operation — all as commits on one branch.

**Is not:** a general-purpose Recovery run. Onboarding's entire design is about doing *less* than Recovery is capable of on day one, on purpose — proving the loop closes on a small area before ever pointing full-strength extraction at an entire legacy codebase.

## Trigger

Explicit human invocation only — `decision-onboarding init`, run once by whoever owns the pilot. Never automatic, never re-run silently on a repository that's already onboarded.

## Pipeline

### Step 0 — Fork and freeze

Before anything else: create the onboarding branch, and tag the commit it forked from.

```
git tag bearing-baseline-<repo>-<date>
git checkout -b bearing-onboarding/<repo>
```

This exists because everything downstream depends on comparing "with BEARING" against "without" — and if main keeps moving during onboarding, that comparison is measuring drift, not the framework. The frozen tag, not whatever main happens to be on the day a given test ticket runs, is the baseline for every comparison in Step 5.

### Step 1 — Scaffold

Pure structure, no judgment calls:

```
docs/decisions/
├── README.md          # states what's authoritative; explains shadow/
├── index.json          # empty
└── shadow/
    ├── README.md
    ├── candidates.jsonl   # empty
    └── rejected.jsonl     # empty

.agents/
├── skills/              # decision-recovery, decision-interview installed, not yet run
└── AGENTS.md             # stub — escalation rules, pointer to docs/decisions/
```

### Step 2 — Scoped Recovery pass

Run `decision-recovery`, restricted to one directory or service — never the whole repository. This is the single most important discipline in the entire onboarding procedure. Unscoped Recovery on a repo with zero existing Anchors produces a large, low-quality first batch, which is exactly the situation the acceptance-rate kill switch exists to catch — except on day one there's no history yet for that metric to be meaningful against. Scope narrow enough that a human can actually review everything the pass produces.

**Scope selection is coordinated with Step 5's test tickets, not made independently.** Whoever picks the scope for this step should be the same person flagging which upcoming tickets will exercise it. Picking scope and picking test tickets separately is close to guaranteeing a null result later — most tickets won't touch what was just recovered, and the pilot will look like it didn't help when the real story is that it was never tested against the part that changed.

### Step 3 — Seed Interviews

A short, targeted list of `decision-interview` sessions — the one or two people who'd feel it most if an agent got something wrong in the scoped area. Highest-risk Contracts first. Not comprehensive coverage; the goal is proving the interview mechanism works end-to-end on real, current knowledge, not documenting everything that person knows.

### Step 4 — First Anchors

Promote a small, deliberate number of candidates from Steps 2 and 3 — 3 to 5, not everything the passes surfaced. Each promotion follows the full lifecycle from the Recovery and Interview specs: a human determines scope, current validity, and lifecycle state, not just confirms a summary. Each promoted candidate gets a real ADR in `docs/decisions/`, an `@see` annotation on the implementation it governs, and an entry in `docs/decisions/index.json`.

The number is small on purpose. The goal of onboarding is proving the whole loop closes — evidence → candidate → promoted → annotated → an agent actually respects it next session — not maximizing graph coverage on day one.

### Step 5 — Pilot: onboarding branch vs. frozen baseline

This is where the branch stops being a bootstrap artifact and starts being a test fixture.

**Setup, before running any tickets:**
- Define the pass/fail bar *now*, not after seeing results. A concrete threshold — e.g., Contract-violation rate on the scoped area drops below X%, rework rate on those tickets improves by Y% — turns this from an open-ended experiment into something with an actual decision point at the end. Record it in `references/pass-fail-criteria.md` before Step 5 begins.
- Select test tickets from the coordination done in Step 2 — tickets that genuinely touch the scoped, recovered area.

**Run each selected ticket twice:** once against the frozen baseline tag, once against the onboarding branch. Same ticket, same starting prompt, two different context conditions.

**Track, per run, not just token count:**
- token consumption (cost, same ledger shape as Recovery/Interview)
- rework rate — how many follow-up corrections did the result need
- Contract-violation rate — did the agent violate something the onboarding branch had documented that the baseline agent had no way to know about
- escalation correctness — did the agent stop and ask when it should have, rather than guess

Token count alone is a genuinely ambiguous signal here and shouldn't be reported in isolation: the onboarding branch will very likely use *more* tokens per session, because it's now loading `AGENTS.md`, the disclosure index, and relevant Contract summaries that the baseline never had. Higher token use paired with lower rework and lower Contract-violation rate is the framework working as intended, not a cost overrun. Token count reported alone, without those outcome metrics next to it, is close to meaningless either direction.

### Step 6 — Handoff

Onboarding mode ends. The branch — scaffold, promoted Anchors, seed interview outputs, pilot results — is reviewed as one PR against the criteria set in Step 5. If it clears the bar, it merges, and the repository moves to normal operation: `decision-recovery` runs on its regular schedule (not scoped anymore, or scoped by whoever owns the next area), `decision-interview` fires ad hoc on escalation same as any repository. If it doesn't clear the bar, the branch and its pilot data are still useful — they're evidence for what the scope, seed set, or promotion choices got wrong before trying again, not a discarded experiment.

---

## Directory structure

```
.agents/skills/decision-onboarding/
├── README.md
├── SKILL.md
├── scripts/
│   ├── freeze-baseline.py       # step 0 — tags the fork point
│   ├── scaffold.py              # step 1 — pure structure
│   └── evaluate-pilot.py        # step 5 — computes metrics against the frozen tag
├── subagents/
│   └── onboarding-coordinator.md   # sequences steps 0–6, enforces scope discipline
└── references/
    └── pass-fail-criteria-template.md
```

## Success Criteria

- The onboarding branch is one reviewable PR, not four disconnected artifacts.
- Every promoted Anchor traces to a candidate in `docs/decisions/shadow/candidates.jsonl`.
- The pass/fail bar was written down before Step 5 ran, not after.
- Test tickets in Step 5 were selected to overlap Step 2's scope, not chosen independently.
- Token consumption is never reported without a paired outcome metric.
