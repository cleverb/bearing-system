---
id: ADR-0003
status: Accepted
eocr_function: Contract
trigger: adding a runtime adapter, renderer, or generated agent/rule file
scope: plugin/src/bearing/render.py, plugin/src/bearing/agentsmd.py, plugin/src/bearing/manifests.py, plugin/src/bearing/artifacts.py, plugin/src/bearing/decisions.py
---

# ADR-0003: Project canonical sources into runtime adapters

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

Cursor, Claude Code, and Codex cannot read one shared subagent or rules format. Forcing a lowest-common-denominator file makes every runtime worse and still leaves generated copies that people edit by hand.

## Decision Drivers

* Standardize organizational meaning; do not require a standardized runtime representation.
* A generated file must never become a second source of truth.
* Projection applies only where a real format gap exists.

## Considered Options

1. One portable file every runtime is asked to read.
2. Canonical sources in the plugin, deterministic adapters per runtime, drift-checked by `bearing render --check`.

## Decision Outcome

Chosen option: **2**. Subagents and rules are projected. SKILL.md is not (ADR-0006). Accepted Contracts compile into the AGENTS.md block and are queryable with `bearing context <path>`; lint and CI consume them via `bearing lint` / `bearing verify` rather than a second generated config.

## Consequences

* Edit the canonical source and re-run `bearing render`. Hand-editing an adapter is drift.
* `projections.lock.json` records both produced artifacts and deliberate skips.

## Deletion test

Without projection, each runtime's agent file becomes an independent constitution. Without the AGENTS.md digest and `bearing context`, a Contract exists only in `docs/decisions/` and is invisible at generation time — the failure this system exists to prevent.
