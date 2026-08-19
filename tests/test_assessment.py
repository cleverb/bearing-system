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
