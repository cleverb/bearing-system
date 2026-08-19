#!/usr/bin/env python3
"""
Stage 3: SCORE (Sonnet-tier)

Computes all five evidence axes per source (reliability, organizational
authority, corroboration, specificity, temporal relevance) and a collapsed
top-line confidence for the review queue. The full breakdown is always
stored, regardless of whether it's surfaced by default — it's forced open
automatically when a candidate is contested or conflicts with an accepted
Contract.

TODO: implement per-axis scoring — do not collapse these into a single
      LLM-produced confidence number without preserving the breakdown
TODO: implement the collapse-to-top-line logic for the default queue view
"""

def main():
    raise NotImplementedError("See ../SKILL.md, pipeline step 3.")

if __name__ == "__main__":
    main()
