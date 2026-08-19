"""Operator-scope CLI enablement (ADR-0012)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from context import PLUGIN_ROOT, BearingTestCase


class PluginBinLauncherTest(BearingTestCase):
    def setUp(self):
        super().setUp()
        self.install_root = os.path.realpath(tempfile.mkdtemp(prefix="bearing-bin-"))
        self.plugin_copy = os.path.join(self.install_root, "bearing")
        shutil.copytree(
            PLUGIN_ROOT,
            self.plugin_copy,
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "build", "dist", "*.egg-info"
            ),
            ignore_dangling_symlinks=True,
        )

    def tearDown(self):
        shutil.rmtree(self.install_root, ignore_errors=True)
        super().tearDown()

    def _run(self, launcher: str, args):
        return subprocess.run(
            [sys.executable, os.path.join(self.plugin_copy, "bin", launcher)] + list(args),
            cwd=self.install_root,
            capture_output=True,
            text=True,
            env={"NO_COLOR": "1"},
        )

    def test_bearing_launcher_reports_version(self):
        result = self._run("bearing", ["--version"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bearing", result.stdout)

    def test_bearing_mcp_launcher_imports(self):
        result = subprocess.run(
            [sys.executable, os.path.join(self.plugin_copy, "bin", "bearing-mcp"), "--help"],
            cwd=self.install_root,
            capture_output=True,
            text=True,
            env={"NO_COLOR": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_schema_resolves_through_bin_launcher(self):
        result = self._run("bearing", ["schema", "candidate"])
        self.assertEqual(result.returncode, 0, result.stderr)
        path = result.stdout.strip()
        self.assertTrue(path.startswith(self.plugin_copy + os.sep), path)


class EnableShimTest(BearingTestCase):
    def setUp(self):
        super().setUp()
        self.home = os.path.realpath(tempfile.mkdtemp(prefix="bearing-home-"))
        self.install_root = os.path.realpath(tempfile.mkdtemp(prefix="bearing-plugin-"))
        self.plugin_copy = os.path.join(self.install_root, "plugin")
        shutil.copytree(
            PLUGIN_ROOT,
            self.plugin_copy,
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "build", "dist", "*.egg-info"
            ),
            ignore_dangling_symlinks=True,
        )

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.install_root, ignore_errors=True)
        super().tearDown()

    def test_ensure_enabled_writes_pointer_and_shims(self):
        sys.path.insert(0, os.path.join(PLUGIN_ROOT, "src"))
        from bearing.enable import ensure_enabled, load_install_pointer

        outcome = ensure_enabled(
            self.plugin_copy,
            sys.executable,
            home=self.home,
        )
        self.assertTrue(outcome["ok"], outcome.get("errors"))
        pointer = load_install_pointer(home=self.home)
        self.assertIsNotNone(pointer)
        self.assertEqual(pointer["plugin_root"], self.plugin_copy)
        shim = os.path.join(self.home, "bin", "bearing")
        self.assertTrue(os.path.isfile(shim))
        with open(os.path.join(self.home, "install.json"), encoding="utf-8") as handle:
            json.load(handle)

    def test_plugin_root_uses_install_pointer_when_package_isolated(self):
        sys.path.insert(0, os.path.join(PLUGIN_ROOT, "src"))
        from bearing.enable import ensure_enabled
        from bearing.paths import plugin_root

        ensure_enabled(self.plugin_copy, sys.executable, home=self.home)
        site = os.path.realpath(tempfile.mkdtemp(prefix="bearing-site-"))
        self.addCleanup(shutil.rmtree, site, True)
        pkg = os.path.join(site, "bearing")
        shutil.copytree(
            os.path.join(PLUGIN_ROOT, "src", "bearing"),
            pkg,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = site
        env["BEARING_HOME"] = self.home
        env["NO_COLOR"] = "1"
        script = (
            "from bearing.paths import plugin_root; "
            "print(plugin_root())"
        )
        out = subprocess.run(
            [sys.executable, "-c", script],
            cwd=site,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), self.plugin_copy)

    def test_mirrored_local_bin_counts_as_operator_shim(self):
        sys.path.insert(0, os.path.join(PLUGIN_ROOT, "src"))
        from bearing.enable import ensure_enabled, is_operator_shim

        outcome = ensure_enabled(self.plugin_copy, sys.executable, home=self.home)
        self.assertTrue(outcome["ok"], outcome.get("errors"))
        shim = os.path.join(self.home, "bin", "bearing")
        self.assertTrue(is_operator_shim(shim))
        copy = os.path.join(self.home, "bearing-copy")
        shutil.copy2(shim, copy)
        self.assertTrue(is_operator_shim(copy))

    def test_enable_with_read_only_plugin_succeeds(self):
        sys.path.insert(0, os.path.join(PLUGIN_ROOT, "src"))
        from bearing.enable import ensure_enabled

        for directory, dirnames, filenames in os.walk(self.plugin_copy, topdown=False):
            for filename in filenames:
                os.chmod(os.path.join(directory, filename), 0o444)
            for dirname in dirnames:
                os.chmod(os.path.join(directory, dirname), 0o555)
        os.chmod(self.plugin_copy, 0o555)
        outcome = ensure_enabled(
            self.plugin_copy,
            sys.executable,
            home=self.home,
        )
        self.assertTrue(outcome["ok"], outcome.get("errors"))

    def test_discover_plugin_roots_finds_marketplace_copy(self):
        sys.path.insert(0, os.path.join(PLUGIN_ROOT, "src"))
        from bearing.enable import discover_plugin_roots

        cache = os.path.join(self.install_root, "cursor", "plugins", "cache", "bearing")
        os.makedirs(cache, exist_ok=True)
        shutil.copytree(
            self.plugin_copy,
            cache,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        found = discover_plugin_roots(bases=[os.path.join(self.install_root, "cursor", "plugins")])
        self.assertEqual(found[0], os.path.abspath(cache))

    def test_discover_skips_orphaned_and_binless_trees(self):
        sys.path.insert(0, os.path.join(PLUGIN_ROOT, "src"))
        from bearing.enable import discover_plugin_roots, ensure_enabled

        base = os.path.join(self.install_root, "claude", "plugins")
        orphan = os.path.join(base, "cache", "bearing", "orphaned")
        shutil.copytree(
            self.plugin_copy,
            orphan,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        write_orphan = open(os.path.join(orphan, ".orphaned_at"), "w", encoding="utf-8")
        write_orphan.write("1")
        write_orphan.close()

        binless = os.path.join(base, "cache", "bearing", "binless")
        shutil.copytree(
            self.plugin_copy,
            binless,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "bin"),
        )
        # Remove bin if copytree still left an empty dir pattern miss
        bin_dir = os.path.join(binless, "bin")
        if os.path.isdir(bin_dir):
            shutil.rmtree(bin_dir)

        found = discover_plugin_roots(bases=[base])
        self.assertEqual(found, [])
        outcome = ensure_enabled(binless, sys.executable, home=self.home)
        self.assertFalse(outcome["ok"])

    def test_standalone_enable_script(self):
        env = dict(os.environ)
        env["BEARING_HOME"] = self.home
        env["NO_COLOR"] = "1"
        result = subprocess.run(
            [sys.executable, os.path.join(PLUGIN_ROOT, "enable.py"), "--plugin-root", self.plugin_copy],
            cwd=self.install_root,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.home, "bin", "bearing")))


if __name__ == "__main__":
    unittest.main()
