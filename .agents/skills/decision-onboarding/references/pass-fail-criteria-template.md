# Pass/Fail Criteria — <repository name>

Fill this out and commit it to the onboarding branch BEFORE Step 5 runs
any test tickets. Do not adjust thresholds after seeing results.

## Scope under test
- Directory / service: <fill in — must match Step 2's recovery scope>
- Baseline tag: bearing-baseline-<repo>-<date>

## Thresholds to clear

| Metric | Baseline (expected) | Bar to clear |
|---|---|---|
| Contract-violation rate on scoped tickets | <measure on baseline first> | e.g. drops below X% |
| Rework rate on scoped tickets | <measure on baseline first> | e.g. improves by Y% |
| Escalation correctness (stopped-to-ask when it should have) | <measure on baseline first> | e.g. improves by Z% |
| Token cost per ticket | <measure on baseline first> | reported alongside the above — not a pass/fail criterion on its own |

## Test tickets selected
List tickets chosen in coordination with Step 2's scope — each should
genuinely touch the recovered/promoted area:
1. <ticket>
2. <ticket>
3. <ticket>

## Decision
- [ ] Bar cleared — proceed to Step 6 handoff, merge the branch.
- [ ] Bar not cleared — branch and pilot data retained as evidence for
      what to change (scope, seed interview selection, promoted Anchors)
      before re-attempting onboarding.
