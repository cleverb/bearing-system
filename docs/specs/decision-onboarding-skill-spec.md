# Skill Spec: Decision Onboarding

*Facilitates a bounded trial of BEARING so maintainers can decide whether and
how to adopt it. It is not an installation system or a mandatory experiment
protocol.*

## Product boundary

Onboarding owns guidance, discoverability, and optional evaluation helpers. It
does not own a team's branch strategy, recovery cadence, interview process,
success threshold, or decision to continue.

`bearing init` bootstraps a repository. `bearing onboard` checks readiness,
records resumable hints, and points to the Skill. Neither command mines history,
promotes a candidate, creates a branch or tag, or declares adoption successful.

The only non-negotiable boundaries are BEARING's authority rules:

- inferred candidates remain non-authoritative;
- promotion requires human judgment;
- inference and evaluation results do not block merges; and
- destructive or surprising git operations require user agreement.

## Evaluation depth is a user choice

The Skill offers several useful entry points:

1. **Orientation:** bootstrap, inspect the index and contextual lookup, and ask
   maintainers whether the model is understandable.
2. **Real-work trial:** use BEARING during ordinary changes and note useful
   context, friction, false escalation, and gaps.
3. **Audit:** recover a bounded set of shadow candidates without promotion.
4. **Comparative pilot:** compare a baseline and BEARING-assisted condition with
   pre-declared criteria and paired measurements.

These may be combined, reordered, or stopped early. The `pilot`, `thorough`, and
`audit` profiles are presets for optional helpers, not maturity levels.

## Suggested activities

| Activity | Mechanism | Required? |
| --- | --- | --- |
| Bootstrap and diagnose | `bearing init`, `bearing doctor`, `bearing render` | bootstrap is needed to use repository features |
| Choose representative work | one area, ticket, or recurring point of confusion | recommended |
| Surface missing context | `decision-recovery` or `decision-interview` | no |
| Promote useful decisions | human review, ADR, Anchor, `bearing index` | no |
| Evaluate | qualitative review, ordinary-work observation, or comparative metrics | user-selected |
| Handoff | document what helped, what did not, and the maintainer's choice | recommended |

A small scope is usually easier to review, but BEARING does not enforce a fixed
candidate count or require all activity to occur on one branch.

## Optional comparative pilot

Teams seeking stronger evidence may:

- freeze a baseline and use a dedicated branch;
- write criteria before running the comparison;
- choose tickets that exercise the same area as the recovered context;
- run paired baseline and BEARING-assisted conditions; and
- record rework, Contract violations, escalation correctness, cost, and
  maintainer experience.

These controls reduce confounding but cost time and may not suit an early trial.
The template at `.bearing/ledger/pass-fail-criteria.md` and `bearing report
--pilot` support the method without making it a gate. Missing or late criteria
produce an advisory. Incomplete measurements are shown with caveats.

## Workspace state

All runtime state stays outside the installed plugin:

```text
.bearing/
├── config.json
├── ledger/
│   ├── cost.jsonl
│   └── pass-fail-criteria.md
└── runs/
    └── onboarding.json
```

The criteria file and ledger are optional operator data. The onboarding state is
a convenience for resuming a guided flow, not an authoritative lifecycle record.

## Success and exit

The desired output is evidence proportionate to the user's question: what was
tried, what helped, what created friction, and whether maintainers want to
expand, revise, pause, or remove BEARING. Completion of every helper, a fixed
number of Anchors, and a statistically controlled pilot are not prerequisites.
