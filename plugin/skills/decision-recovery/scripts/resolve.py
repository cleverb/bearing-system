#!/usr/bin/env python3
"""
Stage 2: RESOLVE (Sonnet-tier, candidates only)

Clusters raw evidence from extract.py that appears to refer to the same
underlying decision. Conflicting evidence is NOT reconciled into one
confident answer — emit a "conflicting evidence" candidate with all
sources attached, confidence capped at LOW.

Before emitting any candidate, checks docs/decisions/shadow/rejected.jsonl.
If a new cluster's evidence substantially overlaps a rejected fingerprint,
suppress by default (log, don't surface) unless the new evidence isn't
covered by the existing fingerprint.

TODO: implement clustering (entity/relation resolution across evidence)
TODO: implement conflict detection — do not let the model silently pick
      a side when two sources disagree
TODO: implement rejected.jsonl fingerprint comparison
"""

def main():
    raise NotImplementedError("See ../SKILL.md, pipeline step 2.")

if __name__ == "__main__":
    main()
