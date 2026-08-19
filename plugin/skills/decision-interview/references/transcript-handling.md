# Interview transcripts: location, retention, and standing

Transcripts do **not** live in this directory. They live in the workspace at `<decisions.path>/shadow/<transcripts_dir>/`, alongside the shadow graph they justify. Resolve the path with `bearing transcripts`.

## Why they sit with the shadow graph

A transcript is evidence. It belongs with the other evidence, one directory below the authored decision records, where it inherits the shadow graph's standing for free: *nothing in this folder is authoritative.* A transcript is supporting record for how a candidate was obtained — the structured candidate in `candidates.jsonl` is the output, and the transcript is the provenance behind it.

The two placements that were rejected:

- **Inside this Skill** (`references/interview-transcripts/`) — plugin directories are replaced on update, so every upgrade would destroy the audit trail. It also puts repository-specific content inside generic tooling, which is what keeps a Skill from being cleanly versionable.
- **In `.bearing/`** — that directory holds state about *runs*. Reclassifying testimony as run state makes it natural to gitignore, and a transcript that is not in version control cannot serve as the audit record a promoted Contract may later need.

## Retention is a policy decision, not a default

Set `interview.transcripts.retention` in `.bearing/config.json`:

- **`committed`** (default) — transcripts are tracked in git as durable audit evidence.
- **`local`** — transcripts are written to a gitignored `local/` subdirectory. For organizations that will not commit a named person's testimony to version control. The candidate still records that a transcript existed and its identifier, so the audit trail shows a gap deliberately rather than looking like nothing happened.
- **`none`** — the transcript is discarded once the candidate is written. The candidate's evidence excerpt is all that survives.

Ask before the first interview, not after. Under `none` and `local`, a promoted Contract's full provenance is not reconstructible from the repository alone, and whoever relies on that Contract later should know that.

## What a transcript must record

Enough to reconstruct the judgment, and no more than the interviewee agreed to:

- The triggering question — the actual ambiguity that caused the escalation. This becomes the disclosure-index trigger phrase on promotion, because it is definitionally the most accurate description of when the decision matters.
- The deletion-test question and its answer, verbatim. If the answer named no specific consequence, the transcript must show that, since it is the basis for capping the candidate at Rationale rather than Contract.
- The authority-check question and its answer, which sets `organizational_authority` on the evidence entry.
- Any conflict surfaced against an existing accepted Contract, and how the interviewee responded.
- `interview_duration_minutes`, measured rather than estimated.

## Naming

`<candidate_id>.md` — one transcript per candidate, so the reference from `candidates.jsonl` is unambiguous. The candidate carries `evidence[].transcript_ref` as a workspace-relative path.
