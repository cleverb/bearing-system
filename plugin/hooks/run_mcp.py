#!/usr/bin/env python3
"""Launch the BEARING MCP disposition server from the plugin tree.

Used by plugin/mcp.json so marketplace install surfaces MCP without requiring
`bearing-mcp` on PATH. Enables the operator-scope CLI shim on start, then
runs the server in this process (no second interpreter on the stdio pipe).
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SRC = os.path.join(PLUGIN_ROOT, "src")


def _enable() -> None:
    sys.path.insert(0, SRC)
    from bearing.enable import ensure_enabled

    ensure_enabled(PLUGIN_ROOT, sys.executable)


def main() -> int:
    try:
        _enable()
    except Exception as exc:
        sys.stderr.write("bearing-mcp: enable skipped: %s\n" % exc)
        sys.stderr.flush()
        if SRC not in sys.path:
            sys.path.insert(0, SRC)

    os.environ["PYTHONUNBUFFERED"] = "1"
    from bearing.mcp_server import main as mcp_main

    return mcp_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
