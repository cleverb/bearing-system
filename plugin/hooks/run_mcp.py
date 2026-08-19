#!/usr/bin/env python3
"""Launch the BEARING MCP disposition server from the plugin tree.

Used by plugin/mcp.json so marketplace install surfaces MCP without requiring
`bearing-mcp` on PATH. Enables the operator-scope CLI shim on start.
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SRC = os.path.join(PLUGIN_ROOT, "src")


def _enable() -> None:
    sys.path.insert(0, SRC)
    from bearing.enable import ensure_enabled

    ensure_enabled(PLUGIN_ROOT, sys.executable)


def main() -> int:
    _enable()
    launcher = os.path.join(PLUGIN_ROOT, "bin", "bearing-mcp")
    return subprocess.call(
        [sys.executable, launcher] + sys.argv[1:],
        cwd=PLUGIN_ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
