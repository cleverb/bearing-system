"""v0.2 decision-to-runtime boundary contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from context import BearingTestCase, PLUGIN_ROOT, SRC_ROOT, TempWorkspace, run_cli

from bearing.assessment import assess
from bearing.artifacts import projection_lock_path
from bearing.compatibility import (
    evidence_errors,
    runtime_fingerprint,
    runtime_inputs,
    valid_evidence,
    version_in_range,
)
from bearing.health import aggregate
from bearing.lint import run as lint_run
from bearing.verify import FAIL, PASS, WARN, _inference_gate_results, run as verify_run
from bearing.workspace import _normalize, effective_workspace_files


def record(scope: str, allow: bool = False, reason: str = "") -> str:
    extra = ""
    if allow:
        extra += "scope_allow_empty: true\n"
    if reason:
        extra += "scope_empty_reason: %s\n" % reason
    return (
        "---\nid: ADR-0001\nstatus: Accepted\neocr_function: Contract\n"
        "trigger: changing governed code\nscope: %s\n%s---\n\n"
        "# ADR-0001\n\n## Decision\n\nThe scoped implementation is governed.\n"
        % (scope, extra)
    )


class EffectiveWorkspaceTest(BearingTestCase):
    def test_windows_style_paths_normalize_to_workspace_relative_posix(self):
        self.assertEqual(_normalize(r"src\feature\file.py"), "src/feature/file.py")

    def test_git_defines_tracked_untracked_ignored_deleted_and_spaces(self):
        with TempWorkspace() as workspace:
            workspace.write("tracked.py", "tracked\n")
            workspace.write("deleted.py", "deleted\n")
            workspace.write("ignored.py", "ignored\n")
            workspace.write(".gitignore", "ignored.py\n")
            workspace.commit()
            os.remove(os.path.join(workspace.path, "deleted.py"))
            workspace.write("untracked file.py", "new\n")
            files = effective_workspace_files(workspace.path)
            self.assertIn("tracked.py", files)
            self.assertIn("untracked file.py", files)
            self.assertNotIn("ignored.py", files)
            self.assertNotIn("deleted.py", files)
            self.assertIn(".gitignore", files)

    def test_include_exclude_and_non_git_fallback_are_identical_filters(self):
        with TempWorkspace(git=False) as workspace:
            workspace.write("src/a.py", "a\n")
            workspace.write("src/generated/b.py", "b\n")
            workspace.write("README.md", "readme\n")
            self.assertEqual(
                effective_workspace_files(
                    workspace.path, ["src/**"], ["src/generated/**"]
                ),
                ["src/a.py"],
            )

    def test_symlink_escaping_workspace_is_not_effective(self):
        with TempWorkspace(git=False) as workspace, tempfile.TemporaryDirectory() as outside:
            target = os.path.join(outside, "secret.py")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("secret\n")
            try:
                os.symlink(target, os.path.join(workspace.path, "linked.py"))
            except OSError as error:
                self.skipTest("symlink creation unavailable: %s" % error)
            self.assertNotIn("linked.py", effective_workspace_files(workspace.path))


class ScopeIntegrityTest(BearingTestCase):
    def _findings(self, text: str, source: str = ""):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write("docs/decisions/0001-scope.md", text)
            if source:
                workspace.write("src/example.py", source)
            return lint_run(workspace.config())

    def test_intentional_empty_requires_and_surfaces_reason(self):
        missing = self._findings(record("src/future/**", allow=True))
        self.assertIn("scope-empty-reason-missing", {item.code for item in missing})
        intentional = self._findings(
            record("src/future/**", allow=True, reason="feature lands in the next release")
        )
        match = [item for item in intentional if item.code == "scope-intentionally-empty"]
        self.assertEqual(len(match), 1)
        self.assertIn("next release", match[0].message)

    def test_empty_exception_becomes_stale_and_anchor_scope_is_governing(self):
        stale = self._findings(
            record("src/**", allow=True, reason="future implementation"), "# implementation\n"
        )
        self.assertIn("scope-empty-exception-stale", {item.code for item in stale})
        outside = self._findings(record("lib/**"), "# @see " + "ADR-0001\n")
        self.assertIn("anchor-outside-contract-scope", {item.code for item in outside})


class RuntimeBoundaryTest(BearingTestCase):
    def test_fingerprint_ignores_docs_and_changes_only_relevant_runtime_input(self):
        with TempWorkspace() as workspace:
            workspace.write("plugin/.codex-plugin/plugin.json", "{}\n")
            workspace.write("plugin/src/bearing/render.py", "one\n")
            before = runtime_fingerprint("codex", workspace.path)
            workspace.write("README.md", "docs only\n")
            self.assertEqual(before, runtime_fingerprint("codex", workspace.path))
            workspace.write("plugin/src/bearing/render.py", "two\n")
            self.assertNotEqual(before, runtime_fingerprint("codex", workspace.path))

    def test_evidence_exposes_artifact_hashes_and_version_ranges(self):
        with TempWorkspace() as workspace:
            workspace.write("plugin/.codex-plugin/plugin.json", "{}\n")
            workspace.write("plugin/src/bearing/render.py", "renderer\n")
            inputs = runtime_inputs("codex", workspace.path)
            row = {
                "schema_version": 1,
                "runtime": "codex",
                "runtime_version_min": "0.140.0",
                "runtime_version_max": "0.150.0",
                "platform": "test",
                "tested_at": "2026-08-18",
                "bearing_compatibility_api": inputs["bearing_compatibility_api"],
                "renderer_version": inputs["renderer_version"],
                "config_schema_version": inputs["config_schema_version"],
                "fingerprint": runtime_fingerprint("codex", workspace.path),
                "artifacts": inputs["artifacts"],
                "checks": {
                    "install": True,
                    "skill_discovery": True,
                    "agent_acceptance": True,
                    "hook_execution": True,
                    "readonly_boundary": True,
                    "uninstall_preservation": True,
                },
                "result": "pass",
            }
            self.assertEqual(evidence_errors(row), [])
            self.assertTrue(version_in_range("codex-cli 0.148.0", row))
            self.assertFalse(version_in_range("codex-cli 0.151.0", row))
            workspace.write("conformance/evidence/codex.json", json.dumps(row))
            self.assertEqual(len(valid_evidence("codex", workspace.path)), 1)
            workspace.write("README.md", "unrelated documentation\n")
            self.assertEqual(len(valid_evidence("codex", workspace.path)), 1)
            workspace.write("plugin/src/bearing/render.py", "changed renderer\n")
            self.assertEqual(valid_evidence("codex", workspace.path), [])

    def test_claude_adapter_injects_on_read_and_retry_is_adapter_local(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write("docs/decisions/0001-scope.md", record("src/**"))
            workspace.write("src/example.py", "print('ok')\n")
            script = os.path.join(PLUGIN_ROOT, "hooks", "context_injection.py")
            env = dict(os.environ)
            env["PYTHONPATH"] = SRC_ROOT
            env["BEARING_HOME"] = os.path.join(workspace.path, "operator")

            def invoke(tool, session):
                payload = {
                    "cwd": workspace.path,
                    "session_id": session,
                    "tool_name": tool,
                    "tool_input": {"file_path": "src/example.py"},
                }
                result = subprocess.run(
                    [sys.executable, script], input=json.dumps(payload), text=True,
                    capture_output=True, env=env, check=True,
                )
                return json.loads(result.stdout)

            injected = invoke("Read", "read-first")
            self.assertIn("additionalContext", injected["hookSpecificOutput"])
            self.assertEqual(invoke("Write", "read-first"), {})
            denied = invoke("Write", "direct-write")
            self.assertEqual(
                denied["hookSpecificOutput"]["permissionDecision"], "deny"
            )
            self.assertTrue(workspace.exists(".bearing/runtime/context/direct-write.json"))

            prompt_payload = {
                "cwd": workspace.path,
                "session_id": "prompt-first",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Please update src/example.py safely.",
            }
            prompt_result = subprocess.run(
                [sys.executable, script], input=json.dumps(prompt_payload), text=True,
                capture_output=True, env=env, check=True,
            )
            early = json.loads(prompt_result.stdout)
            self.assertEqual(
                early["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
            )
            self.assertEqual(invoke("Write", "prompt-first"), {})


class ReportingAndMeasurementTest(BearingTestCase):
    def test_health_findings_are_only_lint_or_verify_results_and_exit_zero(self):
        with TempWorkspace() as workspace:
            workspace.init()
            result = aggregate(workspace.config())
            self.assertTrue(
                all(item["source"] in {"lint", "verify"} for item in result["findings"])
            )
            lint_codes = {item.code for item in lint_run(workspace.config())}
            verify_codes = {
                "%s:%s" % (item.pillar, item.name) for item in verify_run(workspace.config())
                if item.status != "ok"
            }
            for finding in result["findings"]:
                self.assertIn(
                    finding["code"],
                    lint_codes if finding["source"] == "lint" else verify_codes,
                )
            cli = run_cli(["health", "--json"], workspace=workspace.path)
            self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
            self.assertIn("descriptive_counts", json.loads(cli.stdout))

    def test_observe_updates_existing_case_and_score_accepts_legacy_case_id(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/eval/negative/cases.jsonl",
                json.dumps({"case_id": "neg-1", "expects": "no_decision"}) + "\n",
            )
            observed = run_cli(
                ["observe", "negative", "--case", "neg-1", "--observed", "no_decision"],
                workspace=workspace.path,
            )
            self.assertEqual(observed.returncode, 0, observed.stdout + observed.stderr)
            scored = run_cli(["eval", "negative", "--score"], workspace=workspace.path)
            self.assertEqual(scored.returncode, 0, scored.stdout + scored.stderr)
            self.assertEqual(json.loads(scored.stdout)["hallucination_rate"], 0.0)

    def test_ledger_add_appends_validated_rows_and_duplicate_cases_fail_scoring(self):
        with TempWorkspace() as workspace:
            workspace.init()
            row_path = workspace.write(
                "row.json", json.dumps({"run_id": "run-1", "stage": "extract"})
            )
            added = run_cli(
                ["ledger", "add", "--from-json", row_path], workspace=workspace.path
            )
            self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
            self.assertIn("run-1", workspace.read(".bearing/ledger/cost.jsonl"))
            workspace.write(
                ".bearing/eval/escalation/cases.jsonl",
                json.dumps({"id": "same", "expects": "escalate"}) + "\n"
                + json.dumps({"id": "same", "expects": "proceed"}) + "\n",
            )
            scored = run_cli(["eval", "escalation", "--score"], workspace=workspace.path)
            self.assertNotEqual(scored.returncode, 0)
            self.assertIn("duplicate id", scored.stdout)

    def test_assessment_declares_supported_ecosystem_detectors(self):
        with TempWorkspace(git=False) as workspace:
            workspace.write("pyproject.toml", "[tool.ruff]\nline-length = 100\n")
            rows = assess(workspace.config())["dimensions"]["ecosystems"]
            by_name = {row["ecosystem"]: row for row in rows}
            self.assertEqual(by_name["python"]["status"], "assessed")
            self.assertEqual(by_name["rust"]["status"], "not-assessed")


class WorkflowInspectionTest(BearingTestCase):
    def _results(self, workflow: str):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(".github/workflows/recovery.yml", workflow)
            return _inference_gate_results(workspace.config())

    def test_continue_on_error_is_step_local_and_multiline_gate_is_found(self):
        results = self._results(
            "jobs:\n  scan:\n    steps:\n"
            "      - name: harmless\n        continue-on-error: true\n"
            "        run: echo unrelated\n"
            "      - name: gating recovery\n        run: |\n"
            "          bearing eval escalation --score\n          echo complete\n"
        )
        primary = [row for row in results if row.name == "no known BEARING inference gate"][0]
        self.assertEqual(primary.status, FAIL)

    def test_non_gating_recovery_passes_and_opaque_agent_warns(self):
        non_gating = self._results(
            "jobs:\n  scan:\n    steps:\n"
            "      - name: advisory\n        continue-on-error: true\n"
            "        run: bearing eval escalation --score\n"
        )
        self.assertEqual(non_gating[0].status, PASS)
        opaque = self._results(
            "jobs:\n  scan:\n    steps:\n"
            "      - name: custom candidate recovery\n"
            "        run: codex exec custom-recovery-prompt\n"
        )
        self.assertTrue(any(row.status == WARN for row in opaque))


class ProjectionAuthorityTest(BearingTestCase):
    def test_repo_and_user_artifacts_have_separate_locks(self):
        with TempWorkspace() as workspace:
            workspace.init()
            operator = os.path.join(workspace.path, "operator")
            rendered = run_cli(
                ["render"],
                workspace=workspace.path,
                env={
                    "BEARING_HOME": operator,
                    "BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"user"',
                },
            )
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            repo = json.loads(workspace.read(".bearing/projections.lock.json"))
            os.environ["BEARING_HOME"] = operator
            user_path = projection_lock_path(workspace.path, "user")
            with open(user_path, "r", encoding="utf-8") as handle:
                user = json.load(handle)
            self.assertTrue(all(row["scope"] == "repo" for row in repo["artifacts"]))
            self.assertTrue(all(row["scope"] == "user" for row in user["artifacts"]))

    def test_check_reports_legacy_mixed_lock_without_migrating(self):
        with TempWorkspace() as workspace:
            workspace.init()
            initial = run_cli(["render"], workspace=workspace.path)
            self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
            lock = json.loads(workspace.read(".bearing/projections.lock.json"))
            lock["artifacts"].append(
                {
                    "path": "~/.codex/agents/legacy.toml",
                    "kind": "subagent",
                    "target": "codex",
                    "scope": "user",
                    "source": "legacy",
                    "sha256": "0" * 64,
                }
            )
            workspace.write(".bearing/projections.lock.json", json.dumps(lock))
            checked = run_cli(["render", "--check"], workspace=workspace.path)
            self.assertNotEqual(checked.returncode, 0)
            self.assertIn("legacy mixed lock", checked.stdout + checked.stderr)
            self.assertEqual(
                json.loads(workspace.read(".bearing/projections.lock.json"))["artifacts"][-1]["scope"],
                "user",
            )
