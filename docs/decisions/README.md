# Decision Records

This directory is the authored, authoritative source of decisions governing this repository. Files here are numbered, sequential, and version-controlled with the code they describe: `0001-record-architecture-decisions.md`, `0002-...`, and so on.

## What's here

- **`*.md` files** — authored ADRs. The only authoritative content at this level. Each carries a Status (`Proposed | Accepted | Deprecated | Superseded`), and code that depends on one links back via `@see ADR-XXX`.
- **`index.json`** — a compact, generated index compiled from the front matter of every ADR in this directory. Regenerated automatically on promotion; never hand-edited. Structured for progressive disclosure — an agent loads this cheap index first and only pulls a full ADR body when its scope or trigger phrase matches the current task.
- **`shadow/`** — candidate decisions inferred by `decision-recovery` and `decision-interview`. **Nothing in `shadow/` is authoritative.** See `shadow/README.md`.

## Adding a decision

1. Copy the template pattern from `0001-record-architecture-decisions.md`.
2. Use the next sequential number, zero-padded: `000N-short-title.md`.
3. Link the implementation it governs with `@see ADR-000N` in an annotation.
4. Run the index regeneration so `index.json` picks it up.

See `/BEARING.md` for the full architecture this directory is part of, and `/QUICKSTART.md` for a 30-minute orientation.
