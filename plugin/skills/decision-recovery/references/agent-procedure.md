# Agent-executed recovery procedure

There is no `extract.py`, `resolve.py`, `score.py`, or `budget-tracker.py`.
Those filenames were a specification of stages, not tools. An agent that
runs them will get `NotImplementedError`. The official path, until a real
extractor exists, is this procedure.

## Mechanical steps the CLI will check

1. Resolve paths: `bearing schema candidate`, `bearing ledger`,
   `bearing eval negative` (and gold/dark/escalation as needed),
   `bearing config decisions.path`.
2. Bound the corpus. Never scan the whole repository on a first pass.
   Honour `scope.include` / `scope.exclude` from config, or the scope
   the operator named.
3. Mine with host tools: `git log`, `git blame`, `gh pr list` / `gh pr view`
   when GitHub is available, and comments on un-anchored symbols.
4. Check `docs/decisions/shadow/rejected.jsonl` before emitting. Suppress
   a candidate whose evidence fingerprint overlaps a prior rejection.
5. Write one JSON object per line to `<decisions.path>/shadow/candidates.jsonl`,
   satisfying the candidate schema. Do not write authored ADRs or `@see`
   annotations.
6. Run `bearing lint`. Fix schema and lifecycle errors before surfacing
   anything to a human.
7. Append a cost row to the ledger path. If `cost.budget_usd_per_run` would
   be exceeded, stop and report partial results.

## What stays judgment

EOCR tagging, conflict handling, confidence axes, and whether a LOW
candidate should surface are Skill instructions, not CLI flags. Do not
invent a decision. Claim only that evidence exists.
