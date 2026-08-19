# Decision Records

This directory tree is the authored, authoritative source of decisions governing this repository. Records are numbered, sequential, and version-controlled with the code they describe.

## What's here

- **Numbered `*.md` files** — authored ADRs, either directly here or in category subdirectories. Each carries a Status (`Proposed | Accepted | Deprecated | Superseded`), and code that depends on one links back via `@see ADR-XXX`.
- **`index.json`** — a compact, generated index compiled recursively from every authored ADR. Regenerated automatically on promotion; never hand-edited. Structured for progressive disclosure — an agent loads this cheap index first and only pulls a full ADR body when its scope or trigger phrase matches the current task.
- **`shadow/`** — candidate decisions inferred by `decision-recovery` and `decision-interview`. **Nothing in `shadow/` is authoritative.** See `shadow/README.md`.

## Adding a decision

1. Copy the template pattern from `0001-record-architecture-decisions.md`.
2. Use the next repository-wide sequential number, zero-padded. Both `000N-short-title.md` and `ADR-000N-short-title.md` are supported.
3. Place it here or in a descriptive category directory such as `auth/` or `frontend/`. Categories do not create separate ADR namespaces; every ADR ID must remain unique across the tree.
4. Link the implementation it governs with `@see ADR-000N` in an annotation.
5. Run the index regeneration so `index.json` picks it up.

Every scan-recognized `@see ADR-NNNN` is a governing Anchor. Use an ordinary
prose link for related reading that does not claim the decision governs or
explains that implementation.

See `/BEARING.md` for the full architecture this directory is part of, and `/QUICKSTART.md` for an orientation and optional evaluation paths.
