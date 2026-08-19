# decision-interview

Live counterpart to decision-recovery. Structured, synchronous elicitation
from a human when an agent hits real ambiguity mid-task, or on direct
human request.

Shares decision-recovery's schema and shadow graph — see
../decision-recovery/schemas/. Writes to the same
docs/decisions/shadow/candidates.jsonl, tagged evidence_source:
live_interview. No separate schema directory here by design.

Full spec: see SKILL.md in this directory, and the extended rationale in
the project's decision-interview-skill-spec.md.
