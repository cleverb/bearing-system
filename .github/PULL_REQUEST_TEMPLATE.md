## Summary

<!-- What changed, and why. Link the ADR if this implements or amends a decision. -->

## Decision integrity

- [ ] `docs/decisions/index.json` was loaded (or `bearing context <path>` run) for the files this PR touches
- [ ] New or changed code that depends on a decision carries `@see ADR-000N`
- [ ] This change does not conflict with an accepted Contract
- [ ] Generated files (adapters, manifests, the AGENTS.md block) were regenerated, not hand-edited
- [ ] If a new decision was required, it is an authored record — not a shadow candidate treated as authority

## Test plan

- [ ] `python3 -m unittest discover -s tests`
- [ ] `PYTHONPATH=plugin/src python3 -m bearing lint`
- [ ] `PYTHONPATH=plugin/src python3 -m bearing verify`
