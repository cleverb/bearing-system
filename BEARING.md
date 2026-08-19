# BEARING: An EOCR-Based Decision System for Human-Agent Engineering

*A reference architecture for how engineering knowledge should be structured, anchored, enforced, and consumed — by developers and by agents.*

---

## How to use this document

This document is written to be read twice, by two different kinds of readers.

**If you are a human engineer:** read it top to bottom once. After that, treat it as reference — jump to the section that answers your current question (Where do I document a constraint? Why does this legacy code still exist? How do I write a Skill?).

**If you are an agent:** this document is the canonical description of how knowledge is organized in this organization's repositories. If you are asked to modify code, generate documentation, propose an architecture, or act autonomously, this document tells you where authoritative knowledge lives, what you are permitted to infer versus required to retrieve, and when you must stop and escalate to a human. Treat the Decision Graph section and the Escalation Rules throughout as binding, not advisory.

---

## Part I — The Problem

### Why this document exists

Engineering teams are in an uncomfortable transitional period. AI coding agents have moved faster than the practices required to govern them. Most repositories now contain some combination of:

- editor-specific rule files (`.cursor/`, `.windsurf/`, `.github/copilot-instructions.md`) <!-- bearing:ignore-paths: describes other repositories -->
- `AGENTS.md`, `CLAUDE.md`, or similar repository instructions
- custom prompts, MCP servers, linters, CI checks
- emerging agent Skills and specialized subagents
- internal documentation scattered across Confluence, tickets, and chat

Individually, each of these is useful. Collectively, they rarely constitute a *system*. Teams end up maintaining bridge architectures — copying the same instruction into three formats, deciding by instinct whether a rule belongs in `AGENTS.md` or an editor file, exposing tools without defining how they should be used, and asking agents to navigate repositories whose architectural intent is almost entirely implicit.

The symptoms show up downstream, not at the point of failure. An agent generates an implementation that is locally reasonable and organizationally wrong. CI discovers a constraint that was never available during generation. A PR reviewer identifies an architectural expectation that existed only as institutional knowledge. The developer re-prompts, regenerates, and repeats.

**This is easy to mistake for a model-quality problem. It is almost always a decision-system-quality problem.** A codebase can contain excellent code and still be a poor environment for generative development if the decisions governing that code are hard to discover, inconsistently represented, disconnected from the implementation, or impossible to enforce before generation completes.

### A concrete failure: the missing guardrail

Here is what this looks like in practice, and an example  of why this framework was written.

The repository has an established cyclomatic-complexity ceiling for Java services — a real constraint, agreed on, backed by a linter rule. An agent working a routine feature request extended a method past that ceiling. Nothing stopped it. The constraint existed in the codebase's tooling, but it did not exist anywhere the agent was reading *before* it wrote the code. The failure surfaced downstream, in review, after the work was already done and needed to be redone.

This is not a story about the agent being careless. It is a story about a Contract that was **enforced but not discoverable**. The complexity ceiling lived in a linter config the agent never consulted, was never summarized in an `AGENTS.md` the agent was told to read, and had no annotation on the method itself warning that it was close to the limit. The rule was real. It was simply invisible until it was too late to matter.

Every section that follows is, in part, an answer to how that specific failure gets prevented — not by writing more documentation, but by making sure a Contract like "cyclomatic complexity MUST NOT exceed N" is discoverable at generation time, not just enforceable at commit time. We return to this example directly in Part V.

---

## Part II — The Foundation

### What Diátaxis got right

