# BEARING Quickstart

*Orientation, not a closed loop. Reading this and running `bearing init` takes a short sitting. A measured onboarding pilot — recovery, interviews, promoted anchors, paired tickets — takes reviewer sessions, not thirty minutes. See `BEARING.md` for the complete architecture.*

---

## The four categories, in one paragraph

Every piece of engineering knowledge is doing one of four jobs: **Entry** helps you get oriented, **Operations** describes how work gets done, **Contracts** state what's required or forbidden, **Rationale** explains why. You don't need to memorize this to start — you'll see it in action in about five minutes.

## What you're about to do

You're going to bootstrap BEARING and then run `bearing onboard`, which gates the `decision-onboarding` Skill. The CLI records state and checks preconditions; the Skill (an agent, with you reviewing) carries out the six steps. By the end of a completed pilot you'll have one branch containing a small amount of real, promoted decision knowledge, and a measured comparison showing whether it actually helped.

## Before you start

- Pick a repository with real history — legacy is fine, encouraged even.
- Pick a scope inside it: one directory or one service, not the whole thing.
- Have one or two people in mind who'd know the most about that scope if you had a question.

## Run it

```
bearing assessment    # optional: score current decision readiness (works without init; always exits 0)
bearing init          # detect the decisions directory, scaffold .bearing/ and docs/decisions/
bearing doctor        # confirm the plugin, CLI, and config resolve
bearing onboard       # Step 0a preflight, then load the decision-onboarding Skill
```

`bearing onboard` does not itself mine git or promote ADRs. It gates the pipeline and records run state (gitignored). The Skill then runs six steps, in order, on a branch — nothing touches `main` directly:

1. **Freeze** — tags the current commit as the baseline, so later comparisons are against a fixed point, not a moving target.
2. **Scaffold** — creates `docs/decisions/`, the `.agents/` tree, and an `AGENTS.md` stub. No content yet, just structure.
3. **Scoped recovery** — mines commits, PRs, and comments in your chosen scope for evidence of undocumented decisions. Produces candidates, not decisions — nothing here is authoritative yet.
4. **Seed interviews** — a short conversation with the people you picked, structured around specific ambiguous points the recovery pass surfaced.
5. **First anchors** — a small, deliberate set of candidates (3 to 5) get promoted: real ADRs, real annotations in the code, entries in the decision index.
6. **Pilot** — a handful of real tickets run twice, once against the frozen baseline, once against the onboarded branch, measuring rework, Contract violations, and token cost side by side.

You'll be asked to review and confirm at steps 4 and 5. Nothing is written to `docs/decisions/` without you looking at it first.

## What "day one" actually looks like

After handoff, this is what changes about how you work:

- **When you touch code with a `@see ADR-XXX` annotation**, you (or an agent working on your behalf) now have a one-line pointer to why it's built that way, not just what it does.
- **When an agent is about to touch something in the onboarded scope**, it loads a short index first — cheap, a few KB — that tells it which Contracts and Rationale are relevant before it writes anything, not after.
- **When something is genuinely ambiguous and undocumented**, the expected move — for a human or an agent — is to stop and ask, not guess. `decision-interview` is that "ask" made structured: a real conversation, pressure-tested with a deletion test (*if we removed this constraint, what would actually break?*), routed into the same review process as everything else.
- **Recovery keeps running on a schedule**, quietly, in the background, on whatever scope you point it at next. You'll see a small queue of candidates periodically — most will be low-confidence and stay out of your way; the ones worth your time will say so.
- **Nothing an agent infers becomes a rule on its own.** A recovery signal can flag a change that looks like it lacks decision history. It can never block a merge on its own. Only a real, authored Contract can do that.

That's the whole day-to-day shape of it: annotations that actually mean something when you hover over them, agents that ask instead of guess when it matters, and a small, growing set of decisions that stay true because someone checks, not because a model was confident.

## Where to go next

- Full architecture and reasoning: `BEARING.md`
- How recovery and interview actually work: `decision-recovery-skill-spec.md`, `decision-interview-skill-spec.md`
- The onboarding procedure in full: `decision-onboarding-skill-spec.md`
