# Contributing

This repository is both the BEARING plugin and a repository using BEARING. Decision records in `docs/decisions/` are binding, subject to their `Status`. Load `docs/decisions/index.json` (or run `bearing context <path>`) before changing code they govern.

Machine setup for a local checkout — including running proposed CLI and plugin changes — is in [`SETUP.md`](SETUP.md) (the Contributor section). This file is the definition of done once that environment runs.

## Definition of done

A change is ready for review when:

1. It does not conflict with an accepted Contract.
2. New or changed code that depends on a decision carries `@see ADR-000N`.
3. Generated adapters were not hand-edited — change the canonical source and run `bearing render`.
4. The checks below pass.

## Before you open a pull request

```bash
python3 -m unittest discover -s tests
PYTHONPATH=plugin/src python3 -m bearing doctor
PYTHONPATH=plugin/src python3 -m bearing render --check
PYTHONPATH=plugin/src python3 -m bearing package --check
PYTHONPATH=plugin/src python3 -m bearing index
PYTHONPATH=plugin/src python3 -m bearing lint
PYTHONPATH=plugin/src python3 -m bearing verify
```

Nothing in CI may gate a merge on a recovery signal. See ADR-0004.

## Decision integrity

If you encounter a `@deprecated` marker with no `@see` link, do not refactor it — open a clarification request. Promotion out of `docs/decisions/shadow/` is a human judgment, not a confirmation that a summary read correctly.
