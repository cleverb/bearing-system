"""Packaging conformance: the plugin must survive being installed.

This is the tier-2 gate, and it is a CI test rather than a manual step because
the bug class it catches is invisible in a checkout and fatal after install.

Both Cursor and Claude Code **copy** the plugin directory into a versioned cache.
Agent Plugins v1.0.0 section 4.1.3 makes the consequence normative:

    When a client discovers, reads, or executes a file or directory supplied by
    the plugin package, the filesystem-resolved path MUST remain within the
    filesystem-resolved plugin root. ... clients MUST reject package paths that
    resolve outside it.

So a `../` reference from one skill to a sibling -- which reads perfectly
naturally in a monorepo checkout, and which the original interview spec called
for by design -- is not merely fragile. It is a path a conforming client is
required to refuse.

The test therefore copies the plugin somewhere with no parent context at all, and
asserts that everything still resolves.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unittest

from context import PLUGIN_ROOT, REPO_ROOT, BearingTestCase, run_cli

# `../` inside a quoted path, a markdown link, or a bare token.
_PARENT_REF_RE = re.compile(r"(?<![\w.])\.\./[A-Za-z0-9_.\-/]+")

_TEXT_EXTENSIONS = {".md", ".py", ".json", ".toml", ".yaml", ".yml", ".txt", ".mdc", ".sh"}

# Documentation legitimately quotes the anti-pattern in order to explain it. A
# reference is only a violation if a *tool* would follow it, so prose that names
# `../decision-recovery/...` while explaining why that breaks is allowed -- but
# only on a line that also explains itself.
_EXPLANATORY_MARKERS = (
    "breaks",
    "break",
    "rejected",
    "reject",
    "does not survive",
    "not survive",
    "anti-pattern",
    "would resolve outside",
    "resolve outside",
    "instead of",
    "rather than",
    "no longer",
    "used to",
)


# Local `pipx install ./plugin` / `python setup.py build` leftovers. They are
# gitignored and must not be treated as files the plugin needs to ship.
_SKIP_DIRS = {"__pycache__", ".git", "build", "dist", ".eggs"}


def _iter_text_files(root):
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in sorted(dirnames)
            if d not in _SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for filename in sorted(filenames):
            if os.path.splitext(filename)[1].lower() in _TEXT_EXTENSIONS:
                yield os.path.join(directory, filename)


class PluginRootContainmentTest(BearingTestCase):
    def test_no_parent_directory_references_escape_the_plugin_root(self):
        violations = []
        for path in _iter_text_files(PLUGIN_ROOT):
            relative = os.path.relpath(path, PLUGIN_ROOT)
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    for match in _PARENT_REF_RE.findall(line):
                        lowered = line.lower()
                        if any(marker in lowered for marker in _EXPLANATORY_MARKERS):
                            continue
                        resolved = os.path.normpath(
                            os.path.join(os.path.dirname(path), match)
                        )
                        if not resolved.startswith(os.path.abspath(PLUGIN_ROOT) + os.sep):
                            violations.append("%s:%d -> %s" % (relative, number, match))
        self.assertEqual(
            violations,
            [],
            "these references resolve outside the plugin root, which a conforming Agent "
            "Plugins client must reject after install:\n  " + "\n  ".join(violations),
        )

    def test_skills_do_not_reach_into_sibling_skills(self):
        """The specific failure the interview spec's original design would hit."""
        skills_root = os.path.join(PLUGIN_ROOT, "skills")
        violations = []
        for skill_name in sorted(os.listdir(skills_root)):
            skill_dir = os.path.join(skills_root, skill_name)
            if not os.path.isdir(skill_dir):
                continue
            for path in _iter_text_files(skill_dir):
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    for number, line in enumerate(handle, 1):
                        lowered = line.lower()
                        if any(marker in lowered for marker in _EXPLANATORY_MARKERS):
                            continue
                        for match in _PARENT_REF_RE.findall(line):
                            resolved = os.path.normpath(os.path.join(os.path.dirname(path), match))
                            if not resolved.startswith(os.path.abspath(skill_dir) + os.sep):
                                violations.append(
                                    "%s:%d -> %s"
                                    % (os.path.relpath(path, PLUGIN_ROOT), number, match)
                                )
        self.assertEqual(
            violations,
            [],
            "a skill may not reach outside its own directory by relative path; resolve shared "
            "files through the CLI (`bearing schema candidate`) instead:\n  "
            + "\n  ".join(violations),
        )


