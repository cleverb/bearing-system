"""Copy marketplace-root files into the installed `bearing` package.

`plugin.json` and `skills/` live beside `src/bearing` so a marketplace client
can copy the plugin directory. A `pip` / `pipx` / `uv tool` install only
places the Python package on site-packages, so those files have to be copied
*into* `bearing/` at build time or `plugin_root()` cannot find them.

This module is not part of the importable `bearing` package. `setup.py` and
the packaging tests load it from the plugin directory.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# Marketplace-root paths that must exist inside the installed `bearing` package
# so `plugin_root()` / `bearing doctor` resolve after a pip-style install.
BUNDLE_FROM_PLUGIN_ROOT = (
    "plugin.json",
    "runtime-compatibility.json",
    "skills",
    "bin",
)


def bundle_plugin_root(destination: str, plugin_dir: Optional[str] = None) -> None:
    """Place bundled plugin-root files inside an installed `bearing` directory."""
    source_root = plugin_dir or PLUGIN_DIR
    os.makedirs(destination, exist_ok=True)
    for name in BUNDLE_FROM_PLUGIN_ROOT:
        source = os.path.join(source_root, name)
        target = os.path.join(destination, name)
        if not os.path.exists(source):
            raise FileNotFoundError(
                "cannot bundle %s: %s is missing from the plugin root" % (name, source)
            )
        if os.path.isdir(source):
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(
                source,
                target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
            )
        else:
            shutil.copy2(source, target)
