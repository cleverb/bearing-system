#!/usr/bin/env python3
"""
Step 0: tags the current commit as the frozen baseline before onboarding
begins, and creates the onboarding branch.

    git tag bearing-baseline-<repo>-<date>
    git checkout -b bearing-onboarding/<repo>

Every comparison in evaluate-pilot.py runs against this tag, not whatever
main happens to be on the day a given test ticket runs.

TODO: implement tag naming (repo name, date) and git operations
TODO: fail loudly if a bearing-baseline-* tag already exists for this
      repo/date combination rather than silently overwriting
"""

def main():
    raise NotImplementedError("See ../SKILL.md, Step 0.")

if __name__ == "__main__":
    main()
