# decision-onboarding

Helps maintainers try BEARING and decide whether it is useful. It composes the
existing bootstrap, recovery, interview, and reporting capabilities without
requiring a fixed adoption ceremony.

Run explicitly, and adapt the path to the repository:

```bash
bearing onboard
bearing onboard --profile audit
```

`bearing onboard` is a readiness check and guide. It does not create branches or
tags, run recovery, promote decisions, or declare a pilot successful.

## Available approaches

- Orient maintainers and verify that decision context is discoverable.
- Try BEARING during ordinary work and collect qualitative feedback.
- Recover a bounded set of candidates without promoting them.
- Run a comparative pilot using the supplied metrics and criteria template.

The `pilot`, `thorough`, and `audit` profiles are presets for people who want
more structure, not maturity levels or required stages. Branches, baseline tags,
fixed candidate counts, and paired-ticket measurements remain operator choices.

## Workspace data

- Optional evaluation criteria — `.bearing/ledger/pass-fail-criteria.md`
- Optional run measurements — `.bearing/ledger/cost.jsonl`
- Resume hints for the guided flow — `.bearing/runs/onboarding.json` <!-- bearing:ignore-paths -->

Generated runtime adapters derive from
`subagents/onboarding-coordinator.md`; edit the canonical source here.
