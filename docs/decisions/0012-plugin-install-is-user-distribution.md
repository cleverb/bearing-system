---
id: ADR-0012
status: Proposed
eocr_function: Contract
trigger: changing how the CLI is distributed or discovered after a marketplace plugin install
scope: plugin/bin/**, plugin/hooks/**, plugin/src/bearing/enable.py, plugin/src/bearing/paths.py, plugin/src/bearing/doctor.py, plugin/src/bearing/cli.py
---

# ADR-0012: Plugin install is user distribution; PATH CLI is derived

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

v0.2 required two installs: a marketplace plugin (Skills, hooks, MCP) and a
separate `pipx` / `uv tool` install for the `bearing` CLI. The CLI already
lives inside the plugin tree; hooks already invoke it with `python3` and
`PYTHONPATH`. The second install duplicated the same code in a different tree,
confused `bearing doctor`, and blocked enterprise adoption where a second
package manager step is unacceptable.

## Decision Drivers

* One marketplace install should be enough for interactive BEARING use.
* The plugin tree stays read-only at runtime (ADR-0002).
* Operator facts (where the CLI launcher points) belong in `~/.bearing`, not in
  repository config (ADR-0007).
* pipx/uv remain valid for CI and contributors who never open a client.

## Considered Options

1. Require pipx/uv forever; document the two-install model.
2. Ship only `plugin/bin/bearing`; users add `${PLUGIN_ROOT}/bin` themselves.
3. On workspaceOpen / MCP start, write an operator-scope PATH shim under
   `~/.bearing/bin` that delegates to the installed plugin cache via
   `~/.bearing/install.json`.

## Decision Outcome

Chosen option: **3**. User distribution is the marketplace plugin. The PATH
CLI is derived: `install.json` records the live plugin root and interpreter;
`~/.bearing/bin/bearing` and `bearing-mcp` delegate to `plugin/bin/*` inside
that tree. Never write inside the plugin directory. Do not edit shell rc files;
report a one-line `PATH` export when the shim is not visible.

`pipx install ./plugin` and `uv tool install ./plugin` remain optional.

## Consequences

* Opening a workspace (or running `bearing enable`) retargets the shim when the
  plugin updates.
* `plugin_root()` consults `install.json` when walk-up from the import package
  does not find a full plugin tree.
* Doctor distinguishes missing shim, missing PATH, and pipx skew (advisory).

## Deletion test

If this constraint is removed, every enterprise rollout reintroduces a second
installer, `bearing doctor` again fails for plugin-only users, and the
distribution story contradicts the product layout (CLI inside `plugin/src`).
