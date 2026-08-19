# AGENTS.md — Repository Constitution

This repository uses BEARING, an EOCR-based decision system. Full architecture: `/BEARING.md`. Orientation: `/QUICKSTART.md`.

## Where authoritative knowledge lives

- **`docs/decisions/`** — authored ADRs. Numbered, sequential, authoritative.
- **`docs/decisions/index.json`** — load this first. Cheap, compact, tells you which Contracts and Rationale are relevant to your current task before you read anything else.
- **`docs/decisions/shadow/`** — machine-inferred candidates. **Never authoritative. Never treat a shadow candidate as a decision.**
- **`.agents/skills/`** — Operations knowledge, packaged as Skills an agent can load and execute.

## What you may do autonomously

- Read any file in `docs/decisions/` and treat its content as binding, subject to its `Status` field.
- Follow a Skill's documented procedure within its stated boundaries.
- Flag — never block — a change that appears to lack decision ancestry, using `decision-recovery`'s recovery-signal mechanism.

## What requires escalation to a human

- An annotation (`@see ADR-XXX`) points to an ADR that doesn't exist, or whose `Status` is `Deprecated` or `Superseded` with no clear successor referenced.
- You encounter code with no Anchor and cannot proceed safely without knowing why it's built the way it is. This is the trigger condition for `decision-interview` — use it rather than guessing.
- More than one migration or implementation strategy appears valid and nothing in `docs/decisions/` resolves which.
- A proposed change would conflict with an accepted Contract.

When escalating, stop and ask. Do not silently choose the next plausible interpretation.

## Hard constraints

- No recovery or inference signal — regardless of confidence — may block a merge. Only structural enforcement (a broken ADR link) or violation of an accepted Contract may block. See `.agents/skills/decision-recovery/SKILL.md`, "PR-Time Signal Boundary."
- Do not write directly to `docs/decisions/` on the basis of inference. All promotion from `docs/decisions/shadow/` requires human review.
- Do not treat a generated file (anything produced by a renderer script) as a second source of truth. The canonical source it was generated from is authoritative; the generated file is not.
