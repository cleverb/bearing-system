---
name: decision-recovery
description: Recover evidence of undocumented architectural decisions from commit history, PR descriptions, tickets, and code comments into reviewable shadow candidates. Use for a manual or scheduled audit, or opportunistically when ordinary work exposes missing decision ancestry. Never writes to the authored decision record directly.
metadata:
  bearing-role: retrospective-acquisition
  writes-to: shadow-graph
---

# Skill: Decision Recovery

## Purpose

Surface evidence that may help a human recover undocumented decisions. This
Skill does not assert that a decision was made, promote candidates, add code
annotations, or prescribe how often recovery runs.

## Invocation

Recovery is operator-controlled. Use whichever mode fits the repository:

- opportunistically, when ordinary work exposes useful evidence;
- as an explicit, bounded manual pass;
- from operator-owned automation such as GitHub Actions or cron; or
- through a custom extractor that emits the same candidate format.

The procedure in `references/agent-procedure.md` is the shipped reference
workflow, not a required scheduler or system architecture. Never make recovery
a live PR gate.

## Reference workflow

When this Skill is asked to perform a recovery pass:

1. Bound the corpus to the area and evidence relevant to the request.
2. Extract evidence without inventing intent. Tag the possible EOCR function.
3. Cluster evidence that appears to concern the same decision. Preserve
   conflicts instead of choosing a side.
4. Record confidence and its evidence basis. Confidence is about evidence,
   never organizational authority.
5. Write schema-valid candidates to the configured shadow graph and run
   `bearing lint`.

Detailed scoring, cost logging, idempotency, evaluation sets, and budget limits
are available when an operator wants a repeatable batch. They are optional
operational controls, not prerequisites for surfacing a useful candidate.

## Candidate disposition

Shadow candidates are non-authoritative repository content. The operator may:

- review and commit a candidate alongside the work that exposed it;
- put it in a separate focused commit or change for easier review; or
- keep it as a short-lived local change while finishing an interruption.

Do not use a stash as durable storage, and never imply that committing a shadow
candidate promotes it. Promotion remains a separate human judgment about scope,
validity, lifecycle state, and authority.

## Hard boundaries

- Never write directly to `docs/decisions/` outside `shadow/`, add an `@see`
  annotation, or claim a decision "was made."
- Never turn confidence into organizational authority.
- Never resolve conflicting evidence by silently selecting one account.
- Never let a recovery signal block a merge. Only structural enforcement or a
  known accepted Contract may block.
- Check prior rejected candidates before repeatedly surfacing substantially the
  same evidence.

## Useful output

A useful candidate is schema-valid, identifies its sources and uncertainty, and
gives a reviewer enough context to decide whether to reject, revise, defer, or
promote it. Completeness, a fixed candidate count, and a particular run cadence
are not success criteria.
