#!/usr/bin/env python3
"""workspaceOpen hook: ephemeral render without requiring `bearing` on PATH.

Walks to the plugin root from this file (hooks live one directory below
plugin.json), enables the operator-scope CLI shim, then runs `bearing render`.
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SRC = os.path.join(PLUGIN_ROOT, "src")
ARGS = ["render", "--ephemeral", "--emit-plugin-paths"]


def _enable() -> None:
    sys.path.insert(0, SRC)
    from bearing.enable import ensure_enabled

    ensure_enabled(PLUGIN_ROOT, sys.executable)


def main() -> int:
    _enable()
    launcher = os.path.join(PLUGIN_ROOT, "bin", "bearing")
    return subprocess.call([sys.executable, launcher] + ARGS)


if __name__ == "__main__":
    raise SystemExit(main())
