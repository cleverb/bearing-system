# BEARING

*An EOCR-based decision system for human-agent engineering, packaged as an installable Agent Plugin.*

BEARING makes the decisions governing a codebase discoverable at the moment code is generated, rather than enforceable only after it is written. It does that with four Skills-worth of machinery over one durable idea: **standardize the organizational source, project it into whatever each runtime natively reads.**

- **Read the architecture:** [`BEARING.md`](BEARING.md)
- **Get oriented in 30 minutes:** [`QUICKSTART.md`](QUICKSTART.md)
- **Agent entering this repo:** [`AGENTS.md`](AGENTS.md)

## The mandate

- **ESCALATE** — if intent is missing, stop. Do not guess.
- **ANCHOR** — wire implementation directly to architectural intent.
- **PROJECT** — standardize the organizational source; generate the tool adapters.
- **EVOLVE** — treat the system as a stateful graph, not a static library.

`bearing verify` turns each of those four into a computed pass/fail rather than an aspiration. See [Fit and finish](docs/specs/bearing-distribution-spec.md#6-fit-and-finish-the-conformance-suite).

## What's in this repository

This repository is two things at once, which is worth stating plainly because it explains the layout:

- **`plugin/`** — the BEARING plugin itself. This is what ships and what users install: three Skills, their canonical subagent definitions, the renderers, and the `bearing` CLI. Nothing here is written to at runtime.
- **`.bearing/`, `docs/decisions/`, `AGENTS.md`** — this repository's *own* use of BEARING. BEARING is self-hosted here, so its decision records, config, cost ledger, and evaluation sets sit exactly where they would in any other repo.
- **`docs/specs/`** — the specifications for each Skill and for the distribution layer.

The line between those first two is a hard rule, not a convention: **the plugin tree is read-only after install; all writes go to `.bearing/` (run state) or the configured decisions directory (decision content).** Plugin directories get replaced wholesale on update, so anything BEARING wrote inside itself would be destroyed on every upgrade.

## Install

```bash
# From the BEARING marketplace (Cursor)
cursor-agent plugin marketplace add https://github.com/<org>/bearing-system
# then install `bearing` from /plugin

# From the BEARING marketplace (Claude Code)
/plugin marketplace add <org>/bearing-system
/plugin install bearing@bearing
```

The CLI is bundled in the plugin, and can also be installed on its own:

```bash
pipx install ./plugin        # or: uv tool install ./plugin
bearing --help
```

Requires Python 3.9 or newer and no third-party packages.

## Bootstrap a repository

```bash
cd /path/to/your/repo
bearing init          # detects your decision-record convention, writes .bearing/config.json
bearing doctor        # verifies everything resolves before you rely on it
```

`bearing init` never guesses where your decisions live. If the repo already uses `docs/adr/`, `docs/ADRs/`, or anything else, it detects and asks — see [the legacy convention case](docs/specs/bearing-distribution-spec.md#33-the-legacy-convention-case).

Then run the onboarding pilot, which is the actual 30-minute path in [`QUICKSTART.md`](QUICKSTART.md).

## Developing BEARING itself

BEARING dogfoods its own distribution layer rather than shortcutting it. The Skills live in `plugin/skills/`, which is deliberately *not* a discovery path, so you install the plugin locally rather than letting an in-repo copy shadow it:

```bash
ln -s "$(pwd)/plugin" ~/.cursor/plugins/local/bearing   # Tier 0: fastest iteration
python3 -m unittest discover -s tests -v                 # full suite, zero dependencies
python3 plugin/src/bearing/__main__.py package            # regenerate all manifests
```

The four testing tiers, from a symlink to a published marketplace, are documented in [the distribution spec](docs/specs/bearing-distribution-spec.md#14-local-testing-to-marketplace-promotion).

## License

See [LICENSE](LICENSE).
