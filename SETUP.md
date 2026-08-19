# SETUP.md — First-run setup

Install the machinery, then bootstrap a repository. This file is the first-run
path. [`QUICKSTART.md`](QUICKSTART.md) is what to do after `bearing` runs.
[`CONTRIBUTING.md`](CONTRIBUTING.md) is the definition of done for a change.

Two audiences:

- **User** — adopt BEARING on a repository you work in.
- **Contributor** — run *this* checkout, including proposed changes, locally.

They share prerequisites. They do not share how the plugin is discovered.

## What you are installing

**One marketplace plugin install is enough.** The plugin ships Skills, hooks,
MCP, and the `bearing` CLI (`plugin/src/bearing`). Opening a workspace (or
starting MCP) writes operator-scope launchers under `~/.bearing/bin` that point
at the plugin copy the runtime actually loaded — no separate `pipx` / `uv tool`
step required.

| Layer | What it delivers | Who needs it |
| --- | --- | --- |
| **Plugin** | Skills, projected agents, hooks, MCP, and the CLI module | Everyone using BEARING |
| **PATH shim** (derived) | `bearing` and `bearing-mcp` in `~/.bearing/bin` | Anyone running terminal commands |

`plugin/skills/` in this repository is **not** a discovery path. Opening
`bearing-system` in Cursor does not install the plugin. Skills are consumed from
an installed or vendored copy.

The Python distribution name is `bearing-system`. The import package and command
remain `bearing`. Python 3.9 or newer, standard library only. Optional:
`pipx install ./plugin` or `uv tool install ./plugin` for CI and contributors.

## Prerequisites

- Git.
- Python 3.9+. `python3 --version` must succeed.
- An agent runtime you actually use: Cursor, Claude Code, or Codex.

---

## User: adopt BEARING on a repository

### 1. Get the marketplace source (for local install only)

Published marketplace users can skip cloning. For a local marketplace from this
checkout:

```bash
git clone https://github.com/cleverb/bearing-system.git
cd bearing-system
```

Use a release tag when you are evaluating a specific version.

### 2. Install the plugin into your runtime

**Cursor (published marketplace):**

```bash
cursor-agent plugin marketplace add https://github.com/cleverb/bearing-system
```

Then install `bearing` from `/plugin` in the Cursor plugin UI. Cursor's agent
CLI does not currently perform the install step; the GUI marketplace flow does.

**Cursor (this checkout, no publish):** this repository root *is* the marketplace
(`.cursor-plugin/marketplace.json`). Add it as a local marketplace in the Cursor
UI and install **BEARING** (install id `bearing`). Prefer **Add for Myself**
(User scope). **Add to Project** currently fails in Cursor with
`Workspace collection is not available` — that is a Cursor bug, not a BEARING
config error. Reload the window after install.

**Claude Code:**

```bash
claude plugin marketplace add https://github.com/cleverb/bearing-system
claude plugin install bearing@bearing
```

From a clone, `claude plugin marketplace add . --scope local` then install
`bearing@bearing`.

**Codex:** add this checkout as a local marketplace and install the plugin, then
confirm with `codex plugin list --json`.

After install you should see the three Skills. Cursor and Claude Code *copy* the
plugin into a versioned cache; that copy is what the runtime reads.

### 3. Enable the CLI

After installing the plugin, enable the terminal CLI once. You do **not** need
a separate `pipx` install.

**Recommended (from a bearing-system clone):** point the shim at this checkout's
`plugin/` tree — it always includes `bin/bearing`:

```bash
cd /path/to/bearing-system
python3 plugin/enable.py
export PATH="$HOME/.bearing/bin:$PATH"
bearing --help
```

Do **not** invent paths like `~/plugin/enable.py` unless that directory is a
real BEARING plugin tree.

**After a marketplace GUI install** that copied a complete plugin (including
`bin/`), you can discover the cache copy instead:

```bash
cd /path/to/bearing-system
python3 plugin/enable.py --discover
```

`--discover` skips incomplete/orphaned caches (no `bin/bearing`, or marked
`.orphaned_at`). If discovery finds nothing usable, fall back to the clone
command above.

Opening a workspace also enables the CLI automatically (`workspaceOpen` and MCP
start write the same `~/.bearing/` files). Use the explicit command when you
have not opened a workspace yet.

If `bearing` is already on PATH and working: `bearing enable` retargets the
shims. Prefer `python3 plugin/enable.py` when `bearing` itself is broken.

`pipx install ./plugin` / `uv tool install ./plugin` remain optional for CI and
contributors; they are not required for the user path.

### 4. Bootstrap the target repository

In the **repository you want BEARING to govern**, not necessarily this one:

```bash
cd /path/to/your/repo
bearing assessment    # optional scorecard; works before init; always exits 0
bearing init          # detect decision-record convention; write .bearing/config.json
bearing doctor        # confirm paths, plugin discovery, and configuration
bearing health        # aggregate checks and counts; always exits 0
```

