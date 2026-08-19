# Agent-executed onboarding procedure

There is no `freeze-baseline.py`, `scaffold.py`, or `evaluate-pilot.py`.
`bearing onboard` gates the pipeline; this Skill carries out the steps
with host tools and other Skills.

| Step | Mechanism |
| --- | --- |
| 0a Preflight | `bearing preflight` (also run by `bearing onboard`) |
| 0 Freeze | `git tag bearing-baseline-<repo>-<date>` then `git checkout -b bearing-onboarding/<repo>` |
| 1 Scaffold | `bearing init` then `bearing render` |
| 2 Scoped recovery | `decision-recovery` Skill, one directory or service |
| 3 Seed interviews | `decision-interview` Skill |
| 4 First anchors | Human promotion; `bearing index`; `bearing lint` |
| 5 Pilot | Fill `.bearing/ledger/pass-fail-criteria.md` *before* running tickets; `bearing report --pilot` |
| 6 Handoff | Human PR against the pre-registered bar |
