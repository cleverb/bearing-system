---
id: ADR-0002
status: Accepted
eocr_function: Contract
trigger: writing run state, ledgers, transcripts, or skill output
scope: plugin/src/bearing/*.py
---

# ADR-0002: Plugin tree is read-only at runtime

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

Cursor and Claude Code copy an installed plugin into a versioned cache and replace that copy wholesale on update. Anything BEARING wrote inside `plugin/` would be deleted on the next upgrade, including cost history and interview transcripts.

## Decision Drivers

* Runtime data must outlive plugin updates.
* Agent Plugins v1.0.0 §4.1.3 rejects package paths that escape the plugin root.

## Considered Options

1. Store ledgers and eval sets beside the Skills that produce them.
2. Write run state to `.bearing/` and decision content to the configured decisions directory; treat `plugin/` as read-only after install.

## Decision Outcome

Chosen option: **2**. Maintainer commands such as `bearing package` may write generated manifests into `plugin/`; runtime commands must not.

## Consequences

* Skills cannot keep a per-repo ledger in `references/`.
* Cross-skill schema access goes through `bearing schema`, not `../`.

## Deletion test

If this constraint is removed, the next plugin update silently destroys the repository's cost ledger, eval sets, and any transcript written inside the install. The kill switch resets. Provenance for promoted Contracts becomes unrecoverable.
