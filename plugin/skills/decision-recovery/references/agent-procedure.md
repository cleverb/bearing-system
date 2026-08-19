# Agent-executed recovery procedure

There is no `extract.py`, `resolve.py`, `score.py`, or `budget-tracker.py`.
Those filenames were a specification of stages, not tools. This procedure is
the shipped manual reference path. It does not prevent an operator from using
another scheduler, workflow, or compatible extractor.

## Mechanical steps the CLI will check

1. Resolve paths: `bearing schema candidate`, `bearing ledger`,
   `bearing eval negative` (and gold/dark/escalation as needed),
   `bearing config decisions.path`.
2. Bound the corpus to the request. A small first pass is usually easier to
   review; a broader scope is an operator choice.
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
7. If the operator is measuring recovery, append a cost row to the ledger path
   and honour any configured budget.

## What stays judgment

EOCR tagging and conflict handling remain judgment, not CLI flags. Detailed
confidence axes and surfacing thresholds are useful for repeatable batches but
optional for an opportunistic candidate. Do not invent a decision. Claim only
that evidence exists.
