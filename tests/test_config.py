"""Config resolution, precedence, and the legacy-convention path."""

from __future__ import annotations

import json
import os
import unittest

from context import BearingTestCase, TempWorkspace, run_cli


class ClassificationTest(BearingTestCase):
    def test_every_default_key_is_classified(self):
        """An unclassified key has undefined precedence, so it is a hard error."""
        from bearing.config import classify, default_config
        from bearing.util import flatten

        unclassified = sorted(key for key in flatten(default_config()) if classify(key) is None)
        self.assertEqual(
            unclassified,
            [],
            "these keys have no repo/operator classification, so their precedence is "
            "undefined: %s" % ", ".join(unclassified),
        )

    def test_repo_and_operator_facts_are_split_as_designed(self):
        from bearing.config import OPERATOR_FACT, REPO_FACT, classify

        self.assertEqual(classify("decisions.path"), REPO_FACT)
        self.assertEqual(classify("scope.include"), REPO_FACT)
        self.assertEqual(classify("enforcement.block_on"), REPO_FACT)
        self.assertEqual(classify("verify.anchor_coverage_min"), REPO_FACT)
        self.assertEqual(classify("interview.transcripts.retention"), REPO_FACT)

        self.assertEqual(classify("models.extract.model"), OPERATOR_FACT)
        self.assertEqual(classify("cost.reviewer_rate_usd_per_hour"), OPERATOR_FACT)

    def test_projection_targets_are_repo_facts_but_scope_is_an_operator_fact(self):
        """Which runtimes the repo supports versus where one machine writes them."""
        from bearing.config import OPERATOR_FACT, REPO_FACT, classify

        self.assertEqual(classify("projections.subagents.targets"), REPO_FACT)
        self.assertEqual(classify("projections.subagents.scope"), OPERATOR_FACT)

    def test_budget_cap_is_a_repo_fact_despite_living_under_cost(self):
        from bearing.config import OPERATOR_FACT, REPO_FACT, classify

        self.assertEqual(classify("cost.budget_usd_per_run"), REPO_FACT)
        self.assertEqual(classify("cost.price_book_max_age_days"), OPERATOR_FACT)


class PrecedenceTest(BearingTestCase):
    def _layers(self, workspace, user=None, repo=None, local=None):
        home = os.path.join(workspace.path, "fake-home")
        os.makedirs(home, exist_ok=True)
        if user is not None:
            with open(os.path.join(home, "config.json"), "w", encoding="utf-8") as handle:
                json.dump(user, handle)
        if repo is not None:
            workspace.write(".bearing/config.json", json.dumps(repo))
        if local is not None:
            workspace.write(".bearing/config.local.json", json.dumps(local))
        os.environ["BEARING_HOME"] = home

    def test_repo_config_wins_for_a_repo_fact(self):
        with TempWorkspace() as workspace:
            self._layers(
                workspace,
                user={"version": 1, "decisions": {"path": "docs/decisions"}},
                repo={"version": 1, "decisions": {"path": "docs/adr"}},
            )
            config = workspace.config()
            self.assertEqual(config.get("decisions.path"), "docs/adr")
            self.assertEqual(config.origin("decisions.path"), "repo")

    def test_user_config_wins_for_an_operator_fact(self):
        with TempWorkspace() as workspace:
            self._layers(
                workspace,
                user={"version": 1, "models": {"resolve": {"model": "gpt-5"}}},
                repo={"version": 1, "models": {"resolve": {"model": "claude-sonnet-4.5"}}},
            )
            config = workspace.config()
            self.assertEqual(config.get("models.resolve.model"), "gpt-5")
            self.assertEqual(config.origin("models.resolve.model"), "user")

    def test_repo_may_suggest_an_operator_default_that_user_config_overrides(self):
        with TempWorkspace() as workspace:
            self._layers(
                workspace,
                repo={"version": 1, "projections": {"subagents": {"scope": "repo"}}},
            )
            self.assertEqual(workspace.config().get("projections.subagents.scope"), "repo")

            self._layers(
                workspace,
                user={"version": 1, "projections": {"subagents": {"scope": "user"}}},
                repo={"version": 1, "projections": {"subagents": {"scope": "repo"}}},
            )
            config = workspace.config()
            self.assertEqual(config.get("projections.subagents.scope"), "user")
            self.assertEqual(config.origin("projections.subagents.scope"), "user")

    def test_local_override_of_a_repo_fact_warns(self):
        with TempWorkspace() as workspace:
            self._layers(
                workspace,
                repo={"version": 1, "decisions": {"path": "docs/decisions"}},
                local={"decisions": {"path": "docs/somewhere-else"}},
            )
            config = workspace.config()
            self.assertEqual(config.get("decisions.path"), "docs/somewhere-else")
            self.assertTrue(
                any("repo fact overridden" in warning for warning in config.warnings),
                "a repo fact set locally must be reported: it makes one machine behave "
                "differently from every other clone",
            )

    def test_env_and_flags_win_over_every_file(self):
        with TempWorkspace() as workspace:
            self._layers(workspace, repo={"version": 1, "decisions": {"path": "docs/adr"}})

            from_env = {"BEARING_DECISIONS_PATH": "docs/from-env"}
            config = workspace.config(environ=from_env)
            self.assertEqual(config.get("decisions.path"), "docs/from-env")
            self.assertEqual(config.origin("decisions.path"), "env")

            flagged = workspace.config({"decisions.path": "docs/from-flag"}, environ=from_env)
            self.assertEqual(flagged.get("decisions.path"), "docs/from-flag")
            self.assertEqual(
                flagged.origin("decisions.path"),
                "flags",
                "an explicit flag is the most local intent there is and outranks the environment",
            )

    def test_an_unparseable_env_value_is_taken_as_a_literal_string(self):
        """`BEARING_DECISIONS_PATH=docs/adr` must work without JSON quoting."""
        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config(environ={"BEARING_DECISIONS_PATH": "docs/adr"})
            self.assertEqual(config.get("decisions.path"), "docs/adr")

    def test_an_unrecognized_bearing_variable_is_ignored_rather_than_guessed_at(self):
        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config(environ={"BEARING_NOT_A_REAL_SETTING": "1"})
            self.assertEqual(config.errors, [])


