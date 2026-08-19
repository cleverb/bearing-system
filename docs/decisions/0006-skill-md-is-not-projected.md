---
id: ADR-0006
status: Accepted
eocr_function: Contract
trigger: adding a SKILL.md renderer or a projection whose targets all share one format
scope: plugin/src/bearing/render.py
---

# ADR-0006: SKILL.md is not projected

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

Surrounded by subagent renderers, a SKILL.md renderer looks like consistency. Agent Skills is already an open standard that Cursor, Claude Code, and Codex read natively from `.agents/skills/` or an installed plugin.

## Decision Drivers

* Projection is justified only by a real format gap.
* A pile of unnecessary renderers is how a clean principle becomes machinery nobody can justify.

## Considered Options

1. Render SKILL.md into each runtime's preferred layout.
2. Leave SKILL.md as the canonical consumable artifact; fail `bearing verify` if a Skill grows a SKILL.md renderer.

## Decision Outcome

Chosen option: **2**. `skill_projection_errors()` and `projection_necessity_errors()` enforce this.

## Consequences

* Subagents still need projection (incompatible native formats). Skills do not.
* Vendoring copies SKILL.md as-is via `bearing vendor`.

## Deletion test

A SKILL.md renderer would duplicate instructions that already load, drift independently, and teach the next contributor that every artifact needs an adapter whether a format gap exists or not.
