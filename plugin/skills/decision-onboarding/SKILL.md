---
name: decision-onboarding
description: Bootstrap a repository into the BEARING decision system as one reviewable branch — preflight, freeze a baseline, scaffold, run a scoped recovery pass, seed interviews, promote a small number of first anchors, then measure the result against the frozen baseline. Use once per repository when setting up BEARING, or when asked to onboard, pilot, or evaluate BEARING on a repo.
metadata:
  bearing-role: orchestration
  run-once-per-repo: true
---

# Skill: Decision Onboarding

## Context
Bootstraps a repository into BEARING. Everything downstream (decision-
recovery, decision-interview) assumes docs/decisions/, .agents/, and an
AGENTS.md already exist and are populated with at least some real,
promoted knowledge. This Skill produces that starting state, deliberately
scoped small, as one reviewable branch.

## Trigger
Explicit human invocation only: `decision-onboarding init`. Run once per
repository by whoever owns the pilot.

## Pipeline

### Step 0 — Fork and freeze
Tag the current commit as the baseline before anything else changes:
    git tag bearing-baseline-<repo>-<date>
    git checkout -b bearing-onboarding/<repo>
Every later comparison in Step 5 runs against this frozen tag, not
whatever main happens to be on the day a given ticket runs.

### Step 1 — Scaffold
Pure structure: docs/decisions/ (with README.md, index.json, shadow/),
.agents/ (with AGENTS.md stub and the decision-recovery /
decision-interview Skills installed but not yet run).

### Step 2 — Scoped recovery pass
Run decision-recovery restricted to ONE directory or service — never the
whole repository. This is the single most important discipline in this
Skill. Scope selection is coordinated with Step 5's test ticket
selection — the same person choosing what to recover should flag which
upcoming tickets will exercise that area. Picking scope and picking test
tickets independently risks a null result: most tickets won't touch what
onboarding changed.

### Step 3 — Seed interviews
A short, targeted list of decision-interview sessions with the one or two
people who'd feel it most if an agent got something wrong in the scoped
area. Highest-risk Contracts first, not comprehensive coverage.

### Step 4 — First anchors
Promote 3 to 5 candidates from Steps 2 and 3 — small on purpose. Each
promotion follows the full lifecycle: a human determines scope, current
validity, and lifecycle state, not just confirms a summary. Each gets a
real ADR, a @see annotation, and a docs/decisions/index.json entry.

### Step 5 — Pilot: onboarding branch vs. frozen baseline
Define the pass/fail bar BEFORE running any tickets — record it in
references/pass-fail-criteria.md. Select test tickets from the Step 2
coordination. Run each ticket twice: once against the frozen baseline tag,
once against the onboarding branch. Track per run:
  - token consumption
  - rework rate
  - Contract-violation rate
  - escalation correctness
Never report token count without a paired outcome metric — the onboarding
branch will likely use MORE tokens (loading AGENTS.md, the index, Contract
summaries); higher token use with lower rework is the framework working
as intended, not a cost problem.

### Step 6 — Handoff
Onboarding mode ends. The branch is reviewed as one PR against the
criteria set in Step 5. If it clears the bar, it merges and the repository
moves to normal operation — decision-recovery on its regular schedule,
decision-interview ad hoc on escalation. If it doesn't clear the bar, the
branch and pilot data are still evidence for what to change before trying
again — not a discarded experiment.

## Success Criteria
- The onboarding branch is one reviewable PR, not four disconnected
  artifacts.
- Every promoted Anchor traces to a candidate in
  docs/decisions/shadow/candidates.jsonl.
- The pass/fail bar was written down before Step 5 ran, not after.
- Test tickets in Step 5 overlap Step 2's scope.
- Token consumption is never reported without a paired outcome metric.