class ValidationTest(BearingTestCase):
    def test_unknown_key_is_rejected(self):
        with TempWorkspace() as workspace:
            workspace.write(
                ".bearing/config.json", json.dumps({"version": 1, "decisions": {"pathh": "x"}})
            )
            config = workspace.config()
            self.assertTrue(config.errors)
            self.assertTrue(any("unknown key" in error or "not classified" in error for error in config.errors))

    def test_recovery_signal_may_never_block_a_merge(self):
        """The hard invariant, refused at the config layer."""
        with TempWorkspace() as workspace:
            workspace.write(
                ".bearing/config.json",
                json.dumps({"version": 1, "enforcement": {"block_on": ["recovery_signal"]}}),
            )
            config = workspace.config()
            self.assertTrue(
                any("recovery_signal" in error for error in config.errors),
                "config must refuse to let an inference signal gate a merge",
            )

    def test_vendored_without_a_pinned_version_is_rejected(self):
        with TempWorkspace() as workspace:
            workspace.write(
                ".bearing/config.json",
                json.dumps({"version": 1, "skills": {"source": "vendored"}}),
            )
            config = workspace.config()
            self.assertTrue(any("vendored_version" in error for error in config.errors))

    def test_decisions_path_may_not_escape_the_workspace(self):
        with TempWorkspace() as workspace:
            workspace.write(
                ".bearing/config.json",
                json.dumps({"version": 1, "decisions": {"path": "../elsewhere"}}),
            )
            self.assertTrue(any("inside the workspace" in e for e in workspace.config().errors))


