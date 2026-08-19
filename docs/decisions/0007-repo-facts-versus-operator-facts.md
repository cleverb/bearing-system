---
id: ADR-0007
status: Accepted
eocr_function: Contract
trigger: adding a config key or changing which layer wins for an existing key
scope: plugin/src/bearing/config.py
---

# ADR-0007: Repo facts versus operator facts

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

Nearest-file-wins config lets one clone rewrite `decisions.path` and lets a repository pin a model someone else pays for. Both failures showed up as soon as more than one person used the tool.

## Decision Drivers

* A repository owns where its decisions live and what may block a merge.
* An operator owns model choice, hourly rate, and whether adapters land in the clone or the home directory.

## Considered Options

1. Single precedence chain (nearest wins).
2. Classify every leaf key as repo or operator; different layer orders for each class. Unclassified keys are a hard error.

## Decision Outcome

Chosen option: **2**. `bearing init` writes only repo facts (unless an operator key is passed explicitly). A repo-fact override in `.bearing/config.local.json` is reported every time.

Default `projections.subagents.scope` is `repo` so a fresh init commits adapters with the clone; operators who want home-directory adapters set `user`.

## Consequences

* Adding a config key requires a classification, not just a schema entry.
* User config still wins over a repository suggestion for operator facts.

## Deletion test

If classification is dropped, one developer's `~/.bearing/config.json` can move another clone's decision records, or a committed model id can spend money on machines the repository does not pay for.
