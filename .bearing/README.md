# .bearing/ — run state

Everything BEARING writes about *runs* lives here. Everything BEARING writes about *this repository's decisions* lives in the configured decisions directory instead. That line is the whole organizing principle of this folder, and it is worth stating because the two are easy to conflate.

This directory exists at the workspace root rather than inside `docs/decisions/` for a bootstrapping reason, not an aesthetic one: `config.json` is what declares where decisions live, so it cannot itself be stored at a location that requires reading it first.

## Contents

- **`config.json`** — committed. Repo facts only: where decisions live, the recovery scope, what may block a merge, projection targets, verification thresholds. Operator facts are deliberately excluded so one developer's model preference never becomes a repository default.
- **`config.local.json`** — gitignored. Personal overrides for this repository. Setting a repo fact here works but is reported by `bearing doctor`, because it makes one machine behave differently from every other clone.
- **`pricing.json`** — committed. The price book, merged over packaged defaults. Every entry carries `as_of` and a source, and every cost figure BEARING reports names the price-book version it used.
- **`projections.lock.json`** — committed. Every generated adapter, its canonical source, its hash, and every target deliberately skipped. This is what lets `bearing render --check` distinguish "not generated because it was turned off" from "not generated because something broke."
- **`ledger/cost.jsonl`** — committed, append-only. Run history feeding acceptance rate, cost per promoted candidate, and the kill switch. Committed because the trend matters across contributors and CI, not just on one laptop.
- **`ledger/pass-fail-criteria.md`** — committed. The pilot bar, written before any pilot ticket runs. `bearing report --pilot` fails if this file was modified after the first pilot run, which is the only real defense against a threshold that gets adjusted to fit the results.
- **`eval/{gold,dark,negative}/`** — committed. Evaluation content specific to this repository.
- **`runs/`** — gitignored. Per-run logs and partial results. Decision Recovery writes `runs/recovery/<run-id>/status.json` (snapshot) and `events.jsonl` (append-only activity). The Recovery MCP App projects this state; it is not a second source of decision authority.
- **`cache/`** — gitignored. Corpus fingerprints and idempotency keys. Rebuildable; deleting it costs a re-scan, not correctness.

## What is deliberately *not* here

The shadow graph stays at `<decisions.path>/shadow/`, with the decision corpus. Moving candidates here would reclassify evidence as machine state, which makes it natural to gitignore — and a rejection ledger that is not in version control cannot stop a candidate from being re-litigated by the next contributor's run.
