#!/usr/bin/env python3
"""
Regenerates docs/decisions/index.json on promotion.

Called after a candidate reaches lifecycle state Promoted. Adds an index
entry using the interview's own triggering question as the trigger phrase
(the most accurate available summary of when this decision matters, since
it's the actual situation that required it).

Contracts are indexed for near-always visibility. Rationale stays fully
lazy — pulled only when an Anchor fires or a trigger phrase matches.

TODO: implement index regeneration from docs/decisions/*.md front matter
      plus this promotion's new entry
TODO: never hand-edit index.json directly — this script is the only writer
"""

def main():
    raise NotImplementedError("See ../SKILL.md, pipeline step 7.")

if __name__ == "__main__":
    main()
