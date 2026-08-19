#!/usr/bin/env python3
"""Enable the BEARING terminal CLI after a plugin install.

Does not require `bearing` on PATH or pipx. Run from the plugin directory:

  python3 enable.py

From a bearing-system clone:

  python3 plugin/enable.py

To target a Cursor/Claude marketplace copy (after GUI plugin install):

  python3 plugin/enable.py --discover

Do not use a bare path like ~/plugin/enable.py unless that directory is a real
BEARING plugin tree. From this repository, prefer the clone path above.
"""

from __future__ import annotations

import argparse
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "src"))

from bearing.enable import (  # noqa: E402
    discover_plugin_roots,
    ensure_enabled,
    resolve_enable_plugin_root,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write ~/.bearing/bin CLI shims.")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="find the newest complete BEARING plugin under ~/.cursor/plugins or ~/.claude/plugins",
    )
    parser.add_argument(
        "--plugin-root",
        default=None,
        help="explicit plugin directory containing plugin.json (overrides --discover)",
    )
    args = parser.parse_args(argv)

    root = resolve_enable_plugin_root(
        explicit=args.plugin_root,
        discover=args.discover,
        start=PLUGIN_ROOT,
    )
    if not root:
        print(
            "bearing enable: no complete BEARING plugin tree found.\n"
            "A usable tree needs plugin.json, skills/, and bin/bearing.\n"
            "From a bearing-system clone (recommended):\n"
            "  python3 plugin/enable.py\n"
            "After a marketplace install that includes bin/:\n"
            "  python3 plugin/enable.py --discover\n"
            "Or set BEARING_PLUGIN_ROOT to an explicit plugin directory.",
            file=sys.stderr,
        )
        if args.discover:
            print("Searched:", file=sys.stderr)
            for base in (
                os.path.expanduser("~/.cursor/plugins"),
                os.path.expanduser("~/.claude/plugins"),
            ):
                print("  %s" % base, file=sys.stderr)
        return 1

    outcome = ensure_enabled(root, sys.executable)
    if not outcome.get("ok"):
        for message in outcome.get("errors") or []:
            print(message, file=sys.stderr)
        return 1

    print("OK: CLI enabled from %s" % root)
    print("  %s" % outcome.get("bin_dir"))
    print('Add once: export PATH="%s:$PATH"' % outcome.get("bin_dir"))
    if args.discover and len(discover_plugin_roots()) > 1:
        print("Note: multiple installs found; used the newest complete plugin.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
