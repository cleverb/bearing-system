# Interview transcripts — nothing in this folder is authoritative

Transcripts of `decision-interview` sessions, retained as audit evidence for the candidates in `../candidates.jsonl`.

A transcript is not a decision, and it is not even the candidate. It is the record of *how* a candidate was obtained: what was asked, what was answered, whether the deletion test produced a defensible consequence, and whether the person answering said they had standing to make the call. The structured candidate one directory up is the output; this is its provenance.

These files inherit the shadow graph's standing — see `../README.md`. No `@see` annotation may point here, and that is checked by lint rather than merely asked for.

## Naming

`<candidate_id>.md`, one transcript per candidate, so the reference from `candidates.jsonl` is unambiguous.

## Retention

Governed by `interview.transcripts.retention` in `.bearing/config.json`. This repository uses the default, `committed`: transcripts are tracked in git.

Under `local` retention they are written to `local/` here and gitignored, for organizations that will not commit a named person's testimony. Under `none` they are discarded once the candidate is written. In both of those cases a promoted Contract's full provenance is not reconstructible from the repository alone, which is a real tradeoff to make deliberately rather than discover later.

Format and required contents: `plugin/skills/decision-interview/references/transcript-handling.md`.
