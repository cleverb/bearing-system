# ADR-0001: Record Architecture Decisions

* **Status:** Accepted
* **Date:** <!-- fill in on adoption -->
* **Deciders:** <!-- fill in -->
* **Tickets:** <!-- fill in -->

## Context and Problem Statement

Decisions behind this codebase were previously undocumented, or scattered across chat, tickets, and tribal memory. Agents and new engineers alike had no reliable way to discover why the system is shaped the way it is before making a change.

## Decision Drivers

* Agents now regularly generate code in this repository and need discoverable, authoritative context before doing so — not just after, in review.
* Institutional memory should not depend on any one person staying at the company.
* Documentation that isn't connected to the code it governs is documentation nobody reads.

## Considered Options

1. Continue relying on tribal knowledge and ad hoc documentation.
2. Adopt lightweight, numbered Architecture Decision Records under `docs/decisions/`, connected to implementation via annotations, per the BEARING decision system (see `/BEARING.md`).

## Decision Outcome

Chosen option: **2**. This repository adopts numbered ADRs under `docs/decisions/`, following the EOCR knowledge grammar (Entry, Operations, Contracts, Rationale) and the Decision Graph mechanics described in `/BEARING.md`.

## Consequences

* New decisions with real normative weight are recorded here, not just in PR descriptions.
* Code depending on a decision carries a `@see ADR-000N` annotation.
* Legacy decisions may be recovered retrospectively via the `decision-recovery` and `decision-interview` Skills — see `.agents/skills/`.

## Validation

* [ ] `docs/decisions/index.json` reflects this ADR.
* [ ] `AGENTS.md` points agents to this directory as the authoritative decision source.
