"""Shared test setup: import `bearing` from the checkout without installing it.

Deliberately no `conftest.py` and no pytest. The suite runs under stdlib
`unittest` so it works in any environment with Python 3.9 and no packages
installed -- the same constraint the CLI itself is held to, for the same reason.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_ROOT = os.path.join(REPO_ROOT, "plugin")
SRC_ROOT = os.path.join(PLUGIN_ROOT, "src")

if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)


def clean_environment():
    """A copy of the environment with every `BEARING_*` override removed.

    The env layer outranks every config file, so a developer or CI runner that
    happens to have `BEARING_PROJECTIONS_SUBAGENTS_SCOPE` exported would silently
    change what these tests are asserting about precedence. Tests that want an env
    override pass it explicitly.
    """
    return {
        key: value for key, value in os.environ.items() if not key.startswith("BEARING_")
    }


def run_cli(args, workspace=None, env=None):
    """Invoke the CLI in a subprocess, as a user actually would."""
    environment = clean_environment()
    environment["PYTHONPATH"] = SRC_ROOT
    environment.setdefault("NO_COLOR", "1")
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, "-m", "bearing"] + list(args),
        cwd=workspace or REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
    )


class TempWorkspace:
    """A throwaway git repository with BEARING initialized in it.

    A real `git init` rather than a fake directory, because half of what BEARING
    does -- baseline tags, staleness from commit dates, working-tree checks --
    only exists in a git context.
    """

    def __init__(self, decisions_path="docs/decisions", git=True):
        self.decisions_path = decisions_path
        self.git = git
        self.path = ""

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix="bearing-test-")
        # Resolve symlinks: macOS puts temp dirs behind /var -> /private/var, and
        # git reports the resolved form, which would otherwise make every path
        # comparison in these tests fail for an uninteresting reason.
        self.path = os.path.realpath(self.path)
        if self.git:
            subprocess.run(["git", "init", "-q"], cwd=self.path, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"], cwd=self.path, check=True
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=self.path, check=True)
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False

    def init(self, *extra):
        result = run_cli(
            ["init", "--yes", "--decisions-path", self.decisions_path, "--no-render"] + list(extra),
            workspace=self.path,
        )
        if result.returncode != 0:
            raise AssertionError("bearing init failed:\n%s\n%s" % (result.stdout, result.stderr))
        return result

    def write(self, relative, content):
        target = os.path.join(self.path, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)
        return target

    def read(self, relative):
        target = os.path.join(self.path, relative)
        if not os.path.isfile(target):
            return None
        with open(target, "r", encoding="utf-8") as handle:
            return handle.read()

    def exists(self, relative):
        return os.path.exists(os.path.join(self.path, relative))

    def commit(self, message="test"):
        subprocess.run(["git", "add", "-A"], cwd=self.path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=self.path, check=True)

    def config(self, workspace_config=None, environ=None):
        """Resolve config against this workspace, isolating operator layers.

        `BEARING_HOME` is redirected into the temp directory so the developer's
        real `~/.bearing/config.json` cannot change a test result, and stray
        `BEARING_*` overrides are dropped unless a test passes them in `environ`.
        """
        from bearing.config import resolve

        os.environ["BEARING_HOME"] = os.path.join(self.path, "fake-home")
        environment = clean_environment()
        environment.update(environ or {})
        return resolve(
            workspace=self.path,
            flags=workspace_config or {},
            environ=environment,
        )


class BearingTestCase(unittest.TestCase):
    """Restores every `BEARING_*` variable a test may have set.

    In-process tests set them directly rather than through `run_cli`, so without
    this the order tests happen to run in changes their results.
    """

    def setUp(self):
        self._saved_env = {
            key: value for key, value in os.environ.items() if key.startswith("BEARING_")
        }

    def tearDown(self):
        for key in [key for key in os.environ if key.startswith("BEARING_")]:
            del os.environ[key]
        os.environ.update(self._saved_env)