[Diátaxis](https://diataxis.fr) organizes documentation around user need rather than document format, distinguishing four forms: **tutorials** (help someone learn), **how-to guides** (help someone accomplish a task), **reference** (provide precise information), and **explanation** (help someone understand).

The insight that matters is not the four categories themselves. It's that these are fundamentally different forms of knowledge with different standards of success. A tutorial should not become an exhaustive reference manual. Reference should not force someone through an essay before revealing a parameter. A how-to guide should not become a conceptual course. Explanation should not masquerade as operational instruction.

That separation becomes more valuable, not less, in agentic engineering — because documentation is no longer only *read*. It is retrieved, interpreted, transformed into plans, used to invoke tools, checked against implementation, and acted upon autonomously. The question expands from *"what kind of documentation does this user need?"* to *"what kind of knowledge does this human-agent system need in order to understand, act, verify, and evolve safely?"*

**EOCR is Diátaxis translated for that environment.**

---

## Part III — EOCR: Four Forms of Operational Knowledge

EOCR defines four knowledge functions: **Entry — Operations — Contracts — Rationale.**

These are not primarily folders or file types. They describe **the job a piece of engineering knowledge is performing.** A README can contain Entry and Operations. An ADR can contain Rationale and Contract. An `AGENTS.md` can contain Operations and Contract. A Skill can operationalize both. The goal is not to force every artifact into exactly one bucket — it is to make the *role* of the knowledge explicit, so a human or an agent encountering it knows what standard to hold it to.

### Entry — *How do I safely enter this system?*

Entry is the descendant of the tutorial. It provides orientation and a successful first encounter with a repository, service, or engineering environment.

For a human, Entry answers: What is this system? How do I run it? Where do I begin? What's the expected workflow?

For an agent, Entry answers: What kind of repository is this? What instructions govern my behavior? What capabilities are available to me? What decisions should I retrieve before making changes? What actions am I safe to perform autonomously? Where are the authoritative Contracts and Rationale? When must I stop and request human judgment?

Entry is a **discovery surface for the decision environment**, not an exhaustive explanation of it. Good Entry documentation deliberately reduces ambiguity without attempting to explain the entire system in one place.

*Typical Entry surfaces:* `README.md`, quickstarts, repository maps, architecture orientation docs, capability indexes, links to the ADR index, links to `AGENTS.md` and Skills.

### Operations — *How is this work performed?*

Operations is the descendant of the how-to guide. It describes how competent participants — human or agent — accomplish real engineering work: adding an endpoint, creating a component, running a migration, responding to an incident, reviewing a PR, adding an MCP tool.

In conventional documentation these are procedures. In agentic engineering, some become **executable operational knowledge** — this is where Skills matter. A Skill is not synonymous with Operations; Operations is the knowledge function, and a Skill is one mechanism for packaging that knowledge so an agent can reliably act on it.

A mature operational procedure makes its execution model explicit:

- prerequisites and inputs
- steps and available tools
- boundaries and required checks
- expected outputs and rollback behavior
- escalation conditions and required human approval points

This lets the same organizational knowledge support different participants: a human reads the procedure, an agent loads the Skill implementing it, a subagent executes that Skill, a reviewer verifies the required checks occurred. The procedure stays conceptually stable even as the execution technology changes underneath it.

### Contracts — *What is true, required, permitted, or forbidden?*

Contracts are the descendant of reference. Traditional reference documentation describes a system precisely; agentic engineering makes the normative force of that precision far more important, because an agent will act on what a Contract says without pausing to wonder whether it's aspirational.

*Typical Contracts:* API specs, schemas, CLI interfaces, configuration definitions, repository conventions, dependency boundaries, permissions, security constraints, design-system requirements, required checks, contribution requirements, automation boundaries, human-approval requirements — **and things like a cyclomatic-complexity ceiling.**

A Contract should minimize interpretation. Terms like **MUST**, **MUST NOT**, **REQUIRED**, **RECOMMENDED**, **DEPRECATED**, **HUMAN APPROVAL REQUIRED**, and **SAFE TO AUTOMATE** are coordination signals, not stylistic emphasis.

This is also where machine verification becomes powerful. Whenever possible, a Contract should progress along this ladder:

```
documented → structured → machine-readable → machine-verifiable
```

A convention written only in prose is useful. The same convention expressed as a schema is stronger. Validated in CI, stronger still. **Surfaced to an agent before generation, strongest of all** — because that's the only point in the ladder where the Contract can prevent the violation instead of merely detecting it. The complexity-ceiling failure in Part I was a Contract stuck at "machine-verifiable" that never made it to "surfaced before generation." Closing that gap is the objective, not maximizing automation for its own sake.

### Rationale — *Why is it this way?*

Rationale is the descendant of explanation. It preserves context, history, tradeoffs, rejected alternatives, and organizational intent.

*Typical Rationale:* ADRs, design documents, tradeoff analyses, postmortems, domain models, migration histories, explanations of intentional technical debt.

This matters more for agents than it ever did for humans, because agents are highly capable at spotting local patterns while having no access to the history that made those patterns necessary. A compatibility layer looks like unnecessary abstraction. Duplicated logic looks like an obvious refactor. A hard-coded value looks like unfinished work. A seemingly obsolete interface may still be supporting a migration in progress.

**Without Rationale, an agent can produce a technically elegant change that moves the architecture backward — and be entirely confident while doing it.** The Decision System exists specifically because systems tend to preserve *what* exists while losing *why* it exists, and that loss is the primary source of architectural drift.

ADRs are the strongest Rationale artifact, but rationale is not the whole of an ADR's job. A single ADR often emits knowledge into all three other categories:

> *"We selected Pattern B because of these constraints"* — that's Rationale.
> *"New implementations MUST use Pattern B"* — that's a Contract, once accepted.
> *"Existing Pattern A implementations should be migrated according to this procedure"* — that's Operations.

**Decisions emit knowledge. They don't just record it.**

### Where ADRs live: `docs/decisions/`, not `docs/adr/` or `docs/adrs/`

This is a small structural choice with outsized effect on whether Rationale actually gets discovered, so it's worth settling explicitly rather than leaving it to whichever engineer sets up the first directory.

The traditional default, going back to Michael Nygard's original 2011 proposal and reinforced for years afterward, was <cite index="12-1">keeping decision records in the source repository under a location like doc/adr, so they stay easily available to whoever is working on the code</cite>. That convention is still common, and plenty of mature projects run on it successfully.

But the convention is visibly shifting, and the reasoning behind the shift is worth adopting on its merits, not just its popularity. The team behind one of the most widely used ADR tooling references switched their own default from "adr" to "decisions" and <cite index="8-1">documented why: teams that use the word "decisions" instead of the abbreviation "ADRs" tend to start putting more into the directory — vendor decisions, planning decisions, scheduling decisions — because the plain word invites it in a way the acronym doesn't</cite>. Their stated hypothesis is that <cite index="8-1">people orient faster around ordinary words than abbreviations, and drop the more intimidating "record" and "architecture" framing that quietly discourages non-architects from writing decisions down at all</cite>. That is exactly the failure mode this document is trying to close — a Contract or Rationale that exists but never gets written because the container for it feels reserved for someone else.

Current guidance reflects that this is now a live split rather than a settled question in one direction: recent write-ups on ADR practice describe <cite index="6-1">docs/adr/ and docs/decisions/ as the two directories teams commonly use</cite>, and one recent field guide states plainly that <cite index="10-1">docs/adr/ or docs/decisions/ is the most popular approach precisely because it keeps the decisions version-controlled alongside the code they describe</cite>. Real organizations actively consolidating their own decision trees illustrate the same instinct toward a single canonical location, whichever name they land on — one recent internal ADR standard explicitly retired a second, competing decision directory and declared a single canonical tree the enforced convention going forward, precisely to stop institutional memory from splitting across two places.

**`docs/adrs/`** — the plural of the abbreviation — is the pattern to actively avoid. It doesn't appear as a recommended convention in any of the guidance above. It inherits the acronym-friction the "decisions" rename was meant to fix, while also introducing a pluralization inconsistent with the file-naming convention inside it (the files themselves are singular — `0001-use-postgresql.md`, not `0001-use-postgresql-adr.md`). It is the worst of both established options: neither the traditional default nor the direction of travel.

The recommendation, and the pattern this document follows throughout:

```
docs/
└── decisions/
    ├── 0001-record-architecture-decisions.md
    ├── 0002-use-typescript-for-all-new-features.md
    └── 0003-component-tokenization-strategy.md
```

Numbered, zero-padded, sequential filenames are the one part of this convention with no real disagreement across sources — every tool and every style guide surveyed uses them, because sequential numbering is what makes chronological order legible at a glance without opening a file. Keep that part regardless of which directory name is chosen.

This is also a direct application of the Projection principle from Part IV: don't invent a bespoke convention when an emerging one already carries real-world momentum and a documented reason for existing. Settle into `docs/decisions/` for the same reason this document settles into deterministic renderers over portable file formats — it's the option the ecosystem is actively converging toward, not the option that happens to be first alphabetically or most familiar from five years ago.

**A recommendation for a new repository, not a migration order for an existing one.** A repository already using another convention keeps it. `bearing init` detects the existing directory and adopts it — recording the location as a repository fact rather than assuming a default — and never renames or moves a corpus. Demanding a bulk relocation before the tooling does anything useful is the same adoption friction the retrospective recovery path exists to remove, and it would trade a real cost (broken links, rewritten history, an afternoon of review) for a naming preference. Where the choice is genuinely open, choose `docs/decisions/`. Where it is not, `bearing init --record-deviation` writes a short decision record explaining the location, so the next person who looks in the recommended place finds an explanation rather than an empty directory.

---

## Part IV — The Decision System

### EOCR is not the Decision System

This distinction is the load-bearing wall of the whole document, so it's stated plainly:

> **EOCR answers: what kind of knowledge is this?**
> **The Decision System answers: how does that knowledge participate in engineering work?**

EOCR gives knowledge a grammar. The Decision System gives it **topology, locality, relationships, authority, lifecycle, enforcement, execution, and agency.** Without the second half, EOCR collapses into another four-folder documentation scheme that nobody consults during real work — which is exactly what happened to most teams' ADR directories.

### From documents to a Decision Graph

Separate **knowledge nodes** from **operational relationships.**

**Knowledge (EOCR):** `Entry → Operations → Contracts → Rationale`

**Decision-system behavior:** `Discover → Anchor → Constrain → Execute → Verify → Evolve`

Artifacts participate in both dimensions simultaneously:

| Artifact or mechanism | Primary EOCR function | Decision-System role |
|---|---|---|
| Architecture overview | Entry + Rationale | Orientation |
| ADR | Rationale + Contract | Decision capture |
| `@see ADR-*` annotation | Anchor | Locality |
| `@remarks` | Rationale | Local context |
| `@deprecated` | Contract + state | Signal |
| Backlog link | Operations + state | Execution linkage |
| CONTRIBUTING.md | Contracts + Operations | Governance |
| Skill package | Operations + Contracts | Capability boundary — no Projection needed, open standard |
| Canonical subagent definition | Contracts + Operations | Actor semantics |
| Canonical rule source | Contract | Governance semantics |
| Deterministic renderer | — | Adapter generation (Projection) |
| Generated `.cursor/`, `.codex/`, `.windsurf/` files | Generated projection | Runtime-native execution |
| Linter | Consumes Contracts | Enforcement |
| CI | Consumes Contracts | Verification |
| PR template | Operations + Contracts | Quality gate |
| AGENTS.md | Contracts + Operations | Agent governance |
| MCP | — | Capability / knowledge access |
| Human reviewer | Consumes all four | Judgment |

Reality is not symmetrical: some things are knowledge, others are relationships, others are actors, others are enforcement mechanisms. Trying to classify everything as "documentation" obscures the architecture that's actually needed. The rest of Part IV walks through each Decision-System behavior in turn.

### Anchors: connecting implementation to intent

Nodes are not enough. Documentation systems emphasize artifacts; Decision Systems must also emphasize the relationships *between* them.

Take a legacy component. Its source tells you what exists. An ADR explains why it exists and what should eventually replace it. A ticket represents the remaining migration work. A Skill explains how to perform that migration. A Contract defines what new code is allowed to do. A test verifies behavior. **Unless these are connected, whoever encounters the component has to reconstruct those relationships independently** — which is exactly where humans lean on institutional memory and agents improvise.

Annotations provide the missing locality — they connect implementation → architecture → execution directly in the code, so nobody has to go looking.

```typescript
/**
 * A highly flexible Button component used for primary actions.
 *
 * @remarks
 * This component is currently undergoing a refactor to support the new
 * Design System tokens. Avoid adding new logic to the legacy `variant` prop.
 *
 * @see {@link https://github.com/org/repo/docs/decisions/0012-button-tokenization.md | ADR-012}
 * @see {@link https://jira.yourcompany.com/browse/DSYS-552 | DSYS-552: Migration ticket}
 *
 * @deprecated Use `UIButton` from the foundation library for all new features.
 */
export const Button: React.FC<ButtonProps> = ({ label, onClick, variant }) => {
  // Implementation...
};
```

Reading this block by function: `@deprecated` communicates state and Contract. `@remarks` supplies localized Rationale. `@see ADR-012` creates a relationship to the governing decision. `@see DSYS-552` connects the implementation to active work.

**The annotation is not another EOCR category. It is graph infrastructure.** This is why an agent-ready repository needs more than better documents — it needs better connections between them. An agent that reads this block has a fundamentally different task than one that finds a bare deprecated component: it shifts from *blind optimization* ("this is inefficient, I should refactor it") to *informed participation* ("this is deprecated on purpose, the replacement is `UIButton`, and I should only touch it if I'm prepared to move ticket DSYS-552").

### Lifecycle: decisions have state

Decision-aware systems need to understand time, not just structure.

- An ADR may be: `Proposed → Accepted → Deprecated → Superseded`
- A component may be: `Preferred → Legacy → Deprecated → Removed`
- A migration may be: `Planned → Active → Blocked → Complete`

An annotation pointing to an accepted ADR communicates something very different from one pointing to a superseded one. The Decision Graph is therefore not merely a graph of knowledge — it is a **stateful graph of organizational intent.**

**Escalation rule, binding for agents:** an agent encountering a superseded decision must not silently choose the next plausible interpretation. It must follow the successor decision or escalate to a human. A linter discovering a broken ADR link should not treat it as cosmetic documentation debt — the implementation has lost part of its decision ancestry, and that is a structural problem, not a typo.

The standing question for any participant, human or agent, is not *"can I retrieve this?"* but **"is this still authoritative?"**

### Enforcement: closing the gap between knowledge and reality

A Contract nobody checks remains advisory. Decision-aware engineering connects normative knowledge to enforcement — this is where linting stops being about syntax and starts being the **immune system** that detects architectural drift. Traditional linters check whether code is *correct*. Decision-aware linters check whether code is *honest*.

Their job is validating the Decision Graph itself: making sure the nerve endings (annotations) stay connected to the brain (ADRs). Concretely, that means:

- **Constraint-based linting** — block use of a `@deprecated` component unless it carries a `@see ADR-XXX` link.
- **Link validation** — verify that a referenced ADR path actually exists in `/docs/decisions/`.
- **Migration enforcement** — flag a new instance of a legacy pattern if the branch isn't tagged with an active migration ticket.
- **Annotation-to-backlog sync** — flag `@todo` comments with no linked ticket, so tasks don't silently vanish into "dark matter."
- **Agent-specific rules** — require every `SKILL.md` to carry a `Context` and `Instructions` header so it's reliably machine-readable.

The more advanced version of this is a **reviewer subagent acting as a dynamic linter**: it reads the PR template, looks at the diff, and actually navigates to the linked ADR to check whether the implementation matches the *spirit* of the decision, not just its letter.

> Traditional linter: *"This variable name is too short."*
> Subagent linter: *"You're using Flexbox here, but ADR-012 says new layout components move to CSS Grid. Please reconcile."*

A linter in a decision-aware system isn't checking for missing semicolons — it's checking for **missing intent.**

**This is precisely the layer that failed in the cyclomatic-complexity example.** The linter existed and would have caught the violation — eventually, in CI, after the work was done. What was missing was the earlier stage: a Contract stated where the agent could read it *before* generating the method, and an annotation on any method already close to the ceiling warning that it was load-bearing at its current complexity. Enforcement without discoverability only ever produces late correction. The fix, covered in Part V, is to push the same Contract further left.

### Projection: canonical knowledge, tool-native execution

Different editors and agent runtimes will always have different capabilities, configuration formats, and lifecycle models. Requiring every tool to consume one identical file format sounds like agnosticism, but it isn't — it just relocates the coupling into whichever format everyone agreed to use, and support for linking or discovering shared definitions varies enough across tools that a single portable file rarely stays readable everywhere for long.

The governing principle:

> **Standardize the organizational source. Do not require a standardized runtime representation.**

Canonical definitions — a subagent's mission, boundaries, escalation rules, tool access, or any other Contract — live as organizational source material, alongside the capability they serve:

```
skills/
└── decision-recovery/
    ├── README.md
    ├── SKILL.md
    └── subagents/
        ├── decision-archaeologist.md        # canonical
        └── decision-recovery-reviewer.md    # canonical
```

One deterministic renderer, owned by the tooling rather than by each Skill, produces whatever representation each runtime actually consumes:

```
skills/*/subagents/*.md          canonical definitions
             │
             ▼
      bearing render
             │
    ┌────────┼────────┐
    ▼        ▼        ▼
.cursor/  .claude/  .codex/
agents/   agents/   agents/
*.md      *.md      *.toml
```

The renderer is a single command, not a script per Skill. That is a correction worth stating explicitly, because a `render-subagents.py` inside every Skill is the natural-looking first design and it is wrong in two ways: it duplicates the same translation logic once per Skill, and it puts a writable script inside a tree that must be read-only at runtime. Worse, it invites exactly the mistake the next section warns against — once each Skill owns a renderer, adding one for `SKILL.md` looks like consistency rather than the pointless work it is.

The generated files are **adapters, not independent sources of organizational truth.** Each one carries a `DO NOT EDIT` header naming the canonical source it came from and the command that regenerates it, `bearing render --check` reports any hand edit as drift, and `.bearing/projections.lock.json` records every artifact produced *and* every target deliberately skipped — so an absent adapter is distinguishable from a broken one without anyone having to guess.

**Where adapters land is an operator choice, not a repository one.** `projections.<kind>.scope` takes three values, and each answers a real situation: `repo` commits adapters into the working tree so anyone cloning the repository gets them; `user` writes to the home directory, for machinery identical across every repository or for repositories you do not own; `ephemeral` renders to a temp directory at session start and commits nothing at all. Which *runtimes* a repository supports is a repository fact and lives in committed config; which directory this machine writes them to is not.

This produces a durable property: **one organizational definition → multiple runtime representations.** When a subagent's responsibility changes, the team edits the canonical source and regenerates. When a new runtime shows up, the organization adds a renderer instead of rewriting the operational model. When a generated file drifts, it's regenerated rather than manually reconciled.

**Agnostic does not mean lowest-common-denominator.** Different runtimes will keep having different capabilities and configuration formats — forcing every tool to consume an identical representation prevents teams from using those capabilities well. The actual separation is:

> **Canonical semantics → deterministic transformation → runtime-native representation.**

This isn't a new pattern. Source code compiles to multiple targets. An API schema generates clients in multiple languages. Design tokens produce platform-specific artifacts. Infrastructure-as-code produces environment-specific config. Agent architecture uses the same shape.

**Projection is general, not subagent-specific.** The same Source → Projection → Runtime pattern applies wherever EOCR knowledge needs to reach a tool-specific consumer — a Contract expressed as a canonical schema can project to a linter config, a CI check, and an agent-facing rule file without any one of those three being the authoritative copy.

The organizational layer owns meaning. Adapters own representation. Runtimes own execution.

### Projection isn't the default treatment for everything — only for genuine format gaps

It's tempting to read the subagent example above as the general pattern for every artifact a Skill ships. It isn't. Projection solves one specific problem — a runtime that cannot read an artifact's canonical format — and applies only where that problem actually exists:

> **Projection applies when a runtime consuming the knowledge cannot read its canonical format. It does not apply when an open standard already lets every relevant runtime consume the canonical file directly.**

That splits the artifact types this document covers into two groups, not one:

**Needs Projection — genuine, unresolved format divergence:**
- **Subagents** — Cursor and Codex settled on incompatible native representations; a canonical source has to compile to both. Cursor reads markdown with frontmatter, Claude Code reads markdown with a slightly different frontmatter vocabulary, and Codex reads TOML requiring `name`, `description`, and a `developer_instructions` *string*. The same prose is a document body in one runtime and a quoted scalar in another, which is about as unbridgeable as two text formats get.
- **Rules** — `.cursor/rules`, `.windsurf/rules`, `.github/copilot-instructions.md`, and `CLAUDE.md` are mutually unreadable, proprietary formats expressing substantially the same repo-level guidance. Without a canonical source and renderer, a team either hand-duplicates the same rule four times or picks one tool as authoritative and leaves the rest stale. <!-- bearing:ignore-paths: names targets this repo does not enable -->
- **Contracts** — one canonical Contract projects to a linter config, a CI check, and an agent-facing summary. None of those three is the authoritative copy.
- **Distribution manifests** — the same plugin definition has to appear under a different directory per client, plus a per-client marketplace catalog. BEARING generates every one of them from a single canonical `plugin/plugin.json`, which is the framework applying its own principle to its own distribution rather than exempting itself.

**Doesn't need Projection — the format gap has already been closed:**
- **`SKILL.md`** — Agent Skills is an open standard multiple runtimes read natively (Part VII). There's no representational gap for a renderer to bridge. The canonical file *is* the consumable artifact, full stop — writing a renderer here would be solving a problem that doesn't exist.
- **The disclosure index** — one tool-agnostic JSON file compiled from one corpus. No runtime split, so no adapter.

This is worth checking explicitly for any new artifact type this architecture takes on later, rather than assuming Projection by default: ask whether the runtimes involved already share one open format before building a canonical/adapter split for it. If they do, skip Projection — the canonical source stands alone.

**And check it with a machine, since the failure is gradual.** No single unnecessary renderer looks like a mistake; a pile of them is how a clean principle becomes machinery nobody can justify. So `bearing verify` fails a projection whose declared targets all consume one identical format, and fails outright if anything resembling a `SKILL.md` renderer appears in a Skill's `scripts/`. The rule that would otherwise decay into a paragraph people stop reading is the one most worth making executable.

### Two ways knowledge enters the graph

Everything in this document up to this point assumes an organization improves its decision system by authoring knowledge correctly going forward: a human makes a decision, it becomes EOCR knowledge, it enters the Decision Graph, it gets Anchored, it's enforced at runtime. Call that the **prospective** path.

Most real codebases also need a **retrospective** path — one that recovers decisions that already shaped the implementation but were never written down. Existing code, commit history, and tickets are mined for evidence, which produces a **Decision Shadow Graph**: candidate relationships supported by provenance, but with no authority of their own. A human validates a candidate before it ever crosses into the real Decision Graph.

```
Prospective:   Human decision → EOCR knowledge → Decision Graph → Anchor → Enforcement
Retrospective: Existing code/history → extraction/resolution → Shadow Graph
                  → human validation → EOCR knowledge → Decision Graph → Anchor → Enforcement
```

This distinction matters because it's the direct answer to the objection every real adoption of this architecture eventually runs into: *we have fifteen years of code and almost none of it has ADRs — are you saying we have to document everything before this becomes useful?* No. The retrospective path can recover decision ancestry progressively, including opportunistically alongside normal work, without requiring the backlog to be cleared first—and without ever letting what a machine inferred stand in for what the organization has actually declared authoritative. BEARING standardizes the shadow-candidate format and authority boundary, not the execution mechanism: teams may run the shipped Skill manually, schedule it with their own automation, or use a compatible extractor. Shadow candidates can be reviewed in the current change or separately; commit placement never promotes them.

---

## Part V — Skills, Roles, and Enforcement in Practice

### Skills: the execution layer

If ADRs are the "why" and annotations are the "where," Skills are the "how." A Skill is a set of guided instructions that teach an agent how to act on the Decision Graph — the bridge between *knowing* there is a migration and *executing* it correctly. A well-defined Skill encodes the unwritten rules of the team: interpretation ("when you see `@deprecated`, check the `@see` link before proposing a change"), navigation ("cross-reference the design-token doc before reinventing a utility"), and validation ("if ADR-014 is referenced, run the normalization suite before considering this done").

```
.agents/
├── commands/
│   ├── create-branch-from-ticket.md
│   └── migrate-deprecated-components.md
└── skills/
    ├── core/
    │   └── naming-conventions/SKILL.md
    ├── architecture/
    │   └── adr-navigation/
    │       ├── SKILL.md
    │       └── references/adr-status-lifecycle.md
    └── migrations/
        └── card-normalization/
            ├── SKILL.md
            ├── scripts/transform-props.py
            └── references/
                ├── legacy-code-snippet.ts
                └── adr-014-excerpt.md
```

A `SKILL.md` is a prompt-engineered instruction set, not a README:

```markdown
# Skill: Card Normalization (ADR-014)

## Context
We are migrating all legacy cards to `ui-foundation.card`. This skill ensures the
migration follows the approved mapping and doesn't silently break consumers.

## Detection Rules
- Trigger: agent modifies any file containing `@deprecated` cards.
- Anchor: look for `/// @see ADR-014` in the file header.

## Instructions for the Agent
1. Never delete a legacy card without verifying its usage in the DSYS-231 migration tracker.
2. Use the approved prop mapping: `LegacyCard.header` → `Card.Title`, `LegacyCard.footer` → `Card.Actions`.
3. After refactoring, run `npm run test:visual --component=Card`.

## Links
- Policy: ADR-014
- Execution: DSYS-231
```

### Subagents: the specialized workforce

Subagents are the specialized cells that carry out narrow, high-context functions rather than relying on one generalist agent to understand the entire repository. They are the primary *consumers* of Skills — where a human might read a Skill once and internalize it, a subagent loads it fresh for each task.

Following the Projection pattern from Part IV, subagent definitions live **inside the Skill package they serve**, as canonical source material — not in a separate tree, and not as a file every tool is expected to read identically:

```
skills/
└── migration/                    # the Skill package
    ├── README.md                 # documents the maintenance model, kept current automatically
    ├── SKILL.md                  # the "How"
    ├── subagents/                # the "Who" — canonical source, lives with its Skill
    │   ├── migration-reviewer.md
    │   └── migration-planner.md
    └── scripts/                  # the Skill's own tooling — never a subagent renderer
```

The renderer is deliberately absent here. Projection is performed by one command over every Skill, for the reasons given in Part IV; a Skill owning its own renderer duplicates the translation and puts writable tooling inside a read-only tree.

`subagents/migration-planner.md` is the canonical, hand-maintained definition:

```markdown
# Subagent: Migration Planner

## Mission
Safely migrate code from approved legacy patterns to current patterns defined
by an accepted ADR.

## Boundaries
- Do not invent new target patterns.
- Do not delete legacy code without confirming replacement coverage.
- Do not proceed when annotations, ADR links, or migration state are missing.

## Escalation Rules
Escalate to a human when:
- an annotation points to a missing ADR
- the ADR status is deprecated, superseded, or ambiguous
- the code appears load-bearing but is insufficiently documented
- more than one migration strategy appears valid

## Success Criteria
- Migration follows the linked ADR.
- No unauthorized pattern substitutions.
- Required checks run successfully.
- Decision links remain intact.
```

`bearing render` deterministically projects that single source into whatever each runtime needs — `.cursor/agents/migration-planner.md`, `.claude/agents/migration-planner.md`, and `.codex/agents/migration-planner.toml`. <!-- bearing:ignore-paths: `migration` is an illustrative Skill, not one this repo ships --> Note what survives the format change and what does not: `readonly: true` on the canonical definition becomes `sandbox_policy = "read-only"` in the Codex output, because Codex expresses tool restriction as a sandbox policy rather than a boolean. The authority boundary is preserved; its spelling is not. Fields a runtime does not recognize are dropped rather than emitted, since a generated file that produces warnings is a generated file people learn to ignore.

Neither generated file is edited by hand, and neither carries authority independent of the canonical copy. Each opens with a `DO NOT EDIT` header naming its source and the command that regenerates it, `bearing render --check` fails on drift, and `AGENTS.md` states the rule directly so an agent reading a generated file knows it is reading an adapter.

This works because it never asks any tool to understand a shared file format — it asks every tool to understand its own native format, generated deterministically from one canonical place.

### Supporting documents and what belongs in each

| Document | Job | What it should NOT become |
|---|---|---|
| `README.md` | Map of intent — Entry, points to the ADR index | An exhaustive manual |
| `CONTRIBUTING.md` | Operational Contract — the "Definition of Done" for the Decision Graph (code + linked ADR + updated Skill + passing linter) | A style guide with no enforcement teeth |
| `PULL_REQUEST_TEMPLATE.md` | Quality gate — a Decision Integrity checklist a reviewer subagent can pre-check | A generic checkbox list disconnected from the graph |
| `AGENTS.md` | The constitution — sandbox boundaries and escalation paths for any agent entering the repo | A dumping ground for every rule that should live in a Contract instead |

A useful concrete rule for `AGENTS.md`: *"If you encounter a `@deprecated` tag without a `@see` link, you are forbidden from refactoring. Open a 'Clarification Required' issue for a human architect."* That single sentence is what turns escalation from an aspiration into a binding instruction an agent will actually follow.

### Worked example: fixing the cyclomatic-complexity gap

Returning to Part I's failure, here is what closing it looks like using this framework end-to-end.

**1. Contract.** The complexity ceiling is written down as an explicit Contract, not implied by a linter config: *"Cyclomatic complexity per method MUST NOT exceed 10 without an accompanying `@see ADR-XXX` justification."* This lives somewhere retrievable — ideally summarized directly in `AGENTS.md` under a `Code Quality Contracts` heading, with a link to the full policy.

**2. Anchor.** Any method that is legitimately complex and intentionally so — a load-bearing state machine, a compatibility shim — gets an annotation explaining why, not just a suppressed warning:

```java
/**
 * @remarks Complexity intentionally exceeds the standard ceiling. This method
 * consolidates three legacy validation paths pending ADR-031's migration.
 * Do not simplify without confirming path coverage.
 * @see ADR-031
 */
```

**3. Skill.** A `code-quality/complexity-review/SKILL.md` gives any agent editing Java the instruction it needs *before* writing: check current complexity, know the ceiling, know what to do if the ceiling would be crossed (refactor first, or flag and escalate — not silently proceed).

**4. Enforcement.** The linter stays exactly as it is — it's the last line of defense, not the first. What changes is that it's no longer the *only* line of defense.

**5. Escalation.** If an agent's change would cross the ceiling and no ADR justifies it, the Role or Skill instructs it to stop and open a clarification request rather than push a change that will only be caught in review.

The point is not that any single piece here is novel — teams already have linters. The point is that **the same Contract now exists at three points in the pipeline instead of one**, and the earliest of those points is the one that actually prevents the rework this framework exists to eliminate.

---

## Part VI — Distribution and boundaries, stated as Contracts

Everything above describes what the system knows. This part describes where the machinery lives, what it may write, and how a repository configures it — held as Contracts rather than conventions, because each one is a boundary that erodes quietly when it is only documented.

### The distribution layer is separate from the pipeline

Install is not a step in any workflow. It is a precondition satisfied by a different layer, and conflating the two is what produces a Skill that tries to install itself:

| Layer | Owns | Answers |
|---|---|---|
| Distribution | Marketplace, `plugin.json`, per-client manifests | How does the machinery get onto this machine? |
| Bootstrap | `bearing init`, `bearing doctor` | How does *this* repository start using it? |
| Operation | The Skills — recovery, interview, onboarding | How is the work performed? |

BEARING ships as one plugin rather than three, because the three Skills share a schema, a ledger, a config layer, and a renderer. Splitting them would mean either duplicating that substrate in each package or inventing a cross-plugin dependency mechanism the standard does not offer. Onboarding checks the core installation and bootstrap facts it needs, then offers an adaptable evaluation guide. Teams selecting a controlled branch-versus-baseline pilot can run the stricter `bearing preflight`, including its clean-tree check; that rigor is optional rather than a universal adoption ceremony.

**Contract — the plugin tree is read-only at runtime.** Nothing BEARING writes may land inside its own installation. Plugin directories are replaced wholesale on update, so a ledger, a transcript, or an evaluation result stored beside a Skill is data with a deletion date nobody chose. Writes go to `.bearing/` for run state and operator data, or to the decisions directory for decision content. This is the reason the cost ledger lives at `.bearing/ledger/cost.jsonl` and interview transcripts live under `<decisions.path>/shadow/transcripts/` — a transcript is evidence, so it belongs with the shadow graph it justifies and inherits *nothing here is authoritative*.

The rule is enforced, not asserted: the packaging suite runs a full cycle with the plugin tree mounted read-only and compares a content digest of the tree before and after. A write inside the plugin fails the build rather than surfacing as lost data months later.

**Contract — a path may not escape the plugin root.** Agent Plugins v1.0.0 §4.1.3 requires a conforming client to reject any package path resolving outside the resolved plugin root, and both Cursor and Claude Code copy a plugin into a versioned cache where a `../` reference simply has nothing to point at. So a Skill needing another Skill's schema asks the CLI — `bearing schema candidate` — which resolves from the plugin root and therefore works identically whether BEARING was installed from a marketplace, vendored, or run from a checkout.

### Configuration: one key, and a rule about who wins

Everything derives from `decisions.path`. No script hardcodes a decisions directory, which is what allows a repository that already uses `docs/adr/` to adopt BEARING without renaming anything.

Config resolves through five layers — packaged defaults, then user, repo, and local files, then environment and flags — and the interesting question is not the order but *what kind of fact* each key holds:

- A **repo fact** describes the repository, so the repository wins. Where decisions live, what may block a merge, which runtimes the team supports, whether transcripts are committed. One developer's machine does not get to disagree.
- An **operator fact** describes one person or one runner, so the user wins. Which model fills a role, that person's hourly rate, where their generated adapters go.

Getting this backwards is the failure mode: if a repo config could pin a model, a repository would dictate spending on machines it does not pay for; if a user config could redefine `decisions.path`, one clone would write its records somewhere no other clone reads. `bearing init` therefore refuses to write resolved operator facts into repo config, and a repo fact overridden locally is reported every time, because that is a machine deliberately behaving unlike every other clone.

### Projection scope is the operator's choice

A rendered adapter can go in three places, and which one is correct depends on facts BEARING cannot see:

- **`repo`** — committed to the working tree. Right for a team standardizing on one runtime, and the only workable answer on a CI runner, which has no user-level agent directories and should not create any.
- **`user`** — written under the operator's own configuration directory. Right when three developers use three different runtimes and none of them wants the other two's adapters in the diff.
- **`ephemeral`** — generated into a temporary directory, handed to the runtime for one session, never written to the repository at all.

What does not vary is the accounting. Every generated file opens with a `DO NOT EDIT` header naming its canonical source and the command that regenerates it; every one is recorded in `projections.lock.json` with a content hash; and every *deliberate* absence is recorded there too, with its reason. That last part matters more than it looks: absence has to be distinguishable from breakage, or a renderer that silently stopped emitting a target looks exactly like a target somebody turned off on purpose.

---

## Part VII — Why now: the ecosystem has caught up

This architecture isn't a bet on a hypothetical future. The primitives it depends on already exist, independently, across the industry — which is a sign this is closer to convergence than invention.

Persistent, repository-committed project context (rather than reconstructing intent from chat every session), portable Agent Skills built on an open standard, agent lifecycle hooks that let policy execute *inside* the generation loop rather than after it, automated review that checks implementation against intent rather than just style, and MCP-standardized access to the organization's knowledge outside the repository — issue trackers, design systems, incident history — are all becoming standard rather than experimental.

What remains comparatively immature, industry-wide, is the *architecture connecting them.* Access to a knowledge source is not the same as knowing which piece of it governs the file currently being edited. Connectivity is not topology. That is exactly the gap this document is written to close for this organization specifically — not by inventing new tooling, but by giving the tooling that already exists a coherent place to plug into.

---

## Part VIII — Quick Reference

**The four knowledge functions:**
- **Entry** — how do I safely begin?
- **Operations** — how is this work done?
- **Contracts** — what is true, required, permitted, forbidden?
- **Rationale** — why is it this way?

**The Decision-System behaviors:**
`Discover → Anchor → Constrain → Execute → Verify → Evolve`

**The escalation instinct, stated once, meant everywhere:** an agent that finds a decision missing, ambiguous, or superseded does not guess. It follows the successor decision if one exists, or it stops and asks a human. This is true whether the missing link is an ADR, a Role boundary, or a Contract that was never surfaced before generation.

**The organizing principle for tool independence:** standardize the organizational source; project it deterministically into whatever representation each runtime needs. Never require every tool to read the same file. Never let a generated file become a second source of truth.

**Where to look for things:**

| If you need to know... | Look at... |
|---|---|
| Why this code looks the way it does | The linked ADR (`@see`) |
| What's safe to change right now | The nearest Contract + its lifecycle state |
| How to actually perform a task | The relevant Skill |
| Who's authorized to do it autonomously | The relevant Role definition |
| Whether a rule is real or aspirational | Its position on the documented → verifiable ladder |
| What to do when something doesn't add up | `AGENTS.md` escalation rules — stop, don't guess |

---

*This document is itself Rationale plus Contract: it explains why the system is shaped this way, and it establishes what humans and agents are expected to do inside it. Treat updates to it the same way you'd treat updates to any other Contract — propose the change, link the reasoning, and let it evolve on the record rather than in Slack.*
