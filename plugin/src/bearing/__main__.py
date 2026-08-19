"""Entry point for `python -m bearing`.

Also makes `python plugin/src/bearing/__main__.py <command>` work from a checkout
without installing anything, which is how the test suite and CI invoke the CLI.
"""

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bearing.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
