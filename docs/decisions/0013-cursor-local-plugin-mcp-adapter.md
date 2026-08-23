---
id: ADR-0013
status: Proposed
eocr_function: Contract
trigger: changing how the BEARING plugin is launched in Cursor local mode versus marketplace install
scope: plugin/src/bearing/manifests.py, plugin/src/bearing/cli.py, plugin/mcp.json, plugin/mcp.local.json
---

# ADR-0013: Cursor local plugin MCP launch is a distinct projected adapter

* **Date:** 2026-08-23
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

Cursor marketplace installs copy `plugin/` into a versioned cache and expand
`${PLUGIN_ROOT}` in `plugin/mcp.json`. That launch config is correct for
marketplace distribution.

Cursor **local** plugins load from `~/.cursor/plugins/local/bearing-plugin`
without expanding `${PLUGIN_ROOT}`. A relative `hooks/run_mcp.py` with
`cwd: ${PLUGIN_ROOT}` never resolves, so MCP does not start. The working local
launch uses `sh -c` with an absolute path under `$HOME`.

A symlink from `plugin/` into the local plugins directory cannot carry two
`mcp.json` files. Contributors need a copy-sync that projects the canonical
`plugin/` tree into the local install location with the local launch adapter
written to dest `mcp.json`.

## Decision Drivers

* One canonical `plugin/` tree; marketplace and local are load-path adapters, not separate codebases (ADR-0003).
* The plugin tree stays read-only at runtime; maintainer projection may write generated manifests into `plugin/` (ADR-0002).
* Operator facts belong in `~/.bearing`, not repo config — but the local plugin path is a documented product location, like `~/.bearing/bin` in ADR-0012.
* Cursor local install directories are copy targets, not git checkouts.

## Considered Options

1. Symlink `plugin/` to `~/.cursor/plugins/local/bearing` and document that local MCP is broken or requires hand-editing `mcp.json`.
2. Ship only marketplace `mcp.json` and require contributors to hand-edit the local install after every change.
3. Generate `plugin/mcp.local.json` from `manifests.py` and add `bearing package --local` to copy `plugin/` → `~/.cursor/plugins/local/bearing-plugin`, overlay dest `mcp.json` from the local adapter, and delete any dest `.git`.

## Decision Outcome

Chosen option: **3**.

* `plugin/mcp.json` — marketplace adapter (`${PLUGIN_ROOT}`, `python3 hooks/run_mcp.py`).
* `plugin/mcp.local.json` — local adapter (`sh -c`, `$HOME/.cursor/plugins/local/bearing-plugin/hooks/run_mcp.py`). Cursor does not read this file in the repo; `bearing package --local` writes it to dest `mcp.json`.
* `.cursor-plugin/plugin.json` continues to set `mcpServers` to `./mcp.json` in both marketplace and copied local trees.
* `bearing package --local` is a maintainer command; it does not write into `plugin/` at runtime.

## Consequences

* Tier 0 contributor iteration is `bearing package --local`, then reload the Local plugin in Cursor.
* `~/.cursor/plugins/local/bearing-plugin` is solely a copy target — no `.git`, not a second checkout.
* Marketplace zips may include `mcp.local.json` as reference; marketplace installs must not use it as the active launch config.

## Deletion test

Without this adapter, every Cursor local plugin install either fails to launch MCP
or requires hand-maintained `mcp.json` drift beside the canonical tree —
reintroducing the two-codebase failure mode this distribution layer exists to
prevent.
