# decision-recovery

Batch archaeology over commits, PRs, and tickets for evidence of undocumented decisions. Produces candidates in `docs/decisions/shadow/`, never writes directly to `docs/decisions/`.

Full spec: see `SKILL.md` in this directory, and the extended rationale in the project's `decision-recovery-skill-spec.md`.

Maintained automatically: `schemas/` and `scripts/` define the pipeline; `subagents/` are generated/maintained per BEARING's subagent convention; `references/` holds this Skill's own evaluation sets (gold/dark/negative) and cost ledger — self-monitoring data, not decision content.

Run schedule: weekly batch by default, scoped per repository policy. Never triggered per-commit or per-PR.
