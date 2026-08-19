---
id: ADR-0009
status: Accepted
eocr_function: Contract
trigger: changing what assessment scores, making it fail a process, or requiring init before it can run
scope: plugin/src/bearing/assessment.py, plugin/src/bearing/cli.py
---

# ADR-0009: Assessment is informational and runs without init

* **Status:** Accepted
* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

A repository's readiness for agents to discover decisions is a useful scorecard *before* anyone runs `bearing init`, and again after. The same number is easy to mistake for a merge gate: "this clone scored unprepared, so block the PR." That would give a descriptive scan the veto ADR-0004 already withholds from recovery inference.

## Decision Drivers

* `doctor` answers whether this BEARING install resolves; it may fail. Assessment answers a different question and must not inherit that exit behaviour.
* An unreadiness finding is a description of the tree, not a structural broken link and not an accepted Contract violation.
* Teams evaluating BEARING need a before/after reading on a clone that has no `.bearing/` yet.

## Considered Options

1. Fold the scorecard into `bearing doctor` and fail when the repo is unprepared.
2. Ship `bearing assessment` as a read-only scorecard: always exit 0, run without init, never write run state, never appear in `enforcement.block_on`.

## Decision Outcome

Chosen option: **2**. `bearing assessment` prints a deterministic scorecard (human or `--json`) and exits 0. It uses `resolve()` without `require_initialized()`. Findings recommend generic next steps; they are not authority.

## Consequences

* CI must not treat a non-zero assessment exit as a merge blocker — there is no such exit.
* Adding assessment to `enforcement.block_on` is forbidden; that key remains `structural` and `known_contract` only.
* Recommendations are a fixed table from finding ids. The command does not invent missing ADRs.

## Deletion test

If assessment may exit non-zero, someone will put it in required CI and an empty eval or a missing `AGENTS.md` will stall every pull request on a description. If it requires init, the before-state the command exists to measure cannot be measured.
