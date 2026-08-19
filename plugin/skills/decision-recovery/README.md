# decision-recovery

Batch archaeology over commits, PRs, and tickets for evidence of undocumented decisions. Produces candidates in the workspace shadow graph and never writes to the authored decision record directly.

## What is in this directory

Generic, versioned tooling only. Nothing here is written to at runtime.

- `SKILL.md` — the instruction set an agent loads.
- `schemas/` — `candidate.schema.json` and `evidence.schema.json`. Shared with `decision-interview`, which resolves them through `bearing schema candidate` rather than by a relative path, because a `../` reference to a sibling skill does not survive plugin installation.
- `subagents/` — canonical definitions for `decision-archaeologist` and `decision-recovery-reviewer`. Hand-maintained here and projected into each runtime's native format by `bearing render`; the generated `.md` and `.toml` files carry no authority of their own.
- `references/` — format documentation for the evaluation sets, the cost ledger, and the agent-executed mining procedure. There is no `extract.py`: an agent using git/gh writes JSONL, then `bearing lint` validates it.

## Where this Skill's data actually lives

In the workspace, never in this directory:

- Candidates and rejections — `<decisions.path>/shadow/`
- Cost ledger — `.bearing/ledger/cost.jsonl`
- Evaluation sets — `.bearing/eval/{gold,dark,negative}/`

Resolve these with `bearing ledger` and `bearing eval <set>` rather than assuming a layout. The earlier draft of the spec kept the ledger and eval sets under `references/` here, which would have erased both on every plugin update.

## Invocation model

The operator chooses the mode: opportunistic during ordinary work, an explicit
manual pass, operator-owned automation such as GitHub Actions or cron, or a
compatible custom extractor. BEARING ships no required cadence and recovery is
never a live PR gate.

## Maintenance model

`subagents/` is the canonical source; the runtime adapters are generated. `bearing render --check` fails CI when a generated adapter drifts from its source, so a hand-edited adapter is caught rather than silently becoming a second source of truth.
