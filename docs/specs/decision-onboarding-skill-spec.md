# Skill Spec: Decision Onboarding

`plugin/skills/decision-onboarding/`

*Primes a repository for BEARING. Not a new mechanism — a bounded, sequenced composition of `decision-recovery` and `decision-interview`, run once per repository, that produces one reviewable branch and a frozen baseline to test it against.*

---

## What this Skill is and isn't

**Is:** a one-time (per repository) orchestration that scaffolds the structure, runs a deliberately *scoped* recovery pass, conducts a small number of seed interviews, promotes a small number of Anchors, and hands off to normal operation — all as commits on one branch.

**Is not:** a general-purpose Recovery run. Onboarding's entire design is about doing *less* than Recovery is capable of on day one, on purpose — proving the loop closes on a small area before ever pointing full-strength extraction at an entire legacy codebase.

**Also is not: an installer.** Getting BEARING onto the machine belongs to the distribution layer — a marketplace install, or a vendored copy — and bootstrapping a repository belongs to `bearing init`. Onboarding *verifies* both happened and refuses to start otherwise. That separation is the whole reason Step 0a exists: a pipeline that installs its own preconditions cannot tell the difference between "not set up" and "set up wrong", and reports the second as the first.

## Trigger

Explicit human invocation only — `bearing onboard`, run once by whoever owns the pilot. Never automatic, never re-run silently on a repository that's already onboarded.

## Profiles

"Should I run full recovery before evaluating?" is a real question with no single right answer, so it is a named profile rather than a judgment call buried in prose. Set it in `.bearing/config.json` as `profile`, or pass `--profile`.

| Profile | Scopes | Promotions | Branch | Pilot | For |
| --- | --- | --- | --- | --- | --- |
| `pilot` | 1 | 3–5 | yes | yes | Proving the loop closes, fast. The default. |
| `thorough` | unbounded | bounded by review capacity | yes | yes | Coverage, in reviewed waves. |
| `audit` | unbounded | none | no | no | Measuring whether a larger investment is worth making. |

`audit` is the honest answer to "do I have time for this": it runs recovery, promotes nothing, and reports coverage and cost so the decision to invest in `thorough` rests on measurement instead of optimism.

What `thorough` relaxes is the anchor cap and the single-scope restriction. What it does not relax — and what matters *more* rather than less at larger scale:

- **The human authority boundary.** Unchanged, and not negotiable. More candidates is not an argument for reviewing each one less carefully.
- **Pre-registration of the pass/fail bar.** After two weeks of recovery investment, whoever ran it is strongly motivated to find a threshold the results happen to clear. `bearing onboard` compares the criteria file's modification time against the first pilot row in the ledger and refuses to proceed if the bar moved after results were visible.
- **Wave-bounded review.** Recovery generates in waves, each fully reviewed before the next is produced. This is what preserves "a human can review everything the pass produces" *without* capping total coverage. The original spec conflated reviewability with a fixed anchor count; separating them is what makes `thorough` safe. Wave size is the tighter of `review.wave_size` and what `review.budget_minutes_per_session` can actually absorb — configuring a wave of 200 against a 90-minute budget is a contradiction, and resolving it toward the larger number is how review becomes rubber-stamping.
- **Scope and test-ticket coordination.** Still required. Broad recovery makes it easier, and that is the real evaluation benefit of `thorough`: it addresses the null-result risk pilot mode explicitly worries about, where the tickets chosen for evaluation turn out not to touch the recovered area at all.
- **The frozen baseline.** Same tag. The report notes elapsed wall-clock time, so drift between the baseline and a weeks-later comparison is visible rather than invisible.

## Pipeline

### Step 0a — Preflight

A gate, not a setup step. `bearing preflight` (also run automatically by `bearing onboard`) verifies every precondition and stops before touching anything if one is missing:

- **Which skill copy resolved.** A repository's `.agents/skills/` takes discovery precedence over an installed plugin in both Cursor and Codex, so a vendored copy *silently shadows* the installed one. Preflight prints which copy won and, if vendored, the version pinned in config — because a candidate whose provenance cannot be reconstructed is evidence nobody can audit. <!-- bearing:ignore-paths: the vendored path exists only when `bearing vendor` has run -->
- **Config resolves cleanly.** Every layer that contributed, and every error. A repo fact overridden in `.bearing/config.local.json` is reported, since it makes one machine behave unlike every other clone. <!-- bearing:ignore-paths: the local override file is optional by design -->
- **Projection targets are writable.** Under the configured scope. A projection that fails halfway leaves a repository with some adapters current and others stale, which is worse than none.
- **The working tree is clean.** Onboarding compares a frozen baseline against a branch; uncommitted work means the comparison measures the working tree rather than the framework.
- **The decisions directory exists and its convention was detected, not assumed.** `bearing init` adopts `docs/adr/` or `docs/ADRs/` if that is what the repository already uses, and never migrates it.
- **The price book is present and the Model Tiering Contract holds.** A config that puts a frontier model on extraction fails here rather than after spending the money.

