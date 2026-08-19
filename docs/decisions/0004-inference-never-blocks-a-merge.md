---
id: ADR-0004
status: Accepted
eocr_function: Contract
trigger: adding a CI job, linter, or config key that could block a merge
scope: plugin/src/bearing/config.py, plugin/src/bearing/verify.py, plugin/src/bearing/lint.py
---

# ADR-0004: Inference never blocks a merge

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

A recovery confidence score is easy to mistake for organizational authority. If a pipeline treats "we found evidence of a decision" as "this PR must not merge," inference acquires veto power nobody granted it.

## Decision Drivers

* Structural facts (broken `@see`, missing successor) are verifiable.
* Evidence scores are opinions about the historical record.

## Considered Options

1. Allow `enforcement.block_on` to include `recovery_signal`.
2. Ban `recovery_signal` from `block_on`; inspect CI workflows for recovery commands that gate the job.

## Decision Outcome

Chosen option: **2**. Only `structural` and `known_contract` may block. A recovery signal may flag and route to review at any confidence.

## Consequences

* `bearing lint` errors are merge-blocking; candidate confidence is not.
* Adding a CI job that runs `bearing recover|extract|score|resolve` without `continue-on-error` fails the ESCALATE pillar.

## Deletion test

If this constraint is removed, a noisy recovery pass can stall every pull request on evidence that has not crossed the human authority boundary. The shadow graph becomes a shadow government.
