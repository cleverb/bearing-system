"""Build helpers. Project metadata lives in pyproject.toml.

A setuptools install of this directory only copies `src/bearing` onto
site-packages. `plugin.json` and `skills/` sit beside that package so a
marketplace client can copy the plugin tree; `build_py` copies them into the
installed package so `plugin_root()` still resolves after `pipx install` /
`uv tool install`.
"""

from __future__ import annotations

import os
import sys

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


def _plugin_dir():
    # PEP 517 execs setup.py as a string; __file__ is often "<string>".
    # setuptools sets sys.argv[0] to the real setup.py path.
    if "__file__" in globals():
        path = os.path.abspath(__file__)
        if os.path.isfile(path):
            return os.path.dirname(path)
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0 and os.path.isfile(os.path.abspath(argv0)):
        return os.path.dirname(os.path.abspath(argv0))
    return os.getcwd()


sys.path.insert(0, _plugin_dir())
from wheel_bundle import bundle_plugin_root  # noqa: E402


class build_py(_build_py):
    def run(self):
        super().run()
        bundle_plugin_root(os.path.join(self.build_lib, "bearing"))


setup(cmdclass={"build_py": build_py})