### Step 0 — Fork and freeze

Before anything else: create the onboarding branch, and tag the commit it forked from.

```
git tag bearing-baseline-<repo>-<date>
git checkout -b bearing-onboarding/<repo>
```

This exists because everything downstream depends on comparing "with BEARING" against "without" — and if main keeps moving during onboarding, that comparison is measuring drift, not the framework. The frozen tag, not whatever main happens to be on the day a given test ticket runs, is the baseline for every comparison in Step 5.

### Step 1 — Scaffold

Pure structure, no judgment calls. Performed by `bearing init`, which is idempotent and re-runnable. Every path below derives from `decisions.path`; nothing hardcodes `docs/decisions`.

```
docs/decisions/               # or docs/adr/, or whatever this repo already uses
├── README.md                 # states what's authoritative; explains shadow/
├── index.json                # generated disclosure index, empty at first
└── shadow/
    ├── README.md
    ├── candidates.jsonl      # empty
    ├── rejected.jsonl        # empty
    └── transcripts/          # interview transcripts, per the retention policy

.bearing/                     # run state and operator data, never decision content
├── config.json               # committed: the repo facts
├── pricing.json              # committed: price-book corrections
├── eval/                     # this repository's Gold/Dark/Negative sets
├── ledger/
│   ├── cost.jsonl            # append-only run history
│   └── pass-fail-criteria.md # the pre-registered bar for Step 5
├── runs/                     # gitignored
└── projections.lock.json     # what was generated, and what was deliberately skipped

AGENTS.md                     # repository root, with a BEARING-managed delimited block
```

`AGENTS.md` is never overwritten. BEARING owns a delimited region inside it and rewrites only that region, so a repository's own conventions sit alongside BEARING's without either clobbering the other. `CLAUDE.md` gets a one-line pointer to `AGENTS.md` only if the repository already has one — never a duplicated constitution.

The skills themselves are *not* scaffolded here. They arrive from the plugin, or from `bearing vendor` for the four cases where a pinned in-repo copy is genuinely preferable: air-gapped environments, audit contexts needing reconstructible provenance, CI runners that must not depend on user-level plugin state, and organizations that have forked a skill to add local instructions.

### Step 2 — Scoped Recovery pass

Run `decision-recovery`, restricted to one directory or service — never the whole repository in `pilot`. This is the single most important discipline in the entire onboarding procedure. Unscoped Recovery on a repo with zero existing Anchors produces a large, low-quality first batch, which is exactly the situation the cost-per-promoted-candidate kill switch exists to catch — except on day one there's no history yet for that metric to be meaningful against.

In `thorough` and `audit`, scope is unbounded but output is **wave-bounded**: `bearing onboard` will not authorize the next wave while any candidate from the current one is still `Reviewable`. That is what preserves reviewability without capping coverage — generating wave two while wave one is half-reviewed is how a review queue becomes a backlog nobody re-enters.

**Scope selection is coordinated with Step 5's test tickets, not made independently.** Whoever picks the scope for this step should be the same person flagging which upcoming tickets will exercise it. Picking scope and picking test tickets separately is close to guaranteeing a null result later — most tickets won't touch what was just recovered, and the pilot will look like it didn't help when the real story is that it was never tested against the part that changed.

### Step 3 — Seed Interviews

A short, targeted list of `decision-interview` sessions — the one or two people who'd feel it most if an agent got something wrong in the scoped area. Highest-risk Contracts first. Not comprehensive coverage; the goal is proving the interview mechanism works end-to-end on real, current knowledge, not documenting everything that person knows.

### Step 4 — First Anchors

Promote a small, deliberate number of candidates from Steps 2 and 3 — 3 to 5 in `pilot`, not everything the passes surfaced. Each promotion follows the full lifecycle from the Recovery and Interview specs: a human determines scope, current validity, and lifecycle state, not just confirms a summary. Each promoted candidate gets a real ADR in the decisions directory, an `@see` annotation on the implementation it governs, and an entry in the disclosure index.

The cap is enforced by `bearing onboard` rather than trusted. It is not about capacity — it is about keeping the first pass small enough that a wrong promotion is cheap to undo. `audit` caps it at zero by design.

The number is small on purpose. The goal of onboarding is proving the whole loop closes — evidence → candidate → promoted → annotated → an agent actually respects it next session — not maximizing graph coverage on day one.

### Step 5 — Pilot: onboarding branch vs. frozen baseline

