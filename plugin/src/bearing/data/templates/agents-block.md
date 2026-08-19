## BEARING decision system

This repository uses BEARING, an EOCR-based decision system. Treat this section as binding, not advisory.

### Where authoritative knowledge lives

- **`{{decisions_path}}/`** — authored decision records. Numbered, sequential, authoritative. Each carries a `Status`.
- **`{{decisions_path}}/{{index_file}}`** — load this first. It is compact and cheap, and it tells you which Contracts and Rationale bear on your current task before you read anything else.
- **`{{decisions_path}}/{{shadow_dir}}/`** — machine-inferred candidates. **Never authoritative. Never treat a shadow candidate as a decision.** No `@see` annotation may point here.
- **Skills** — Operations knowledge you can load and execute: `decision-recovery`, `decision-interview`, `decision-onboarding`.

### What you may do autonomously

- Read anything in `{{decisions_path}}/` and treat it as binding, subject to its `Status`.
- Follow a Skill's documented procedure within its stated boundaries.
- Flag — never block — a change that appears to lack decision ancestry.

### What requires escalation to a human

- An `@see` annotation points to a decision record that does not exist, or whose `Status` is `Deprecated` or `Superseded` with no successor referenced.
- You encounter code with no Anchor and cannot proceed safely without knowing why it is built the way it is. This is the trigger for `decision-interview` — use it rather than guessing.
- More than one implementation or migration strategy appears valid and nothing in `{{decisions_path}}/` resolves which.
- A proposed change would conflict with an accepted Contract.

When escalating, stop and ask. Do not silently choose the next plausible interpretation. If you find a `@deprecated` marker with no `@see` link, you are forbidden from refactoring it — open a clarification request instead.

### Hard constraints

- **No inference may block a merge.** A recovery signal may only flag and route to review, regardless of its confidence score. A confidence score is a statement about evidence, never a statement of organizational authority. Only structural enforcement (a broken decision link) or violation of an accepted Contract may block.
- **Do not write to `{{decisions_path}}/` on the basis of inference.** Every promotion out of `{{shadow_dir}}/` requires human review, and that review determines scope, current validity, and lifecycle state — it is not a confirmation that a summary read correctly.
- **A generated file is never a second source of truth.** Anything carrying a `DO NOT EDIT` header derives its authority from the canonical source it was rendered from and has none of its own. Edit the source and re-run `bearing render`.
- **The plugin tree is read-only at runtime.** Writes go to `.bearing/` for run state, or `{{decisions_path}}/` for decision content.

{{contracts_section}}
