# BEARING Quickstart

*Get oriented, bootstrap safely, and choose how much evaluation is useful. This
is not a promise that adoption or a meaningful pilot fits into a fixed amount of
time.*

If BEARING is not installed on this machine yet, start with [`SETUP.md`](SETUP.md).

## The model in one paragraph

Engineering knowledge serves one of four functions: **Entry** helps people get
oriented, **Operations** describes how work gets done, **Contracts** state what
is required or forbidden, and **Rationale** explains why. BEARING makes that
knowledge discoverable to humans and agents while keeping inferred history in a
separate, non-authoritative shadow graph.

## Bootstrap

Choose a repository where decision context could improve real work, then run:

```bash
bearing assessment    # optional, informational readiness snapshot
bearing init          # detect the decision-record convention and scaffold state
bearing doctor        # confirm paths, plugin discovery, and configuration
bearing health        # aggregate existing checks and descriptive counts
```

Assessment uses declared static detectors for Java, JS/TS, Python, and Rust.
Unsupported ecosystems are explicitly `not-assessed`; configuration evidence is
surfaced for review and never promoted into decisions automatically.

You can stop here and use BEARING as decisions arise. There is no requirement to
recover the repository's history before the system becomes useful.

## Clear the shadow review queue

When `decision-recovery` or `decision-interview` leaves Reviewable candidates:

```bash
bearing review --json
bearing dispose --id CAND-… --action Promote \
  --still-valid 1 --eocr Contract --scope 'src/**' --status Accepted
```

Or enable Cursor MCP (`bearing-mcp` — see [`SETUP.md`](SETUP.md)). Promote
requires human judgment fields; confidence alone never promotes.

## Choose an evaluation path

`bearing onboard` checks core readiness and loads guidance for an optional trial.
The Skill offers a menu, not a mandatory sequence:

- **Orientation:** inspect the decision index and try `bearing context <path>`.
- **Ordinary work:** use BEARING on a real change and note where it helps or gets
  in the way.
- **Recovery audit:** surface shadow candidates in one useful area without
  promoting them.
- **Comparative pilot:** if stronger evidence is worth the effort, use a frozen
  baseline, pre-declared criteria, and paired work samples.

Branches, baseline tags, interviews, fixed candidate counts, and paired ticket
runs are optional. Confirm any git workflow before applying it.

## Recovery in normal work

When code has no Anchor and history contains useful clues, you may run the
`decision-recovery` Skill opportunistically. A resulting shadow candidate can be
reviewed and committed with the current change or separated into a focused
commit. A stash is only short-lived interruption management.

None of those choices promotes the candidate. It remains evidence until a human
reviews its scope, validity, lifecycle state, and authority.

Teams that want recurring recovery can invoke the same workflow manually,
schedule it with GitHub Actions or cron, or build a compatible extractor.
BEARING does not ship or require a cadence.

## What changes day to day

- An `@see ADR-XXX` Anchor points from implementation to authored intent.
- Agents discover decisions through `Index → Resolve → Inject`: they load the
  compact index and receive the Accepted Contracts relevant to current files.
- Genuine architectural ambiguity is escalated instead of guessed through.
- Recovery signals may flag work for review, but never block a merge.

## Next references

- First-run install: [`SETUP.md`](SETUP.md)
- Architecture and reasoning: [`BEARING.md`](BEARING.md)
- Recovery boundary and options: [`decision-recovery-skill-spec.md`](docs/specs/decision-recovery-skill-spec.md)
- Optional onboarding approaches: [`decision-onboarding-skill-spec.md`](docs/specs/decision-onboarding-skill-spec.md)
