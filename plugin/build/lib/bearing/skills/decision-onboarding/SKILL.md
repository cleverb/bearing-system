---
name: decision-onboarding
description: Help a repository try BEARING, establish a small amount of useful decision context, and evaluate whether it is worth continuing. Use when asked to onboard, pilot, or evaluate BEARING. Offers an adaptable path rather than imposing an experimental protocol.
metadata:
  bearing-role: facilitation
  run-once-per-repo: true
---

# Skill: Decision Onboarding

## Purpose

Help maintainers get enough first-hand evidence to decide whether and how
BEARING should be used in their repository. This Skill facilitates adoption; it
does not own the repository's branch strategy, evaluation rigor, recovery
schedule, or definition of success.

## Invocation

Explicit human invocation only. `bearing onboard` checks readiness and exposes
optional helpers; the human chooses the depth and order of the evaluation.

## Suggested path

Adapt or stop this path whenever the user has enough evidence:

1. Bootstrap with `bearing init`, then use `bearing doctor` and `bearing render`
   to confirm the repository can load its decision context.
2. Choose a small area or ordinary piece of work where missing rationale is
   already causing friction.
3. Surface useful context. Run a bounded recovery pass or an interview only when
   it helps; neither is required.
4. If warranted, have a human promote one or a few decisions and add Anchors.
5. Observe whether the context improves real work. Use qualitative review, a
   before/after comparison, paired tickets, or a formal pilot according to the
   team's needs.
6. Hand the result back to the maintainers. They decide whether to expand,
   revise, pause, or remove the experiment.

Branches, baseline tags, fixed candidate counts, pre-registered thresholds, and
paired runs are optional controls for teams that want a more formal evaluation.
Do not create or require them without the user's agreement.

## Evaluation options

- **Orientation only:** verify discoverability and ask maintainers whether the
  decision context is understandable and useful.
- **Real-work trial:** use BEARING on one or more normal changes and record
  concrete wins, friction, false escalations, and missing guidance.
- **Comparative pilot:** compare a baseline and BEARING-assisted condition. The
  supplied criteria template and report are aids, not gates.
- **Audit:** recover candidates without promoting anything, then decide whether
  deeper adoption is worthwhile.

Cost, token, rework, Contract-violation, and escalation metrics can inform the
decision. No one metric is universally required, and incomplete measurements
must be labelled rather than rejected.

## Hard boundaries

- Only a human may promote inferred material into authoritative decisions.
- Shadow candidates remain non-authoritative regardless of confidence.
- No inference or onboarding score may block a merge.
- Do not perform destructive or surprising git operations; confirm any branch,
  tag, or history-changing workflow with the user.
- Do not claim the repository is fully onboarded merely because a checklist ran.

## Success

Onboarding succeeds when maintainers have enough concrete evidence to make an
informed adoption decision. A formal pilot, a single onboarding branch, a fixed
number of Anchors, and completion of every available helper are not required.
