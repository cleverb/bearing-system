---
id: ADR-0008
status: Accepted
eocr_function: Contract
trigger: implementing or invoking decision-recovery extraction
scope: plugin/src/bearing/cli.py
---

# ADR-0008: Recovery is agent-executed until a real extractor exists

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

The recovery spec described `extract.py` / `resolve.py` / `score.py` as pipeline stages. Shipping those files as `NotImplementedError` stubs made agents run them and fail. The CLI already refuses to perform judgment: `bearing onboard` gates; the Skill carries out the steps.

## Decision Drivers

* Judgment belongs to Skills and humans; the CLI is mechanical.
* A stub that looks like a tool is worse than no file.

## Considered Options

1. Implement a model-client EXTRACT pipeline in the plugin (git + LLM API).
2. Delete the stubs. Document agent-executed mining (`references/agent-procedure.md`). CLI validates JSONL (`bearing lint`) and reports cost.

## Decision Outcome

Chosen option: **2**. A model-client extractor is future work, not a file an agent should run. Schema validation of `candidates.jsonl` is the mechanical bit agents cannot be trusted with.

## Consequences

* Weekly recovery is a policy, not a shipped cron.
* Operators must provide git/`gh` access and a reviewing human.

## Deletion test

Bringing back stub `.py` entry points causes agents to invoke them, surface `NotImplementedError`, and conclude recovery is broken rather than agent-executed. Building an extractor before the schemas have survived a real legacy pass would freeze a pipeline that has not been used.
