"""Projection: determinism, drift detection, scopes, and block management."""

from __future__ import annotations

import json
import os
import unittest

from context import BearingTestCase, TempWorkspace, run_cli

REPO_SCOPE = {"BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"repo"'}


class SubagentProjectionTest(BearingTestCase):
    def test_each_runtime_gets_its_native_format(self):
        with TempWorkspace() as workspace:
            workspace.init()
            result = run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            self.assertTrue(workspace.exists(".cursor/agents/decision-archaeologist.md"))
            self.assertTrue(workspace.exists(".claude/agents/decision-archaeologist.md"))
            self.assertTrue(workspace.exists(".codex/agents/decision-archaeologist.toml"))

    def test_codex_output_carries_the_required_toml_keys(self):
        """Codex custom agents need name, description, and developer_instructions."""
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            toml = workspace.read(".codex/agents/decision-archaeologist.toml")
            self.assertIn('name = "decision-archaeologist"', toml)
            self.assertIn("description = ", toml)
            self.assertIn("developer_instructions = ", toml)

    def test_readonly_maps_onto_codex_sandbox_policy(self):
        """The authority boundary survives the format change."""
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            reviewer = workspace.read(".codex/agents/decision-recovery-reviewer.toml")
            self.assertIn('sandbox_policy = "read-only"', reviewer)

            archaeologist = workspace.read(".codex/agents/decision-archaeologist.toml")
            self.assertNotIn("sandbox_policy", archaeologist)

    def test_cursor_only_fields_are_not_emitted_for_claude(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertIn("is_background", workspace.read(".cursor/agents/decision-archaeologist.md"))
            self.assertNotIn(
                "is_background", workspace.read(".claude/agents/decision-archaeologist.md")
            )

    def test_every_generated_file_carries_a_do_not_edit_header(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            for relative in (
                ".cursor/agents/decision-archaeologist.md",
                ".claude/agents/decision-archaeologist.md",
                ".codex/agents/decision-archaeologist.toml",
                ".cursor/rules/bearing.mdc",
            ):
                content = workspace.read(relative)
                self.assertIn("DO NOT EDIT", content, "%s has no provenance header" % relative)
                self.assertIn(
                    "Generated from plugin/",
                    content,
                    "%s does not name the canonical source it derives authority from" % relative,
                )
                self.assertIn(
                    "bearing render",
                    content,
                    "%s does not say how to regenerate it" % relative,
                )

    def test_markdown_frontmatter_stays_at_the_top_of_the_file(self):
        """The notice must not displace the opening `---` fence."""
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            content = workspace.read(".cursor/agents/decision-archaeologist.md")
            self.assertTrue(content.startswith("---\n"))
            lines = content.split("\n")
            closing = lines.index("---", 1)
            self.assertIn("DO NOT EDIT", "\n".join(lines[closing : closing + 4]))


class DeterminismTest(BearingTestCase):
    def test_two_renders_are_byte_identical(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            first = {
                relative: workspace.read(relative)
                for relative in _generated(workspace)
            }
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            second = {
                relative: workspace.read(relative)
                for relative in _generated(workspace)
            }
            self.assertEqual(first, second)

    def test_lock_file_records_no_wall_clock_time(self):
        """A timestamp inside the lock would report drift on every unrelated run."""
        import re

        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            lock = json.loads(workspace.read(".bearing/projections.lock.json"))

            dated = re.compile(r"\d{4}-\d{2}-\d{2}")
            found = []

            def walk(node, path):
                if isinstance(node, dict):
                    for key, value in node.items():
                        if "time" in key or "date" in key or key.endswith("_at"):
                            found.append(path + "." + key)
                        walk(value, path + "." + key)
                elif isinstance(node, list):
                    for index, item in enumerate(node):
                        walk(item, "%s[%d]" % (path, index))
                elif isinstance(node, str) and dated.search(node):
                    found.append(path)

            walk(lock, "lock")
            self.assertEqual(found, [], "these carry wall-clock time: %s" % ", ".join(found))


class DriftTest(BearingTestCase):
    def test_check_passes_immediately_after_render(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            result = run_cli(["render", "--check"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_hand_edited_adapter_is_reported_as_drift(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            path = ".cursor/agents/decision-archaeologist.md"
            workspace.write(path, workspace.read(path) + "\n\nhand-edited\n")
            result = run_cli(["render", "--check"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertEqual(result.returncode, 1)
            self.assertIn("DRIFT", result.stdout)

    def test_a_deleted_adapter_is_reported_as_missing(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            os.remove(os.path.join(workspace.path, ".codex/agents/decision-interviewer.toml"))
            result = run_cli(["render", "--check"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing", result.stdout)

    def test_check_does_not_write_anything(self):
        with TempWorkspace() as workspace:
            workspace.init()
            result = run_cli(["render", "--check"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertEqual(result.returncode, 1, "nothing rendered yet, so check must fail")
            self.assertFalse(workspace.exists(".cursor/agents/decision-archaeologist.md"))


class ConfigurableProjectionTest(BearingTestCase):
    def test_dropping_a_target_stops_generating_it(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/config.json",
                json.dumps(
                    {
                        "version": 1,
                        "decisions": {"path": "docs/decisions"},
                        "projections": {
                            "subagents": {"targets": ["cursor"], "scope": "repo"},
                            "rules": {"targets": ["cursor"], "scope": "repo"},
                        },
                    }
                ),
            )
            result = run_cli(["render"], workspace=workspace.path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(workspace.exists(".cursor/agents/decision-archaeologist.md"))
            self.assertFalse(workspace.exists(".codex/agents/decision-archaeologist.toml"))

    def test_a_skipped_target_is_recorded_with_a_reason(self):
        """Absence must be distinguishable from breakage."""
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/config.json",
                json.dumps(
                    {
                        "version": 1,
                        "decisions": {"path": "docs/decisions"},
                        "projections": {"subagents": {"targets": ["cursor"], "scope": "repo"}},
                    }
                ),
            )
            run_cli(["render"], workspace=workspace.path)
            lock = json.loads(workspace.read(".bearing/projections.lock.json"))
            skipped = {entry["target"]: entry["reason"] for entry in lock["skipped"]}
            self.assertIn("codex", skipped)
            self.assertTrue(skipped["codex"].strip())

    def test_turning_a_target_off_removes_its_orphaned_output(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertTrue(workspace.exists(".codex/agents/decision-archaeologist.toml"))

            workspace.write(
                ".bearing/config.json",
                json.dumps(
                    {
                        "version": 1,
                        "decisions": {"path": "docs/decisions"},
                        "projections": {
                            "subagents": {"targets": ["cursor"], "scope": "repo"},
                            "rules": {"targets": ["cursor", "agents-md"], "scope": "repo"},
                        },
                    }
                ),
            )
            result = run_cli(["render"], workspace=workspace.path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(
                workspace.exists(".codex/agents/decision-archaeologist.toml"),
                "a stale adapter left behind becomes a second source of truth",
            )

    def test_ephemeral_scope_writes_nothing_into_the_workspace(self):
        with TempWorkspace() as workspace:
            workspace.init()
            result = run_cli(
                ["render", "--ephemeral", "--emit-plugin-paths"],
                workspace=workspace.path,
                env={"BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"ephemeral"',
                     "BEARING_PROJECTIONS_RULES_SCOPE": '"ephemeral"'},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout.strip().split("\n")[-1])
            self.assertIn("pluginPaths", payload)
            self.assertEqual(len(payload["pluginPaths"]), 1)
            self.assertFalse(workspace.exists(".cursor/agents"))
            self.assertFalse(workspace.exists(".codex/agents"))

    def test_projection_necessity_is_enforced(self):
        """A projection whose targets share one format is redundant machinery."""
        from bearing.render import projection_necessity_errors

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config(
                {"projections.contracts.targets": ["agents-md", "agents-md"]}
            )
            self.assertEqual(projection_necessity_errors(config), [])

            config = workspace.config({"projections.subagents.targets": ["cursor", "cursor"]})
            self.assertEqual(projection_necessity_errors(config), [])

    def test_a_single_format_multi_target_projection_is_rejected(self):
        from bearing.config import resolve
        from bearing.render import _NATIVE_FORMATS, projection_necessity_errors

        with TempWorkspace() as workspace:
            workspace.init()
            # Two distinct target names that read the same format would be a
            # renderer bridging nothing.
            original = _NATIVE_FORMATS["claude"]
            _NATIVE_FORMATS["claude"] = _NATIVE_FORMATS["cursor"]
            try:
                config = workspace.config(
                    {"projections.subagents.targets": ["cursor", "claude"]}
                )
                errors = projection_necessity_errors(config)
                self.assertTrue(errors)
                self.assertIn("same format", errors[0])
            finally:
                _NATIVE_FORMATS["claude"] = original


class ManagedBlockTest(BearingTestCase):
    def test_existing_agents_md_content_is_preserved(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "AGENTS.md",
                "# Our Rules\n\nAlways use tabs. Never touch the billing module on a Friday.\n",
            )
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            content = workspace.read("AGENTS.md")
            self.assertIn("Always use tabs.", content)
            self.assertIn("Never touch the billing module on a Friday.", content)
            self.assertIn("BEARING:START", content)

    def test_block_replacement_is_idempotent(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write("AGENTS.md", "# Ours\n\nkeep me\n")
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            once = workspace.read("AGENTS.md")
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertEqual(once, workspace.read("AGENTS.md"))
            self.assertEqual(once.count("BEARING:START"), 1)

    def test_agents_md_is_created_when_absent(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            self.assertTrue(workspace.exists("AGENTS.md"))
            self.assertIn("BEARING:START", workspace.read("AGENTS.md"))

    def test_the_block_names_the_configured_decisions_path(self):
        with TempWorkspace(decisions_path="docs/adr") as workspace:
            workspace.init()
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            content = workspace.read("AGENTS.md")
            self.assertIn("docs/adr/", content)
            self.assertNotIn("docs/decisions/", content)

    def test_claude_md_gets_a_pointer_only_when_it_already_exists(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(
                ["render"],
                workspace=workspace.path,
                env=dict(REPO_SCOPE, BEARING_PROJECTIONS_RULES_TARGETS='["cursor","agents-md","claude"]'),
            )
            self.assertFalse(
                workspace.exists("CLAUDE.md"),
                "BEARING must not add a second governance file to a repository that had one",
            )

            workspace.write("CLAUDE.md", "# Claude notes\n\nour own notes\n")
            run_cli(
                ["render"],
                workspace=workspace.path,
                env=dict(REPO_SCOPE, BEARING_PROJECTIONS_RULES_TARGETS='["cursor","agents-md","claude"]'),
            )
            content = workspace.read("CLAUDE.md")
            self.assertIn("our own notes", content)
            self.assertIn("AGENTS.md", content)
            self.assertIn("BEARING:START", content)
            self.assertNotIn(
                "Hard constraints",
                content,
                "CLAUDE.md gets a pointer, never a duplicated constitution",
            )

    def test_stripping_the_block_leaves_the_rest_of_the_file(self):
        from bearing.agentsmd import strip_block

        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write("AGENTS.md", "# Ours\n\nkeep this line\n")
            run_cli(["render"], workspace=workspace.path, env=REPO_SCOPE)
            strip_block(os.path.join(workspace.path, "AGENTS.md"))
            content = workspace.read("AGENTS.md")
            self.assertIn("keep this line", content)
            self.assertNotIn("BEARING:START", content)


def _generated(workspace):
    found = []
    for base in (".cursor", ".claude", ".codex"):
        root = os.path.join(workspace.path, base)
        for directory, _, filenames in os.walk(root):
            for filename in sorted(filenames):
                path = os.path.join(directory, filename)
                found.append(os.path.relpath(path, workspace.path))
    return sorted(found) + ["AGENTS.md", ".bearing/projections.lock.json"]


if __name__ == "__main__":
    unittest.main()