class InstalledCopyTest(BearingTestCase):
    """Copy the plugin out of the repository and use it from there."""

    def setUp(self):
        super().setUp()
        self.install_root = os.path.realpath(tempfile.mkdtemp(prefix="bearing-install-"))
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
        _force_writable(self.install_root)
        shutil.rmtree(self.install_root, ignore_errors=True)
        super().tearDown()

    def _run(self, args, workspace, extra_env=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(self.plugin_copy, "src")
        env["NO_COLOR"] = "1"
        if extra_env:
            env.update(extra_env)
        import subprocess

        return subprocess.run(
            [sys.executable, "-m", "bearing"] + list(args),
            cwd=workspace,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_plugin_root_resolves_to_the_copy_not_the_checkout(self):
        result = self._run(["--version"], self.install_root)
        self.assertEqual(result.returncode, 0, result.stderr)

        script = (
            "import json, sys;"
            "sys.path.insert(0, %r);"
            "from bearing.paths import plugin_root;"
            "print(plugin_root())" % os.path.join(self.plugin_copy, "src")
        )
        import subprocess

        out = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.install_root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        resolved = out.stdout.strip()
        self.assertEqual(
            resolved,
            self.plugin_copy,
            "plugin_root() must resolve to the installed copy, not back to the checkout",
        )
        self.assertNotIn(REPO_ROOT, resolved)

    def test_shared_schema_resolves_from_the_installed_copy(self):
        """`decision-interview` gets the candidate schema without a `../` path."""
        result = self._run(["schema", "candidate"], self.install_root)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = result.stdout.strip()
        self.assertTrue(os.path.isfile(path), "resolved schema path does not exist: %s" % path)
        self.assertTrue(
            path.startswith(self.plugin_copy + os.sep),
            "schema resolved outside the installed plugin root: %s" % path,
        )
        with open(path, "r", encoding="utf-8") as handle:
            json.load(handle)

    def test_pipeline_runs_with_the_plugin_tree_read_only(self):
        """The purity rule, enforced rather than asserted.

        Every plugin file is made read-only and every plugin directory
        non-writable, then a full render/index/lint cycle runs. If anything in
        BEARING tried to write inside its own installation -- a ledger, a
        transcript, an eval result -- this fails.
        """
        from context import TempWorkspace

        with TempWorkspace() as workspace:
            init = self._run(
                ["init", "--yes", "--decisions-path", "docs/decisions", "--no-render"],
                workspace.path,
                {"BEARING_HOME": os.path.join(workspace.path, "fake-home")},
            )
            self.assertEqual(init.returncode, 0, init.stdout + init.stderr)

            _make_read_only(self.plugin_copy)
            self.addCleanup(_force_writable, self.plugin_copy)

            env = {
                "BEARING_HOME": os.path.join(workspace.path, "fake-home"),
                "BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"repo"',
            }
            for command in (["render"], ["index"], ["lint"], ["verify", "--project"]):
                result = self._run(command, workspace.path, env)
                self.assertIn(
                    result.returncode,
                    (0, 1),
                    "bearing %s crashed with a read-only plugin tree:\n%s\n%s"
                    % (" ".join(command), result.stdout, result.stderr),
                )
                self.assertNotIn(
                    "Read-only file system",
                    result.stdout + result.stderr,
                    "bearing %s tried to write inside the plugin tree" % " ".join(command),
                )
                self.assertNotIn("Permission denied", result.stdout + result.stderr)

    def test_no_runtime_data_ships_inside_the_plugin(self):
        """Guards against the relocated files creeping back in."""
        forbidden = (
            "skills/decision-recovery/references/cost-ledger.jsonl",
            "skills/decision-recovery/references/gold-set",
            "skills/decision-recovery/references/dark-set",
            "skills/decision-recovery/references/negative-set",
            "skills/decision-interview/references/interview-transcripts",
        )
        present = [name for name in forbidden if os.path.exists(os.path.join(self.plugin_copy, name))]
        self.assertEqual(
            present,
            [],
            "runtime-written data is packaged inside the plugin and would be destroyed on the "
            "next update: %s" % ", ".join(present),
        )


class PipInstalledLayoutTest(BearingTestCase):
    """What `pipx install ./plugin` / `uv tool install ./plugin` produce.

    InstalledCopyTest copies the whole plugin tree and puts `src/` on PYTHONPATH,
    which is the marketplace-copy shape. A setuptools install only places the
    `bearing` package on site-packages. `plugin.json` and `skills/` live *beside*
    `src/bearing` in the checkout, so they are omitted unless the wheel bundler
    copies them into the package — and `plugin_root()` then cannot see a Cursor
    GUI install either, because that cache is a third tree.

    This test builds the site-packages layout using the same bundler the wheel
    uses, then asserts doctor can resolve the plugin without a checkout.
    """

    def setUp(self):
        super().setUp()
        self.site = os.path.realpath(tempfile.mkdtemp(prefix="bearing-site-"))
        self.pkg = os.path.join(self.site, "bearing")
        shutil.copytree(
            os.path.join(PLUGIN_ROOT, "src", "bearing"),
            self.pkg,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        loader = importlib.util.spec_from_file_location(
            "wheel_bundle", os.path.join(PLUGIN_ROOT, "wheel_bundle.py")
        )
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        module.bundle_plugin_root(self.pkg)

    def tearDown(self):
        shutil.rmtree(self.site, ignore_errors=True)
        super().tearDown()

    def _python(self, script):
        import subprocess

        env = dict(os.environ)
        env["PYTHONPATH"] = self.site
        env["NO_COLOR"] = "1"
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.site,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_unbundled_package_cannot_resolve_plugin_json(self):
        """The failure SETUP.md's user path hit before the wheel bundler existed."""
        bare = os.path.realpath(tempfile.mkdtemp(prefix="bearing-bare-"))
        empty_home = os.path.join(bare, "home")
        os.makedirs(empty_home)
        self.addCleanup(shutil.rmtree, bare, True)
        shutil.copytree(
            os.path.join(PLUGIN_ROOT, "src", "bearing"),
            os.path.join(bare, "bearing"),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        import subprocess

        env = dict(os.environ)
        env["PYTHONPATH"] = bare
        env["BEARING_HOME"] = empty_home
        env["NO_COLOR"] = "1"
        out = subprocess.run(
            [
                sys.executable,
                "-c",
                "from bearing.paths import plugin_root; "
                "from bearing.doctor import _plugin_check; "
                "check = _plugin_check(); "
                "print(check.status); print(plugin_root())",
            ],
            cwd=bare,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        status, root = out.stdout.strip().splitlines()
        self.assertEqual(status, "fail")
        self.assertEqual(root, os.path.join(bare, "bearing"))

    def test_plugin_root_resolves_inside_the_installed_package(self):
        out = self._python("from bearing.paths import plugin_root; print(plugin_root())")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), self.pkg)

    def test_doctor_plugin_check_passes(self):
        out = self._python(
            "from bearing.doctor import _plugin_check; "
            "check = _plugin_check(); "
            "print(check.status); print(check.detail)"
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        status, detail = out.stdout.strip().splitlines()
        self.assertEqual(status, "ok", out.stdout)
        self.assertEqual(detail, self.pkg)

    def test_schema_candidate_resolves_from_bundled_skills(self):
        import subprocess

        env = dict(os.environ)
        env["PYTHONPATH"] = self.site
        env["NO_COLOR"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "bearing", "schema", "candidate"],
            cwd=self.site,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        path = result.stdout.strip()
        self.assertTrue(path.startswith(self.pkg + os.sep), path)
        self.assertTrue(os.path.isfile(path), path)

    def test_setup_py_invokes_the_bundler(self):
        with open(os.path.join(PLUGIN_ROOT, "setup.py"), "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("from wheel_bundle import bundle_plugin_root", source)
        self.assertIn("bundle_plugin_root", source)


class ManifestConformanceTest(BearingTestCase):
    def test_canonical_manifest_satisfies_the_closed_schema(self):
        from bearing.manifests import load_canonical, validate_canonical

        data = load_canonical(PLUGIN_ROOT)
        self.assertEqual(validate_canonical(data), [])

    def test_generated_manifests_are_current(self):
        result = run_cli(["package", "--check"], workspace=REPO_ROOT)
        self.assertEqual(
            result.returncode,
            0,
            "client manifests have drifted from plugin/plugin.json:\n%s" % result.stdout,
        )

    def test_every_client_manifest_exists_and_parses(self):
        for relative in (
            "plugin/.cursor-plugin/plugin.json",
            "plugin/.claude-plugin/plugin.json",
            "plugin/.codex-plugin/plugin.json",
            ".cursor-plugin/marketplace.json",
            ".claude-plugin/marketplace.json",
        ):
            path = os.path.join(REPO_ROOT, relative)
            self.assertTrue(os.path.isfile(path), "missing generated manifest %s" % relative)
            with open(path, "r", encoding="utf-8") as handle:
                json.load(handle)

    def test_cursor_and_claude_hooks_use_separate_client_schemas(self):
        with open(os.path.join(PLUGIN_ROOT, ".cursor-plugin", "plugin.json"), "r", encoding="utf-8") as handle:
            cursor_manifest = json.load(handle)
        self.assertEqual(cursor_manifest["hooks"], "./hooks/cursor.json")
        self.assertEqual(cursor_manifest["displayName"], "BEARING")
        with open(os.path.join(PLUGIN_ROOT, "hooks", "cursor.json"), "r", encoding="utf-8") as handle:
            cursor = json.load(handle)
        with open(os.path.join(PLUGIN_ROOT, "hooks", "hooks.json"), "r", encoding="utf-8") as handle:
            claude = json.load(handle)
        self.assertIn("workspaceOpen", cursor["hooks"])
        self.assertIn("PreToolUse", claude["hooks"])
        self.assertNotEqual(cursor, claude)

    def test_plugin_ships_mcp_with_plugin_root_not_workspace_folder(self):
        path = os.path.join(PLUGIN_ROOT, "mcp.json")
        self.assertTrue(os.path.isfile(path), "plugin/mcp.json must ship with the marketplace plugin")
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        servers = payload["mcpServers"]
        self.assertIn("BEARING", servers)
        server = servers["BEARING"]
        self.assertEqual(server.get("cwd"), "${PLUGIN_ROOT}")
        blob = json.dumps(server)
        self.assertNotIn("${workspaceFolder}", blob)
        self.assertTrue(os.path.isfile(os.path.join(PLUGIN_ROOT, "hooks", "run_mcp.py")))

    def test_marketplace_entry_advertises_bearing_display_name_and_mcp(self):
        with open(os.path.join(REPO_ROOT, ".cursor-plugin/marketplace.json"), "r", encoding="utf-8") as handle:
            cursor = json.load(handle)["plugins"][0]
        self.assertEqual(cursor["displayName"], "BEARING")
        self.assertEqual(cursor["mcpServers"], "./mcp.json")
        self.assertTrue(cursor["description"].startswith("BEARING"))
        with open(os.path.join(REPO_ROOT, ".claude-plugin/marketplace.json"), "r", encoding="utf-8") as handle:
            claude = json.load(handle)["plugins"][0]
        self.assertNotIn("displayName", claude)
        self.assertNotIn("mcpServers", claude)
        self.assertTrue(claude["description"].startswith("BEARING"))

    def test_marketplace_source_points_at_the_plugin_directory(self):
        for relative in (".cursor-plugin/marketplace.json", ".claude-plugin/marketplace.json"):
            with open(os.path.join(REPO_ROOT, relative), "r", encoding="utf-8") as handle:
                catalog = json.load(handle)
            entry = catalog["plugins"][0]
            source = entry["source"].lstrip("./")
            self.assertTrue(
                os.path.isfile(os.path.join(REPO_ROOT, source, "plugin.json")),
                "%s points `source` at %r, which has no plugin.json" % (relative, entry["source"]),
            )

    def test_marketplace_name_is_not_reserved(self):
        from bearing.manifests import CLAUDE_RESERVED_MARKETPLACE_NAMES

        with open(os.path.join(REPO_ROOT, ".claude-plugin/marketplace.json"), "r", encoding="utf-8") as handle:
            catalog = json.load(handle)
        self.assertNotIn(catalog["name"], CLAUDE_RESERVED_MARKETPLACE_NAMES)

    def test_every_skill_has_discoverable_frontmatter(self):
        """Without `name` and `description`, a skill is invisible to every runtime."""
        from bearing.util import parse_frontmatter

        skills_root = os.path.join(PLUGIN_ROOT, "skills")
        for skill_name in sorted(os.listdir(skills_root)):
            skill_file = os.path.join(skills_root, skill_name, "SKILL.md")
            if not os.path.isfile(skill_file):
                continue
            with open(skill_file, "r", encoding="utf-8") as handle:
                front, _ = parse_frontmatter(handle.read())
            self.assertEqual(
                front.get("name"),
                skill_name,
                "%s/SKILL.md must declare `name: %s` to match its directory" % (skill_name, skill_name),
            )
            self.assertTrue(
                str(front.get("description", "")).strip(),
                "%s/SKILL.md needs a `description`; without one no runtime can decide when to "
                "load it" % skill_name,
            )


class GitHostedInstallTest(BearingTestCase):
    """Tier 2 continued: install by git ref, not by local path.

    A local-path install copies the working tree, so a file that exists on disk
    but is excluded from git is still there. A git-hosted marketplace install
    resolves a *ref*, so anything ignored simply does not arrive. That makes an
    over-broad `.gitignore` a defect that only ever appears for other people --
    exactly the class the four-tier path exists to catch before publish.
    """

    def test_no_file_the_plugin_needs_is_excluded_from_git(self):
        import subprocess

        candidates = [
            os.path.relpath(path, REPO_ROOT).replace("\\", "/")
            for path in _iter_text_files(PLUGIN_ROOT)
        ]
        result = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            cwd=REPO_ROOT,
            input="\n".join(candidates) + "\n",
            capture_output=True,
            text=True,
        )
        # Exit 0 means at least one path matched an ignore rule; 1 means none did.
        ignored = [line for line in result.stdout.split("\n") if line.strip()]
        self.assertEqual(
            ignored,
            [],
            "these ship as part of the plugin but are excluded from git, so a git-hosted "
            "marketplace install would silently omit them:\n  " + "\n  ".join(ignored),
        )

    def test_plugin_works_after_a_clone_round_trip(self):
        import subprocess

        scratch = os.path.realpath(tempfile.mkdtemp(prefix="bearing-githost-"))
        self.addCleanup(shutil.rmtree, scratch, True)

        origin = os.path.join(scratch, "origin")
        os.makedirs(origin)
        shutil.copytree(
            PLUGIN_ROOT,
            os.path.join(origin, "plugin"),
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "build", "dist", "*.egg-info"
            ),
            ignore_dangling_symlinks=True,
        )
        shutil.copy2(os.path.join(REPO_ROOT, ".gitignore"), os.path.join(origin, ".gitignore"))
        for command in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.invalid"],
            ["git", "config", "user.name", "Test"],
            ["git", "add", "-A"],
            ["git", "commit", "-q", "-m", "marketplace"],
        ):
            subprocess.run(command, cwd=origin, check=True)

        clone = os.path.join(scratch, "clone")
        subprocess.run(["git", "clone", "-q", origin, clone], check=True)

        cloned_plugin = os.path.join(clone, "plugin")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(cloned_plugin, "src")
        env["NO_COLOR"] = "1"

        version = subprocess.run(
            [sys.executable, "-m", "bearing", "--version"],
            cwd=clone,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(version.returncode, 0, version.stderr)

        # Every packaged data file the CLI resolves at runtime has to have made
        # the trip, so exercise the ones that are read from disk rather than
        # imported.
        for args in (["schema", "candidate"], ["schema", "config"]):
            result = subprocess.run(
                [sys.executable, "-m", "bearing"] + args,
                cwd=clone,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(
                result.returncode,
                0,
                "`bearing %s` failed after a git-hosted install:\n%s"
                % (" ".join(args), result.stderr),
            )
            path = result.stdout.strip()
            self.assertTrue(
                os.path.isfile(path),
                "`bearing %s` resolved %s, which did not survive the clone" % (" ".join(args), path),
            )
            self.assertTrue(path.startswith(cloned_plugin + os.sep))


def _make_read_only(root):
    for directory, dirnames, filenames in os.walk(root, topdown=False):
        for filename in filenames:
            path = os.path.join(directory, filename)
            os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        for dirname in dirnames:
            path = os.path.join(directory, dirname)
            os.chmod(path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
    os.chmod(root, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)


def _force_writable(root):
    for directory, dirnames, filenames in os.walk(root):
        os.chmod(directory, 0o755)
        for filename in filenames:
            try:
                os.chmod(os.path.join(directory, filename), 0o644)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
