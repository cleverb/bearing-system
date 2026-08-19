#!/usr/bin/env python3
"""workspaceOpen hook: ephemeral render without requiring `bearing` on PATH.

Walks to the plugin root from this file (hooks live one directory below
plugin.json) and runs `python3 -m bearing`. Falls back to a `bearing`
executable if one is already on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SRC = os.path.join(PLUGIN_ROOT, "src")
ARGS = ["render", "--ephemeral", "--emit-plugin-paths"]


def main() -> int:
    bearing = shutil.which("bearing")
    if bearing:
        return subprocess.call([bearing] + ARGS)
    env = os.environ.copy()
    env["PYTHONPATH"] = SRC + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.call([sys.executable, "-m", "bearing"] + ARGS, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
