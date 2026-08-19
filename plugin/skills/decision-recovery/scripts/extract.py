#!/usr/bin/env python3
"""
Stage 1: EXTRACT (Haiku-tier, bulk, recall-oriented)

Scans the scoped corpus (commits, PR descriptions, code comments, tickets)
once per corpus version. For each code symbol with no existing @see
annotation, extracts candidate evidence tagged with its EOCR function.

Contract: MUST use the cheap model tier. Runs once per item per corpus
version — never re-invokes itself, never treats a prior run's output as
new evidence.

Output: appends raw evidence records (pre-resolution) for resolve.py to
cluster. Does NOT write to docs/decisions/shadow/candidates.jsonl directly
— that happens after resolve.py and score.py.

TODO: implement corpus scanning (git log, PR API, ticket API as configured)
TODO: implement the structured-output extraction prompt per EOCR function
TODO: wire idempotency check against existing candidates before extracting
      a symbol already covered by an unchanged evidence base
"""

def main():
    raise NotImplementedError(
        "Wire this to your corpus sources and model client. "
        "See ../SKILL.md for the extraction contract this must satisfy."
    )

if __name__ == "__main__":
    main()
