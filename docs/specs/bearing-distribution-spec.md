# BEARING distribution, config, and projection

Canonical description of how the plugin is installed, how a repository is bootstrapped, and how canonical sources become runtime adapters. The architecture reasoning lives in [`BEARING.md`](../../BEARING.md); this spec is the operational Contract for the distribution layer.

---

## 1. Layers

Install is not a step in recovery, interview, or onboarding. Conflating those layers is what produces a Skill that tries to install itself.

| Layer | Owns | Answers |
| --- | --- | --- |
| Distribution | Marketplace, `plugin/plugin.json`, per-client manifests, the `bearing` CLI | How does the machinery get onto this machine? |
| Bootstrap | `bearing init`, `bearing doctor`, `bearing assessment` | How does *this* repository start using it? |
| Operation | The Skills — recovery, interview, onboarding | How is the work performed? |

**Plugin install and CLI install are both required** for the full product. A marketplace install of the plugin delivers Skills, subagent definitions, and the `workspaceOpen` hook. The hook invokes `python3` against a wrapper in the plugin tree so it does not depend on `bearing` being on `PATH`. Interactive commands (`init`, `lint`, `verify`, `onboard`, `context`) still need the CLI, via `pipx install ./plugin` or `PYTHONPATH=plugin/src python3 -m bearing` from a checkout.

The Python distribution name is `bearing-system`. The import package and CLI
command remain `bearing` so installation naming does not leak into runtime use.

### 1.4 Local testing to marketplace promotion

Four tiers, each catching a failure class the one below it cannot see. The same list is in [`tests/README.md`](../../tests/README.md).

**Tier 0 — iteration.** Point a client at the working tree.

```bash
ln -s "$(pwd)/plugin" ~/.cursor/plugins/local/bearing
```

**Tier 1 — manifest validation.** Every client manifest is generated from `plugin/plugin.json`. A hand-edited manifest is drift.

```bash
PYTHONPATH=plugin/src python3 -m bearing package --check
python3 -m unittest discover -s tests -k ManifestConformance
```

**Tier 2 — copy isolation.** Cursor and Claude Code copy a plugin into a versioned cache. Agent Plugins v1.0.0 §4.1.3 requires a client to reject any package path resolving outside the plugin root. A `../` reference reads perfectly in a checkout and is fatal after install.

```bash
python3 -m unittest discover -s tests -p "test_packaging.py" -v
bash scripts/ci/git-hosted-install.sh
```

**Tier 3 — publish.** Cursor at `cursor.com/marketplace/publish`; Claude Code by pointing at the git-hosted `.claude-plugin/marketplace.json`.

---

## 2. The purity rule

**Nothing under `plugin/` is written to at runtime.** Plugin directories are replaced wholesale on update. Writes go to `.bearing/` (run state) or the configured decisions directory (decision content).

Enforced by the packaging suite: the plugin tree is mounted read-only and a full pipeline is run against it. A write inside the plugin fails the build.

A path may not escape the plugin root. Skills that need a sibling schema ask the CLI (`bearing schema candidate`) rather than using `../`.

---

## 3. Configuration

Everything derives from `decisions.path`. No script hardcodes a decisions directory.

### 3.3 The legacy convention case

`bearing init` never guesses where decisions live, and never migrates a corpus.

If the repository already uses `docs/adr/`, `docs/ADRs/`, or another known convention, init detects it and asks — or, with `--yes`, adopts the detected directory. The location is recorded as a repository fact. Demanding a bulk rename before the tooling does anything useful is the adoption friction the retrospective path exists to remove.

Where the chosen path is not `docs/decisions/`, `bearing init --record-deviation` writes a short decision record explaining the location, so the next person who looks in the recommended place finds an explanation rather than an empty directory.

The configured path is the root of a recursive corpus, not a requirement that
every record be a direct child. Category directories are supported, and both
`NNNN-title.md` and `ADR-NNNN-title.md` are recognized. Categories do not create
namespaces: duplicate ADR IDs anywhere below the corpus root are lint errors.
The configured shadow subtree is always excluded from authored-record traversal.

---

## 4. Projection

Canonical sources live in the plugin. `bearing render` produces runtime adapters. Generated files carry a `DO NOT EDIT` header and are recorded in `.bearing/projections.lock.json`.

