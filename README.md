# BEARING

*An EOCR-based decision system for human-agent engineering, packaged as an installable Agent Plugin.*

BEARING makes the decisions governing a codebase discoverable at the moment code is generated, rather than enforceable only after it is written. It does that with three Skills and a governance CLI over one durable idea: **standardize the organizational source, project it into whatever each runtime natively reads.**

- **First-run setup:** [`SETUP.md`](SETUP.md)
- **Read the architecture:** [`BEARING.md`](BEARING.md)
- **Get oriented:** [`QUICKSTART.md`](QUICKSTART.md)
- **Agent entering this repo:** [`AGENTS.md`](AGENTS.md)

## The mandate

- **ESCALATE** — if intent is missing, stop. Do not guess.
- **ANCHOR** — wire implementation directly to architectural intent.
- **PROJECT** — standardize the organizational source; generate the tool adapters.
- **EVOLVE** — treat the system as a stateful graph, not a static library.

`bearing verify` checks the structural parts of those mandates that the repository can establish mechanically. It does not score inferred intent or certify that a team's decision practice is effective. See [Fit and finish](docs/specs/bearing-distribution-spec.md#6-fit-and-finish-the-conformance-suite).

## What's in this repository

This repository is two things at once, which is worth stating plainly because it explains the layout:

- **`plugin/`** — the BEARING plugin itself. This is what ships and what users install: three Skills, their canonical subagent definitions, the renderers, and the `bearing` CLI. Nothing here is written to at runtime.
- **`.bearing/`, `docs/decisions/`, `AGENTS.md`** — this repository's *own* use of BEARING. BEARING is self-hosted here, so its decision records, config, cost ledger, and evaluation sets sit exactly where they would in any other repo.
- **`docs/specs/`** — the specifications for each Skill and for the distribution layer.

The line between those first two is a hard rule, not a convention: **the plugin tree is read-only after install; all writes go to `.bearing/` (run state) or the configured decisions directory (decision content).** Plugin directories get replaced wholesale on update, so anything BEARING wrote inside itself would be destroyed on every upgrade.

## Install

Install the **plugin** in your agent runtime (Cursor, Claude Code, or Codex).
That ships Skills, hooks, MCP, and the CLI module. Open a workspace once so
`~/.bearing/bin` is populated, then add it to your PATH:

```bash
export PATH="$HOME/.bearing/bin:$PATH"
bearing --help
```

Full first-run steps: [`SETUP.md`](SETUP.md).

```bash
# Plugin (Cursor): add the marketplace, then install BEARING from /plugin
cursor-agent plugin marketplace add https://github.com/cleverb/bearing-system

# Plugin (Claude Code)
claude plugin marketplace add https://github.com/cleverb/bearing-system
claude plugin install bearing@bearing
```

Optional for CI and contributors: `uv tool install ./plugin` or
`pipx install ./plugin`. The Python distribution is named `bearing-system`; the
import package and command remain `bearing`. Python 3.9+, no third-party packages.

## Bootstrap a repository

```bash
cd /path/to/your/repo
bearing assessment    # scorecard of agentic decision readiness; works before init; always exits 0
bearing init          # detects your decision-record convention, writes .bearing/config.json
bearing doctor        # verifies everything resolves before you rely on it
bearing health        # aggregates current checks and statistics; always exits 0
```

Assessment and init also report capability-declared build-quality evidence:
PMD and Checkstyle for Java, ESLint and TypeScript configuration for JS/TS,
Ruff and Flake8 for Python, and Clippy for Rust. Unsupported ecosystems are
reported as `not-assessed`. Configuration is evidence for human review, never a
decision inferred automatically.

`bearing init` never guesses where your decisions live. If the repo already uses `docs/adr/`, `docs/ADRs/`, or anything else, it detects and asks — see [the legacy convention case](docs/specs/bearing-distribution-spec.md#33-the-legacy-convention-case).

Within the configured corpus, records may live at the root or in category
subdirectories such as `auth/`, `backend/`, and `frontend/`. BEARING recognizes
both `0004-title.md` and `ADR-0004-title.md`; IDs remain unique across the whole
tree.

Then use the optional onboarding guide—or simply try BEARING during ordinary work—to gather enough evidence to decide whether it is useful. [`QUICKSTART.md`](QUICKSTART.md) shows the available paths.

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
