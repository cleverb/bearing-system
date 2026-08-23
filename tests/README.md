# Tests

Standard library `unittest`, no pytest, no fixtures package, no dependencies.

That is not minimalism for its own sake. The CLI is held to running on a bare
Python 3.9 with nothing installed, because `bearing init` runs on a repository
that has not installed anything yet. A test suite that needs `pip install` first
would be testing a different program than the one people run.

```bash
python3 -m unittest discover -s tests -p "test_*.py"          # everything
python3 -m unittest discover -s tests -p "test_render.py" -v  # one module
python3 -m unittest discover -s tests -k ManifestConformance   # one class
```

Every test creates a real `git init` repository in a temp directory. Half of what
BEARING does — baseline tags, staleness from commit dates, working-tree checks —
only exists in a git context, so a fake directory would test a different program.

## What each module holds

| Module | Concern |
| --- | --- |
| `test_config.py` | The five-layer resolution chain, repo-fact versus operator-fact precedence, and `bearing init` adopting an existing convention rather than imposing one |
| `test_render.py` | Projection determinism, drift detection, configurable targets, recorded skips, and delimited-block management |
| `test_packaging.py` | Plugin-root containment and the installed-copy behaviour described below |
| `test_mandate.py` | Authority rules, model-tier advisories, honest cost accounting, optional profile helpers, and the conformance suite itself |
| `test_v02.py` | Effective-workspace, scope, runtime evidence, hook, lock-authority, health, measurement, detector, and workflow-inspection contracts |

## Local testing to marketplace promotion

Five tiers, each catching a failure class the one below it cannot see.

**Tier 0 — iteration.** Copy the plugin into Cursor's local plugin directory.

```bash
PYTHONPATH=plugin/src python3 -m bearing package --local
```

Reload Cursor after each copy. See ADR-0013 for why local and marketplace MCP
launch configs differ.

**Tier 1 — manifest validation.** Every client manifest is generated from
`plugin/plugin.json`, so a hand-edited manifest is drift rather than a fix.

```bash
PYTHONPATH=plugin/src python3 -m bearing package --check
python3 -m unittest discover -s tests -k ManifestConformance
```

The repository root *is* the marketplace, so a local catalog needs no build step:

```bash
claude plugin marketplace add . --scope local
```

**Tier 2 — copy isolation.** The tier that has to be automated, because the bug
class it catches is invisible in a checkout and fatal after install.

Cursor and Claude Code both *copy* a plugin into a versioned cache, and Agent
Plugins v1.0.0 §4.1.3 requires a client to reject any package path resolving
outside the plugin root. A `../` reference to a sibling skill reads perfectly
naturally in a monorepo and is something a conforming client must refuse. A
git-hosted install adds a second failure mode on top: an over-broad `.gitignore`
means a needed file simply does not arrive, and that only ever breaks for other
people.

```bash
python3 -m unittest discover -s tests -p "test_packaging.py" -v
bash scripts/ci/git-hosted-install.sh
```

The script clones this ref into an unrelated directory, drives a full
`init → doctor → render → index → lint` cycle against a scratch repository, makes
the plugin tree read-only and repeats, then checks the tree is byte-identical to
what was installed and that `uninstall` leaves decision content behind.

**Tier 3 — publish.** Cursor at `cursor.com/marketplace/publish`; Claude Code by
pointing at the git-hosted `.claude-plugin/marketplace.json`.

**Tier 4 — real-client conformance.** Install a release candidate in scratch
repositories using supported runtime clients, exercise all six behaviors in the
evidence schema, and qualify the release:

```bash
PYTHONPATH=plugin/src python3 -m bearing package --release-check
```

Tier 4 is scheduled and manually dispatchable. It does not gate ordinary PRs.

## Nothing here gates a merge on inference

`bearing lint` and `bearing verify` run in CI. Neither recovery nor scoring does.
A confidence score is a statement about evidence, never a statement of
organizational authority, and `bearing verify` reads `.github/workflows/` looking
for exactly that mistake — so a job added later that gates on a recovery command
fails the ESCALATE pillar rather than passing quietly.