- **Subagents** — genuine format gap (markdown frontmatter vs Codex TOML).
- **Rules** — genuine format gap (`.cursor/rules`, `AGENTS.md`, Copilot instructions).
- **Contracts** — accepted Contract records are compiled into the `AGENTS.md` block as an agent-facing digest. `bearing context <path>` returns the subset whose `scope` matches a file. Linter configs and CI workflows are not generated: `bearing lint` and `bearing verify` already consume those Contracts structurally.
- **SKILL.md** — not projected. Agent Skills is an open standard.

Default subagent scope is `repo` (adapters committed with the clone). Operators who want adapters in the home directory set `projections.subagents.scope` to `user`.

---

## 5. Bootstrap commands that actually exist

```bash
bearing init              # detect convention, scaffold, optional first render
bearing assessment        # agentic decision-readiness scorecard; works before init; always exits 0
bearing doctor            # what resolves, from where, and what is broken
bearing preflight         # optional controlled-pilot readiness check
bearing render            # generate adapters; --check for drift
bearing index             # regenerate docs/decisions/index.json
bearing lint              # structural decision-graph integrity
bearing verify            # mandate conformance
bearing context <path>    # index entries whose scope matches this file
bearing onboard           # readiness check and optional evaluation guidance
bearing vendor            # copy Skills into .agents/skills/ and pin the version
bearing vendor --pin      # pin version when copies already exist
bearing ledger            # print the cost-ledger path
bearing eval <set>        # print an evaluation-set directory (gold|dark|negative|escalation)
bearing transcripts       # print the transcript directory
```

An optional evaluation-criteria template is seeded by `bearing init` into `.bearing/ledger/pass-fail-criteria.md`. There is no `--pass-fail` flag and the file is not required for ordinary use.

### Assessment of build quality evidence

Assessment recognizes PMD- or Checkstyle-named XML files as configuration
evidence, then distinguishes the stronger signal of literal Gradle references to PMD `ruleSetFiles` and
`ruleSetConfig`, Checkstyle `configFile`/`config`, and the conventional
`config/checkstyle/checkstyle.xml` location when the Checkstyle plugin is
applied. It parses local XML with the Python standard library and never executes
Gradle.

The result distinguishes three states:

- **present** — configured XML paths are named in an agent baseline, or its
  consequential rules and configured values are summarized there;
- **partial** — some sources are surfaced, or only a Gradle verification command
  is documented; and
- **absent** — configured rules exist but are invisible to agents before
  generation, or no custom PMD/Checkstyle XML was discovered.

An XML file by itself is evidence that a ruleset may matter. Selection from a
Gradle build is stronger evidence that the repository deliberately makes it
operative. Neither observation establishes organizational authority or proves
that an architectural decision was made.

This is an informational discovery aid, not a claim that every PMD or Checkstyle
rule deserves an ADR. Dynamic Gradle expressions are not guessed, and
assessment never runs or gates on the repository's build.

`bearing init` reports this same build-quality subset after scaffolding. It does
not copy the rules into generated guidance or create a decision record. When a
consequential rule has a customized value, init describes it as an opportunity
to review decision ancestry: a maintainer may surface the operational rule,
recover a candidate separately, or decide that no architectural record is
warranted.

When configured build rules are not fully surfaced, assessment does not award
the top `review-aware` readiness band even if the decision corpus, Anchors, and
review templates are otherwise present. The result remains informational and
still exits zero.

---

## 6. Fit and finish: the conformance suite

`bearing verify` computes the structurally testable parts of the four mandates;
it does not certify inferred intent, decision quality, or adoption success:

| Pillar | What it checks |
| --- | --- |
| ESCALATE | Anchors resolve; superseded records have successors; no inference gates a merge; escalation fixtures score recall when present |
| ANCHOR | No shadow pointers; accepted records are reachable; coverage within `scope.include` |
| PROJECT | Deterministic render, lock drift, DO-NOT-EDIT headers, no redundant projection |
| EVOLVE | Idempotent fingerprints, rejection durability, lifecycle honesty, cost trend |
| USABILITY | Index budget, review-queue size, Negative Set hallucination rate, uninstall safety, documented paths exist |

Missing evaluation fixtures are a **WARN**, not a silent pass. An empty Negative Set or escalation set cannot claim the mandate is met; it can only admit the metric was not measured.

CI for this repository runs the unit suite, `package --check`, copy-isolation, and a dogfood job (`doctor`, `render --check`, `index`, `lint`, `verify`). Nothing in CI gates a merge on a recovery signal.