class InitTest(BearingTestCase):
    def test_init_adopts_an_existing_legacy_convention(self):
        with TempWorkspace() as workspace:
            workspace.write("docs/adr/0001-something.md", "# ADR-0001: Something\n")
            result = run_cli(["init", "--yes"], workspace=workspace.path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            config = workspace.config()
            self.assertEqual(config.get("decisions.path"), "docs/adr")
            self.assertFalse(
                workspace.exists("docs/decisions"),
                "init must not create a second decision tree beside the repository's real one",
            )

    def test_init_never_migrates_a_legacy_directory(self):
        with TempWorkspace() as workspace:
            workspace.write("docs/ADRs/0001-legacy.md", "# ADR-0001: Legacy\n")
            run_cli(["init", "--yes"], workspace=workspace.path)
            self.assertTrue(
                workspace.exists("docs/ADRs/0001-legacy.md"),
                "the original directory and its records must be left exactly where they were",
            )

    def test_discouraged_naming_warns_without_failing(self):
        with TempWorkspace() as workspace:
            workspace.write("docs/adrs/0001-legacy.md", "# ADR-0001: Legacy\n")
            result = run_cli(["init", "--yes"], workspace=workspace.path)
            self.assertEqual(
                result.returncode, 0, "discouraged naming is a warning, never an error"
            )
            self.assertIn("advises against", result.stdout)

    def test_record_deviation_writes_an_explanatory_decision_record(self):
        with TempWorkspace(decisions_path="docs/adr") as workspace:
            result = run_cli(
                ["init", "--yes", "--decisions-path", "docs/adr", "--record-deviation", "--no-render"],
                workspace=workspace.path,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            record = workspace.read("docs/adr/0001-decision-record-location.md")
            self.assertIsNotNone(record, "a non-default location should be recorded as a decision")
            self.assertIn("docs/adr", record)
            self.assertIn("status: Accepted", record)

    def test_repo_config_excludes_resolved_operator_facts(self):
        """One developer's model preference must not become a repository default."""
        with TempWorkspace() as workspace:
            home = os.path.join(workspace.path, "fake-home")
            os.makedirs(home, exist_ok=True)
            with open(os.path.join(home, "config.json"), "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "models": {"resolve": {"model": "gpt-5"}}}, handle)

            result = run_cli(
                ["init", "--yes", "--no-render"],
                workspace=workspace.path,
                env={"BEARING_HOME": home},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            written = json.loads(workspace.read(".bearing/config.json"))
            self.assertNotIn("models", written)
            self.assertIn("decisions", written)

    def test_init_is_idempotent(self):
        with TempWorkspace() as workspace:
            first = run_cli(["init", "--yes", "--no-render"], workspace=workspace.path)
            self.assertEqual(first.returncode, 0)
            index_before = workspace.read("docs/decisions/index.json")
            second = run_cli(["init", "--yes", "--no-render"], workspace=workspace.path)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(index_before, workspace.read("docs/decisions/index.json"))

    def test_gitignore_gains_run_state_entries_without_losing_existing_ones(self):
        with TempWorkspace() as workspace:
            workspace.write(".gitignore", "node_modules/\n*.log\n")
            run_cli(["init", "--yes", "--no-render"], workspace=workspace.path)
            content = workspace.read(".gitignore")
            self.assertIn("node_modules/", content)
            self.assertIn("*.log", content)
            self.assertIn(".bearing/runs/", content)
            self.assertIn(".bearing/config.local.json", content)


class PathDerivationTest(BearingTestCase):
    def test_every_path_derives_from_decisions_path(self):
        with TempWorkspace(decisions_path="docs/adr") as workspace:
            workspace.init()
            config = workspace.config()
            layout = config.layout
            self.assertTrue(layout.shadow.endswith("docs/adr/shadow"))
            self.assertTrue(layout.index.endswith("docs/adr/index.json"))
            self.assertTrue(layout.candidates.endswith("docs/adr/shadow/candidates.jsonl"))
            self.assertTrue(layout.transcripts.endswith("docs/adr/shadow/transcripts"))

    def test_local_transcript_retention_moves_them_to_a_gitignored_subdirectory(self):
        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config({"interview.transcripts.retention": "local"})
            self.assertTrue(config.layout.transcripts.endswith("shadow/transcripts/local"))

    def test_no_module_hardcodes_the_default_decisions_directory(self):
        """`docs/decisions` may appear as a default or in prose, never as logic."""
        import re

        from context import PLUGIN_ROOT

        source_dir = os.path.join(PLUGIN_ROOT, "src", "bearing")
        offenders = []
        allowed = {"paths.py", "config.py", "scaffold.py"}
        for filename in sorted(os.listdir(source_dir)):
            if not filename.endswith(".py") or filename in allowed:
                continue
            with open(os.path.join(source_dir, filename), "r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"'):
                        continue
                    if re.search(r'["\']docs/decisions', line):
                        offenders.append("%s:%d" % (filename, number))
        self.assertEqual(
            offenders,
            [],
            "these hardcode the default decisions directory instead of reading config: %s"
            % ", ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
