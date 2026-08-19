#!/usr/bin/env python3
"""
Step 5: runs the selected test tickets twice each (once against the
frozen baseline tag, once against the onboarding branch) and computes,
per run: token consumption, rework rate, Contract-violation rate,
escalation correctness.

Reads the pass/fail bar from references/pass-fail-criteria.md — this
file MUST already exist before this script runs; it is not generated
here, to enforce that the bar was set before results were seen.

Never emits a token-consumption number without a paired outcome metric
alongside it in the same report.

TODO: implement ticket runner (dispatches the same ticket against both
      conditions)
TODO: implement rework / Contract-violation / escalation-correctness
      scoring — likely requires a human-in-the-loop rubric, not pure
      automation
TODO: implement the pass/fail comparison against
      references/pass-fail-criteria.md
"""

def main():
    raise NotImplementedError("See ../SKILL.md, Step 5.")

if __name__ == "__main__":
    main()
