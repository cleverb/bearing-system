---
id: ADR-0008
status: Accepted
eocr_function: Contract
trigger: implementing or invoking decision-recovery extraction
scope: plugin/src/bearing/cli.py, plugin/src/bearing/profiles.py
---

# ADR-0008: Recovery execution is operator-selected

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

The recovery spec described `extract.py` / `resolve.py` / `score.py` as pipeline stages. Shipping those files as `NotImplementedError` stubs made agents run them and fail. BEARING needs a usable reference workflow without owning the operator's scheduler, automation platform, or recovery cadence.

## Decision Drivers

* Judgment belongs to Skills and humans; the CLI is mechanical.
* A stub that looks like a tool is worse than no file.

## Considered Options

1. Implement a model-client EXTRACT pipeline in the plugin (git + LLM API).
2. Delete the stubs. Document agent-executed mining (`references/agent-procedure.md`) as one available workflow. CLI validates JSONL (`bearing lint`) and can report cost.

## Decision Outcome

Chosen option: **2**. The shipped Skill provides a manual, agent-executed reference workflow. Operators may invoke it opportunistically, run bounded passes manually, schedule it with their own automation, or replace it with a compatible extractor. BEARING owns the candidate format and authority boundary, not the execution mechanism.

## Consequences

* BEARING ships no required cadence, cron job, or CI workflow.
* GitHub access is optional; recovery can use whatever evidence is locally available.
* Promotion still requires human review, but generating and committing a shadow candidate does not imply promotion.

## Deletion test

Bringing back stub `.py` entry points causes agents to invoke them, surface `NotImplementedError`, and conclude recovery is broken. Mandating a particular scheduler or extractor before operational feedback would freeze an execution model that BEARING does not need to own.

## Implementation History

* **2026-08-18:** Clarified the original agent-executed default after maintainer review. The reference Skill remains usable, but execution mode, cadence, automation, and commit grouping are operator choices.
