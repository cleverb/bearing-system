---
id: ADR-{{number}}
status: Accepted
eocr_function: Contract
trigger: adding decision records, or tooling that needs to locate them
scope: {{decisions_path}}/**
---

# ADR-{{number}}: Decision records live in `{{decisions_path}}/`

* **Date:** {{date}}
* **Deciders:** <fill in>

## Context and Problem Statement

BEARING's documented default location for decision records is `docs/decisions/`. This repository keeps them in `{{decisions_path}}/` instead.

That difference needs to be written down somewhere discoverable. Left only in a config value, it becomes a fact that tooling knows and people do not — and the next person to look for the decision records looks in the documented default, finds nothing, and concludes there are none.

## Decision Drivers

* The existing location predates BEARING and is referenced from <fill in: links, bookmarks, other repos, CI config>.
* Renaming a directory with history rewrites paths in every existing reference and in the blame of every record.
* The cost of the rename is real and immediate; the benefit of matching a default is cosmetic.

## Considered Options

1. Rename `{{decisions_path}}/` to `docs/decisions/` to match the BEARING default.
2. Keep `{{decisions_path}}/` and record the deviation here, configuring `decisions.path` to match.

## Decision Outcome

Chosen option: **2**. `decisions.path` in `.bearing/config.json` points at `{{decisions_path}}/`, and every BEARING command derives its paths from that one key.

## Consequences

* Anyone — human or agent — who goes looking for the default location finds this record explaining where the records actually are.
* The deviation is discoverable rather than buried in a config file.
* This is the framework using itself: a deviation from a documented default is exactly the kind of decision that has real consequences and no obvious home, which is what a decision record is for.