This is where the branch stops being a bootstrap artifact and starts being a test fixture.

**Setup, before running any tickets:**
- Define the pass/fail bar *now*, not after seeing results. A concrete threshold — e.g., Contract-violation rate on the scoped area drops below X%, rework rate on those tickets improves by Y% — turns this from an open-ended experiment into something with an actual decision point at the end. Record it in `.bearing/ledger/pass-fail-criteria.md` before Step 5 begins, and commit it.

  It lives in the workspace, not in the skill's `references/`, for a reason that is not filing tidiness: the plugin is read-only at runtime and gets *replaced* on update. A filled-in criteria document written inside the plugin would be destroyed by the next version bump, taking the audit trail for the pilot with it. `references/` holds the blank template; the workspace holds the commitment.
- Select test tickets from the coordination done in Step 2 — tickets that genuinely touch the scoped, recovered area. `bearing onboard` warns when the selected ticket paths do not intersect the recovery scope, because that is the most common way onboarding produces a misleading null result: the pilot measures a BEARING run that had no recovered knowledge bearing on the work, and reports "no improvement" for a reason unrelated to the framework.

**Run each selected ticket twice:** once against the frozen baseline tag, once against the onboarding branch. Same ticket, same starting prompt, two different context conditions.

**Track, per run, not just token count:**
- token consumption (cost, same ledger shape as Recovery/Interview)
- rework rate — how many follow-up corrections did the result need
- Contract-violation rate — did the agent violate something the onboarding branch had documented that the baseline agent had no way to know about
- escalation correctness — did the agent stop and ask when it should have, rather than guess

Token count alone is a genuinely ambiguous signal here and shouldn't be reported in isolation: the onboarding branch will very likely use *more* tokens per session, because it's now loading `AGENTS.md`, the disclosure index, and relevant Contract summaries that the baseline never had. Higher token use paired with lower rework and lower Contract-violation rate is the framework working as intended, not a cost overrun. Token count reported alone, without those outcome metrics next to it, is close to meaningless either direction.

This is enforced rather than advised. `bearing report` **refuses** to print token figures for a pilot row that is missing `rework_count`, `contract_violations`, or `escalation_correct`, and names what is missing instead. A guideline here erodes the first time somebody is in a hurry and just wants the token number; a refusal does not.

### Step 6 — Handoff

Onboarding mode ends. The branch — scaffold, promoted Anchors, seed interview outputs, pilot results — is reviewed as one PR against the criteria set in Step 5. If it clears the bar, it merges, and the repository moves to normal operation: `decision-recovery` runs on its regular schedule (not scoped anymore, or scoped by whoever owns the next area), `decision-interview` fires ad hoc on escalation same as any repository. If it doesn't clear the bar, the branch and its pilot data are still useful — they're evidence for what the scope, seed set, or promotion choices got wrong before trying again, not a discarded experiment.

---

## Directory structure

Read-only, shipped inside the plugin:

```
plugin/skills/decision-onboarding/
├── README.md
├── SKILL.md
├── subagents/
│   └── onboarding-coordinator.md   # canonical; projected to each runtime's format
└── references/
    ├── agent-procedure.md          # git tag, bearing init, bearing report --pilot
    └── pilot-metrics.md
```

Writable, in the workspace:

```
.bearing/ledger/pass-fail-criteria.md   # the filled-in, committed, pre-registered bar
.bearing/ledger/cost.jsonl              # pilot rows, per condition
.bearing/runs/onboarding.json           # which step this repository reached <!-- bearing:ignore-paths -->
```

`subagents/onboarding-coordinator.md` is canonical and is never read by a runtime directly. It is projected to `.cursor/agents/*.md`, `.claude/agents/*.md`, and `.codex/agents/*.toml`, because those three formats are mutually unreadable — Codex requires TOML with a `developer_instructions` key where Cursor and Claude Code read a markdown body. Where the output lands is an operator choice (`projections.subagents.scope`): `repo` commits adapters so anyone cloning gets them, `user` writes to the home directory, and `ephemeral` renders to a temp directory at session start and commits nothing.

## Success Criteria

- The onboarding branch is one reviewable PR, not four disconnected artifacts.
- Every promoted Anchor traces to a candidate in the shadow graph.
- The pass/fail bar was written down before Step 5 ran, not after — verified by mtime, not trusted.
- Test tickets in Step 5 were selected to overlap Step 2's scope, not chosen independently.
- Token consumption is never reported without a paired outcome metric — refused, not merely discouraged.
- Preflight passed before any step ran, and named which skill copy resolved.
- `bearing uninstall` removes every generated adapter and leaves every decision record, the index, the shadow graph, the rejection ledger, and the transcripts intact.
