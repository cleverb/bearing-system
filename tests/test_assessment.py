"""`bearing assessment` is a scorecard: deterministic, always exits 0, runs without init."""

from __future__ import annotations

import json
import os
import unittest

from context import REPO_ROOT, BearingTestCase, TempWorkspace, run_cli

# Fixture lines in this file must not be treated as this repository's anchors.
_MARKER = "bearing:ignore-anchor"


def fixture(text):
    return "\n".join(line.replace(_MARKER, "").rstrip() for line in text.split("\n"))


def _assess(workspace, extra=None):
    env = {"BEARING_HOME": os.path.join(workspace.path, "fake-home")}
    return run_cli(
        ["assessment"] + list(extra or []),
        workspace=workspace.path,
        env=env,
    )


def _payload(result):
    return json.loads(result.stdout)


def _adr(number=1, title="Use Postgres"):
    return (
        "# ADR-%04d: %s\n\n"
        "* **Status:** Accepted\n\n"
        "## Context\n\nWe needed a database.\n\n"
        "## Decision\n\nPostgres.\n\n"
        "## Consequences\n\nQueries go here.\n"
    ) % (number, title)


class AssessmentScorecardTest(BearingTestCase):
    def test_empty_repo_is_unprepared_absent_and_exits_zero(self):
        with TempWorkspace() as workspace:
            result = _assess(workspace, ["--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            data = _payload(result)
            self.assertEqual(data["band"], "unprepared")
            self.assertEqual(data["bearing"], "absent")
            ids = [row["id"] for row in data["recommendations"]]
            self.assertIn("corpus-missing", ids)
            self.assertIn("bearing-uninitialized", ids)
            self.assertTrue(data["recommendations"])

    def test_numbered_records_alone_are_recorded(self):
        with TempWorkspace() as workspace:
            workspace.write("docs/adr/0001-use-postgres.md", _adr())
            data = _payload(_assess(workspace, ["--json"]))
            self.assertEqual(data["band"], "recorded")
            self.assertEqual(data["bearing"], "absent")
            self.assertEqual(data["dimensions"]["corpus"]["record_count"], 1)

    def test_nested_adr_prefixed_records_form_one_detected_corpus(self):
        with TempWorkspace() as workspace:
            workspace.write(
                "docs/decisions/auth/ADR-0004-authenticated-only-access.md",
                _adr(4, "Authenticated-only access"),
            )
            workspace.write(
                "docs/decisions/frontend/ADR-0012-family-members-admin.md",
                _adr(12, "Family members admin"),
            )
            data = _payload(_assess(workspace, ["--json"]))
            corpus = data["dimensions"]["corpus"]
            self.assertEqual(data["band"], "recorded")
            self.assertEqual(corpus["status"], "present")
            self.assertEqual(corpus["record_count"], 2)
            self.assertEqual(corpus["path"], "docs/decisions")
            self.assertNotIn(
                "corpus-missing", [row["id"] for row in data["recommendations"]]
            )

    def test_agents_md_naming_the_corpus_is_discoverable(self):
        with TempWorkspace() as workspace:
            workspace.write("docs/adr/0001-use-postgres.md", _adr())
            workspace.write(
                "AGENTS.md",
                "# Agents\n\nLoad docs/adr before changing storage code.\n",
            )
            data = _payload(_assess(workspace, ["--json"]))
            self.assertEqual(data["band"], "discoverable")

    def test_see_annotation_with_discovery_is_anchored(self):
        with TempWorkspace() as workspace:
            workspace.write("docs/adr/0001-use-postgres.md", _adr())
            workspace.write(
                "AGENTS.md",
                "# Agents\n\nLoad docs/adr before changing storage code.\n",
            )
            workspace.write(
                "src/app.py",
                fixture("# @see ADR-0001  " + _MARKER + "\n\ndef main():\n    pass\n"),
            )
            data = _payload(_assess(workspace, ["--json"]))
            self.assertEqual(data["band"], "anchored")
            self.assertGreaterEqual(data["dimensions"]["anchors"]["count"], 1)

    def test_pr_template_mentioning_adr_is_review_aware(self):
        with TempWorkspace() as workspace:
            workspace.write("docs/adr/0001-use-postgres.md", _adr())
            workspace.write(
                "AGENTS.md",
                "# Agents\n\nLoad docs/adr before changing storage code.\n",
            )
            workspace.write(
                "src/app.py",
                fixture("# @see ADR-0001  " + _MARKER + "\n\ndef main():\n    pass\n"),
            )
            workspace.write(
                ".github/PULL_REQUEST_TEMPLATE.md",
                "## Summary\n\nLink the ADR if this change implements one.\n",
            )
            data = _payload(_assess(workspace, ["--json"]))
            self.assertEqual(data["band"], "review-aware")

    def test_pmd_complexity_rules_are_detected_when_not_surfaced(self):
        with TempWorkspace() as workspace:
            workspace.write(
                "build.gradle",
                "pmd {\n  ruleSets = []\n"
                "  ruleSetFiles = files('./config/pmdrules.xml')\n}\n",
            )
            workspace.write(
                "config/pmdrules.xml",
                """<?xml version="1.0"?>
<ruleset xmlns="http://pmd.sourceforge.net/ruleset/2.0.0" name="Project rules">
  <rule ref="category/java/design.xml/CyclomaticComplexity">
    <properties>
      <property name="methodReportLevel" value="10"/>
      <property name="classReportLevel" value="40"/>
    </properties>
  </rule>
</ruleset>
""",
            )
            data = _payload(_assess(workspace, ["--json"]))
            quality = data["dimensions"]["build_quality_contracts"]
            self.assertEqual(quality["status"], "absent")
            self.assertEqual(quality["configured_count"], 1)
            self.assertEqual(quality["files"][0]["tool"], "pmd")
            self.assertEqual(
                quality["files"][0]["consequential_rules"], ["CyclomaticComplexity"]
            )
            self.assertEqual(
                quality["files"][0]["rules"][0]["properties"]["methodReportLevel"],
                "10",
            )
            self.assertIn(
                "build-rules-unsurfaced", [row["id"] for row in data["recommendations"]]
            )
            recommendation = next(
                row["text"] for row in data["recommendations"]
                if row["id"] == "build-rules-unsurfaced"
            )
            self.assertIn("decision ancestry", recommendation)
            self.assertIn("not as decisions inferred", recommendation)
            rendered = _assess(workspace)
            self.assertIn("## Build quality evidence", rendered.stdout)
            self.assertIn("CyclomaticComplexity", rendered.stdout)
            self.assertIn("methodReportLevel=10", rendered.stdout)
            self.assertIn("evidence: gradle-selected", rendered.stdout)

    def test_unwired_pmd_xml_is_evidence_but_not_an_active_contract(self):
        with TempWorkspace() as workspace:
            workspace.write(
                "config/pmdrules.xml",
                """<ruleset xmlns="http://pmd.sourceforge.net/ruleset/2.0.0" name="Rules">
<rule ref="category/java/design.xml/CyclomaticComplexity">
<properties><property name="methodReportLevel" value="17"/></properties>
</rule></ruleset>""",
            )

            data = _payload(_assess(workspace, ["--json"]))
            quality = data["dimensions"]["build_quality_contracts"]
            self.assertEqual(quality["status"], "partial")
            self.assertEqual(quality["evidence_count"], 1)
            self.assertEqual(quality["configured_count"], 0)
            self.assertEqual(quality["unwired_count"], 1)
            self.assertEqual(quality["files"][0]["evidence"], "file-only")
            ids = [row["id"] for row in data["recommendations"]]
            self.assertIn("build-rules-unwired", ids)
            self.assertNotIn("build-rules-unsurfaced", ids)

    def test_naming_the_pmd_ruleset_surfaces_it_before_generation(self):
        with TempWorkspace() as workspace:
            workspace.write(
                "build.gradle",
                "pmd { ruleSetFiles = files('./config/pmdrules.xml') }\n",
            )
            workspace.write(
                "config/pmdrules.xml",
                """<ruleset xmlns="http://pmd.sourceforge.net/ruleset/2.0.0" name="Rules">
<rule ref="category/java/design.xml/CyclomaticComplexity">
<properties><property name="methodReportLevel" value="10"/></properties>
</rule></ruleset>""",
            )
            workspace.write(
                "AGENTS.md",
                "Before changing Java, load config/pmdrules.xml. "
                "Cyclomatic complexity methodReportLevel is 10.\n",
            )
            data = _payload(_assess(workspace, ["--json"]))
            quality = data["dimensions"]["build_quality_contracts"]
            self.assertEqual(quality["status"], "present")
            self.assertEqual(quality["surfaced_count"], 1)
            self.assertNotIn(
                "build-rules-unsurfaced", [row["id"] for row in data["recommendations"]]
            )

    def test_unsurfaced_build_contracts_cap_the_readiness_band(self):
        with TempWorkspace() as workspace:
            workspace.write("docs/adr/0001-use-postgres.md", _adr())
            workspace.write("src/app.py", fixture("# @see ADR-0001  " + _MARKER + "\n"))
            workspace.write(
                ".github/PULL_REQUEST_TEMPLATE.md", "Link the ADR for governed changes.\n"
            )
            workspace.write(
                "build.gradle", "pmd { ruleSetFiles = files('config/pmdrules.xml') }\n"
            )
            workspace.write(
                "config/pmdrules.xml",
                "<ruleset><rule ref=\"category/java/design.xml/CyclomaticComplexity\"/>"
                "</ruleset>",
            )
            workspace.write("AGENTS.md", "Load docs/adr before changing governed code.\n")
            hidden = _payload(_assess(workspace, ["--json"]))
            self.assertEqual(hidden["band"], "anchored")

            workspace.write(
                "AGENTS.md",
                "Load docs/adr and config/pmdrules.xml before changing Java code.\n",
            )
            surfaced = _payload(_assess(workspace, ["--json"]))
            self.assertEqual(surfaced["band"], "review-aware")

    def test_checkstyle_config_and_check_only_guidance_are_partial(self):
        with TempWorkspace() as workspace:
            workspace.write(
                "build.gradle",
                "checkstyle { configFile = file('./config/checkstyle.xml') }\n",
            )
            workspace.write(
                "config/checkstyle.xml",
                """<!DOCTYPE module PUBLIC "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
"https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker"><module name="TreeWalker"><module name="LineLength">
<property name="max" value="100"/></module></module></module>""",
            )
            workspace.write("AGENTS.md", "Before handoff, run ./gradlew check.\n")
            data = _payload(_assess(workspace, ["--json"]))
            quality = data["dimensions"]["build_quality_contracts"]
            self.assertEqual(quality["status"], "partial")
            self.assertTrue(quality["agent_check_guidance"])
            self.assertEqual(quality["files"][0]["tool"], "checkstyle")

    def test_missing_gradle_ruleset_is_reported(self):
        with TempWorkspace() as workspace:
            workspace.write(
                "build.gradle",
                "pmd { ruleSetFiles = files('./config/missing-pmd.xml') }\n",
            )
            data = _payload(_assess(workspace, ["--json"]))
            quality = data["dimensions"]["build_quality_contracts"]
            self.assertEqual(quality["missing_count"], 1)
            self.assertIn(
                "build-rules-missing", [row["id"] for row in data["recommendations"]]
            )

    def test_checkstyle_conventional_location_is_discovered(self):
        with TempWorkspace() as workspace:
            workspace.write("build.gradle", "plugins { id 'checkstyle' }\n")
            workspace.write(
                "config/checkstyle/checkstyle.xml",
                "<module name=\"Checker\"><module name=\"TreeWalker\">"
                "<module name=\"MethodLength\"><property name=\"max\" value=\"80\"/>"
                "</module></module></module>",
            )
            data = _payload(_assess(workspace, ["--json"]))
            quality = data["dimensions"]["build_quality_contracts"]
            self.assertEqual(quality["configured_count"], 1)
            self.assertEqual(
                quality["files"][0]["path"], "config/checkstyle/checkstyle.xml"
            )
            self.assertEqual(
                quality["files"][0]["consequential_rules"], ["MethodLength"]
            )

    def test_this_checkout_is_review_aware_and_projected(self):
        result = run_cli(["assessment", "--json"], workspace=REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = _payload(result)
        self.assertEqual(data["band"], "review-aware")
        self.assertEqual(data["bearing"], "projected")
        self.assertIn("band", data)
        self.assertIn("bearing", data)
        self.assertIn("recommendations", data)

    def test_human_output_states_it_always_exits_zero(self):
        with TempWorkspace() as workspace:
            result = _assess(workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("always exits 0", result.stdout)
            self.assertIn("Readiness: unprepared", result.stdout)
            self.assertIn("BEARING:", result.stdout)

    def test_json_shape_on_uninitialized_repo(self):
        with TempWorkspace() as workspace:
            result = _assess(workspace, ["--json"])
            self.assertEqual(result.returncode, 0)
            data = _payload(result)
            self.assertFalse(data["initialized"])
            self.assertIsInstance(data["recommendations"], list)
            self.assertIsInstance(data["findings"], list)


if __name__ == "__main__":
    unittest.main()