`bearing init` never guesses a decisions directory. If the repo already uses
`docs/adr/`, `docs/ADRs/`, or another known convention, it detects and asks.
With `--yes` it adopts the detected directory.

This `bearing-system` repository is already initialized. Skip `init` here; run
`doctor`.

Writes go to `.bearing/` (run state) and the configured decisions directory
(decision content). Nothing is written under `plugin/`.

### 5. Confirm the runtime session

Open the **target** repository in Cursor (or Claude Code / Codex).

- The three Skills are available.
- After `init` / `render`, Cursor has `.cursor/rules/` and `.cursor/agents/` when
  those projection targets are enabled (they are, by default, at `scope: repo`).
- `bearing context <path>` prints index entries whose scope matches that file.
- Asking the agent to load `docs/decisions/index.json` (or your configured index)
  should surface Accepted Contracts for governed files.
- To clear the shadow review queue in Cursor, use the **BEARING** MCP tools
  (`list_reviewable`, `review_candidate`) or run `bearing review` /
  `bearing dispose`. Promote requires human judgment fields (scope, present
  validity, lifecycle, EOCR); confidence alone never promotes.

### Cursor MCP

Marketplace / local-plugin install ships `plugin/mcp.json`. After install, Cursor
should list an MCP server named **BEARING** under Tools / MCP. It launches via
`${PLUGIN_ROOT}` — not `${workspaceFolder}`.

`review_candidate` does **not** block on a form by default (mid-tool elicitation
hung some Cursor builds and made the agent feel stuck, including Skills
autocomplete). Pass a `disposition` object on the tool call, or use
`bearing dispose` / `bearing review`. Set `elicit: true` only on hosts that
reliably complete MCP forms.

If Cursor still feels slow: disable **BEARING** under Tools → MCP, reload, and
confirm Skills recover — then re-enable when you need disposition tools.

If you prefer a project-local MCP override that calls `bearing-mcp` on PATH,
copy the template after the shim exists:

```bash
cp plugin/src/bearing/data/templates/mcp.json.example /path/to/repo/.cursor/mcp.json
```

`${workspaceFolder}` is only for that **project** `.cursor/mcp.json` path. Do <!-- bearing:ignore-paths: optional project MCP override, not this checkout -->
not expect it inside the plugin-bundled MCP config.

Tools: `list_reviewable`, `review_candidate`.

Cursor is **session-advisory**: the workspace-open hook injects context when the
workspace opens. Do not treat that as proof the agent knew a file path *before*
a mutation.

### 6. Optional evaluation

```bash
bearing onboard
```

That is a readiness check and a menu, not a ceremony. You can stop after
`doctor` and use BEARING as decisions arise. There is no requirement to recover
history first. Paths after setup are in [`QUICKSTART.md`](QUICKSTART.md).

---

## Contributor: run proposed changes locally

This repository is both the plugin and a repository *using* the plugin. You
install the local plugin the same way a user does — you do not let
`plugin/skills/` shadow an install.

### 1. Clone and confirm Python

```bash
git clone https://github.com/cleverb/bearing-system.git
cd bearing-system
python3 --version   # 3.9 or newer
```

### 2. Point the runtime at this working tree (Tier 0)

```bash
mkdir -p ~/.cursor/plugins/local
ln -s "$(pwd)/plugin" ~/.cursor/plugins/local/bearing
```

Reload Cursor. Edits under `plugin/skills/` and `plugin/hooks/` are what the
client loads. This is the fastest iteration loop. It is not a marketplace
install: Cursor is reading the checkout, not a copied cache.

For Claude Code, add this clone as a local marketplace (`claude plugin
marketplace add . --scope local`) and install `bearing@bearing`. That *does*
copy the tree; reinstall after Skill or hook changes.

### 3. Run the CLI from the working tree

Do **not** rely on a one-time `uv tool install ./plugin` while you are changing
CLI code. That command snapshots `plugin/` and will serve stale bytecode until
you reinstall.

From this repository root, CONTRIBUTING and CI use:

```bash
PYTHONPATH=plugin/src python3 -m bearing --help
PYTHONPATH=plugin/src python3 -m bearing doctor
```

`python3 plugin/src/bearing/__main__.py` is the same entry point.

A `bearing` on `PATH` from an earlier `uv tool install` / `pipx install` will
shadow this. Prefer the `PYTHONPATH` form for proposed changes, or reinstall
after each CLI edit:

```bash
uv tool install --force ./plugin
```

### 4. Sanity-check the checkout

```bash
python3 -m unittest discover -s tests
PYTHONPATH=plugin/src python3 -m bearing doctor
PYTHONPATH=plugin/src python3 -m bearing render --check
PYTHONPATH=plugin/src python3 -m bearing package --check
```

