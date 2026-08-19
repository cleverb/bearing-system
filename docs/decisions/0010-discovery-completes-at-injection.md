---
id: ADR-0010
status: Accepted
eocr_function: Contract
trigger: resolving authoritative decisions for a task, file, or runtime action
scope: plugin/src/bearing/workspace.py, plugin/src/bearing/decisions.py, plugin/src/bearing/lint.py, plugin/src/bearing/verify.py, plugin/hooks/**
---

# ADR-0010: Discovery completes at injection

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

An index can make a decision cheap to find without putting it into the actor's
context before the action it governs. That leaves the flagship promise one rung
below its intended maturity: resolved knowledge remains advisory until it reaches
the actor at the relevant generation or mutation boundary.

## Decision Drivers

* Canonical organizational meaning must remain independent of client lifecycle APIs.
* Every consumer must resolve scope against one definition of the workspace.
* Runtime limitations must be reported honestly rather than hidden behind a generic support claim.

## Considered Options

1. Treat a current index and an instruction to consult it as complete discovery.
2. Define discovery as Index → Resolve → Inject, using the strongest lifecycle mechanism each runtime actually provides.

## Decision Outcome

Chosen option: **2**. Discovery completes only when the relevant Accepted
Contracts reach the actor before the generation or mutation they govern, where
the runtime provides such a boundary. A weaker runtime is reported as advisory;
it does not change the canonical decision model.

An **effective workspace file** is a currently existing, workspace-contained
path returned by Git's tracked-plus-untracked, non-ignored file set (or the
documented non-Git fallback), filtered by BEARING include/exclude rules and
normalized to a workspace-relative POSIX path. One implementation owns this
definition for lint, context, assessment, and verification.

A scan-recognized `@see ADR-*` annotation is a governing Anchor. Informational
references use ordinary prose or links rather than Anchor syntax.

## Consequences

* Runtime adapters may differ in enforcement strength without moving vendor vocabulary into this record.
* Discover integrity is a verification category, not a replacement for the Decision System behavior sequence.
* A stale scope or an Anchor outside an Accepted Contract's scope is a broken discovery edge.

## Deletion test

Without this Contract, the right decision may exist, index correctly, and still
arrive only after the governed code has already been generated.
