"""Candidate disposition: Promote requires judgment; Reject/Defer/Edit/Split work."""

from __future__ import annotations

import json
import unittest

from context import BearingTestCase, TempWorkspace, run_cli
from bearing.disposition import Judgment, dispose, list_reviewable
from bearing.mcp_server import McpServer
from bearing.util import BearingError


def _candidate(**fields):
    row = {
        "candidate_id": "CAND-001",
        "subject": "src/payments/retry.py",
        "candidate_relation": "governed_by",
        "candidate_object": "payment retries MUST use exponential backoff",
        "candidate_eocr_function": "Contract",
        "evidence": [
            {
                "evidence_source": "commit_message",
                "evidence_excerpt": "use exponential backoff for payment retries",
                "evidence_reliability": "HIGH",
            }
        ],
        "confidence": "HIGH",
        "lifecycle_state": "Reviewable",
        "idempotency_key": "src/payments/retry.py@corpus-1@extractor-1",
        "evidence_fingerprint": "fp-retry-backoff-1",
    }
    row.update(fields)
    return row


class DispositionPromoteTest(BearingTestCase):
    def test_promote_refuses_without_judgment_fields(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            config = ws.config()
            with self.assertRaises(BearingError) as ctx:
                dispose(config, "CAND-001", "Promote", Judgment())
            self.assertIn("still_valid", str(ctx.exception))

    def test_promote_refuses_ceremonial_still_valid_false(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            config = ws.config()
            with self.assertRaises(BearingError):
                dispose(
                    config,
                    "CAND-001",
                    "Promote",
                    Judgment(
                        still_valid=False,
                        eocr_function="Contract",
                        lifecycle_state="Accepted",
                        scope="src/payments/**",
                    ),
                )

    def test_promote_scaffolds_adr_and_marks_promoted(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            config = ws.config()
            result = dispose(
                config,
                "CAND-001",
                "Promote",
                Judgment(
                    still_valid=True,
                    eocr_function="Contract",
                    lifecycle_state="Accepted",
                    scope="src/payments/**",
                    title="Payment retry backoff",
                    trigger="changing payment retry behavior",
                    anchor_targets=["src/payments/retry.py"],
                ),
            )
            self.assertEqual(result.action, "Promote")
            self.assertTrue(result.promoted_to.startswith("ADR-"))
            self.assertTrue(ws.exists(result.adr_path))
            text = ws.read(result.adr_path)
            self.assertIn("status: Accepted", text)
            self.assertIn("eocr_function: Contract", text)
            self.assertIn("scope: src/payments/**", text)
            candidates = [
                json.loads(line)
                for line in ws.read("docs/decisions/shadow/candidates.jsonl").splitlines()
                if line.strip()
            ]
            self.assertEqual(candidates[0]["lifecycle_state"], "Promoted")
            self.assertEqual(candidates[0]["promoted_to"], result.promoted_to)
            self.assertEqual(list_reviewable(config.layout), [])

    def test_dispose_cli_promote(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            result = run_cli(
                [
                    "dispose",
                    "--id",
                    "CAND-001",
                    "--action",
                    "Promote",
                    "--still-valid",
                    "1",
                    "--eocr",
                    "Contract",
                    "--scope",
                    "src/payments/**",
                    "--status",
                    "Accepted",
                    "--title",
                    "Payment retry backoff",
                    "--json",
                ],
                workspace=ws.path,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["action"], "Promote")
            self.assertTrue(ws.exists(payload["adr_path"]))

    def test_dispose_cli_refuses_promote_without_still_valid(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            result = run_cli(
                [
                    "dispose",
                    "--id",
                    "CAND-001",
                    "--action",
                    "Promote",
                    "--eocr",
                    "Contract",
                    "--scope",
                    "src/payments/**",
                ],
                workspace=ws.path,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("still_valid", result.stderr)


class DispositionOtherActionsTest(BearingTestCase):
    def test_reject_writes_fingerprint_ledger(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            config = ws.config()
            dispose(
                config,
                "CAND-001",
                "Reject",
                Judgment(rejection_reason="not a real decision"),
            )
            rejected = [
                json.loads(line)
                for line in ws.read("docs/decisions/shadow/rejected.jsonl").splitlines()
                if line.strip()
            ]
            self.assertEqual(rejected[0]["rejected_evidence_fingerprint"], "fp-retry-backoff-1")
            candidates = [
                json.loads(line)
                for line in ws.read("docs/decisions/shadow/candidates.jsonl").splitlines()
                if line.strip()
            ]
            self.assertEqual(candidates[0]["lifecycle_state"], "Rejected")

    def test_defer_keeps_reviewable(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            config = ws.config()
            dispose(config, "CAND-001", "Defer", Judgment(defer_note="next sprint"))
            candidates = [
                json.loads(line)
                for line in ws.read("docs/decisions/shadow/candidates.jsonl").splitlines()
                if line.strip()
            ]
            self.assertEqual(candidates[0]["lifecycle_state"], "Reviewable")
            self.assertEqual(candidates[0]["disposition_note"], "next sprint")
            self.assertEqual(len(list_reviewable(config.layout)), 1)

    def test_edit_revises_object(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            config = ws.config()
            dispose(
                config,
                "CAND-001",
                "Edit",
                Judgment(edit_object="retries MUST use jittered exponential backoff"),
            )
            candidates = [
                json.loads(line)
                for line in ws.read("docs/decisions/shadow/candidates.jsonl").splitlines()
                if line.strip()
            ]
            self.assertIn("jittered", candidates[0]["candidate_object"])

    def test_review_json_lists_queue(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            result = run_cli(["review", "--json"], workspace=ws.path)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = json.loads(result.stdout)
            self.assertEqual(rows[0]["candidate_id"], "CAND-001")


class McpDispositionTest(BearingTestCase):
    def test_list_and_review_with_disposition(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            server = McpServer(workspace=ws.path)
            listed = server._call_tool("list_reviewable", {})
            text = listed["content"][0]["text"]
            self.assertIn("CAND-001", text)

            reviewed = server._call_tool(
                "review_candidate",
                {
                    "candidate_id": "CAND-001",
                    "disposition": {
                        "action": "Reject",
                        "rejection_reason": "duplicate",
                    },
                },
            )
            payload = json.loads(reviewed["content"][0]["text"])
            self.assertEqual(payload["action"], "Reject")
            self.assertIn("Rejected", ws.read("docs/decisions/shadow/candidates.jsonl"))

    def test_review_without_disposition_does_not_block(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            server = McpServer(workspace=ws.path)
            reviewed = server._call_tool(
                "review_candidate",
                {"candidate_id": "CAND-001"},
            )
            payload = json.loads(reviewed["content"][0]["text"])
            self.assertEqual(payload["status"], "needs_disposition")
            self.assertIn("schema", payload)
            # Candidate unchanged — no hang, no write.
            self.assertIn("Reviewable", ws.read("docs/decisions/shadow/candidates.jsonl"))


if __name__ == "__main__":
    unittest.main()