Generated adapters (`.cursor/`, `.claude/`, `.codex/`, per-client manifests, the
BEARING block in `AGENTS.md`) are regenerated, never hand-edited. Change the
canonical source and run `bearing render` / `bearing package`.

### 5. Before a pull request

The full list is in [`CONTRIBUTING.md`](CONTRIBUTING.md):

```bash
python3 -m unittest discover -s tests
PYTHONPATH=plugin/src python3 -m bearing doctor
PYTHONPATH=plugin/src python3 -m bearing render --check
PYTHONPATH=plugin/src python3 -m bearing package --check
PYTHONPATH=plugin/src python3 -m bearing index
PYTHONPATH=plugin/src python3 -m bearing lint
PYTHONPATH=plugin/src python3 -m bearing verify
```

Load `docs/decisions/index.json` (or `bearing context <path>`) before changing
code those records govern. Do not write to `docs/decisions/` on the basis of
inference. Do not hand-edit a file with a `DO NOT EDIT` header.

The testing tiers from this symlink up to a published marketplace are in the
[distribution spec](docs/specs/bearing-distribution-spec.md#14-local-testing-to-marketplace-promotion).

---

## When setup has worked

- `bearing --help` (or `PYTHONPATH=plugin/src python3 -m bearing --help`) prints
  subcommands.
- `bearing doctor` in the target repo reports paths that resolve.
- The runtime lists the three Skills.
- `bearing context` on a governed file returns matching index entries, once
  decisions exist.

## When it has not

- **`bearing: missing plugin launcher at …/bin/bearing`.** Your
  `~/.bearing/install.json` points at an incomplete or orphaned plugin cache
  (common with an old Claude copy). From the bearing-system clone run
  `python3 plugin/enable.py` (not `--discover`, and not `~/plugin/enable.py`),
  then `export PATH="$HOME/.bearing/bin:$PATH"`.
- **`bearing: command not found`.** Run `python3 plugin/enable.py` from a
  bearing-system clone, then `export PATH="$HOME/.bearing/bin:$PATH"`.
- **Doctor warns `bearing on PATH: not found`.** Same remedy; the warning is
  advisory and does not block merges.
- **Doctor warns PATH skew (pipx vs shim).** Both work; re-run
  `python3 plugin/enable.py` from the clone to retarget the operator shim.
- **`Failed to install bearing` / `Workspace collection is not available`.**
  Cursor's **Add to Project** path is broken in current builds. Install with
  **Add for Myself** (User scope), or add the plugin manually under
  `.cursor/settings.json` and reload. Unrelated to `${workspaceFolder}`. <!-- bearing:ignore-paths: Cursor settings, not a file this repo ships -->
- **No BEARING MCP after plugin install.** Confirm the install succeeded (User
  scope) and that `plugin/mcp.json` is present in the installed plugin copy.
  Reinstall the marketplace plugin after pulling this change. Project-local
  MCP is optional (`mcp.json.example`); plugin MCP uses `${PLUGIN_ROOT}`.
- **Cursor feels hung / Skills autocomplete dead.** Often a stuck MCP tool
  call. Disable **BEARING** under Tools → MCP, reload, then update to a build
  where `review_candidate` does not elicit by default. Prefer
  `disposition={...}` args or `bearing dispose`.
- **Doctor fails with `no plugin.json found`.** Run
  `python3 plugin/enable.py --discover`, then add `~/.bearing/bin` to PATH.
  Optional: `pipx install --force ./plugin` for a wheel-only layout.
- **`bearing` runs but looks like an old build.** A `pipx` / `uv tool` install
  snapshots the tree. Reinstall, or run via `PYTHONPATH=plugin/src`.
- **Doctor fails before init.** `assessment` is allowed before init; most other
  commands are not. Run `bearing init` in the target repository.
- **Hook ran, agent still guessed.** Cursor is session-advisory. Check the index
  and `bearing context <path>` rather than inferring pre-mutation injection.

## Tear down

**Repository:** `bearing uninstall` removes generated adapters and run state from
the repo; decision content stays. See `bearing uninstall --dry-run` first.

**Operator CLI shims** (`~/.bearing/bin`) are separate. `bearing uninstall` does
not remove them, and disabling the plugin in Cursor/Claude does not either.
To drop the PATH launchers manually:

```bash
rm -f ~/.bearing/install.json ~/.bearing/bin/bearing ~/.bearing/bin/bearing-mcp
# optional if enable mirrored there:
rm -f ~/.local/bin/bearing ~/.local/bin/bearing-mcp
```

## Next

- Orientation and optional trial paths: [`QUICKSTART.md`](QUICKSTART.md)
- Architecture: [`BEARING.md`](BEARING.md)
- Definition of done: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Distribution layers and projection: [`docs/specs/bearing-distribution-spec.md`](docs/specs/bearing-distribution-spec.md)
