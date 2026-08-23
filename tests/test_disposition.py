"""Candidate disposition: Promote requires judgment; Reject/Defer/Edit/Split work."""

from __future__ import annotations

import io
import json
import unittest

from context import BearingTestCase, TempWorkspace, run_cli
from bearing.disposition import Judgment, dispose, list_reviewable
from bearing.mcp_server import McpServer
from bearing.util import BearingError


def _parse_mcp_frames(raw):
    """Decode NDJSON or Content-Length MCP replies from a byte string."""
    data = raw if isinstance(raw, (bytes, bytearray)) else raw.encode("utf-8")
    replies = []
    i = 0
    while i < len(data):
        if data[i : i + 1] in (b"\n", b"\r", b" "):
            i += 1
            continue
        if data[i : i + 1] == b"{":
            nl = data.find(b"\n", i)
            chunk = data[i:] if nl < 0 else data[i:nl]
            replies.append(json.loads(chunk))
            i = len(data) if nl < 0 else nl + 1
            continue
        sep = data.find(b"\r\n\r\n", i)
        header_end = 4
        if sep < 0:
            sep = data.find(b"\n\n", i)
            header_end = 2
        if sep < 0:
            break
        length = 0
        for line in data[i:sep].split(b"\n"):
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1])
        i = sep + header_end
        replies.append(json.loads(data[i : i + length]))
        i += length
    return replies


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
            self.assertNotIn("_meta", listed)
            self.assertIn("structuredContent", listed)
            self.assertEqual(listed["structuredContent"]["count"], 1)
            self.assertIn("CAND-001", listed["structuredContent"]["candidates"][0]["candidate_id"])
            self.assertIn("CAND-001", server._queue_html or "")

            server._host_supports_ui = True
            listed_ui = server._call_tool("list_reviewable", {})
            self.assertEqual(
                listed_ui["_meta"]["ui"]["resourceUri"], "ui://bearing/reviewable-queue"
            )
            self.assertNotIn("CAND-001", listed_ui["content"][0]["text"])

    def test_list_reviewable_ui_host_uses_minimal_model_text(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            server = McpServer(workspace=ws.path)
            server._host_supports_ui = True
            listed = server._call_tool("list_reviewable", {})
            text = listed["content"][0]["text"]
            self.assertNotIn("CAND-001", text)
            self.assertIn("MCP App", text)
            self.assertIn("do not list", text.lower())
            self.assertEqual(listed["structuredContent"]["count"], 1)
            self.assertIn("_meta", listed)

    def test_list_reviewable_fallback_includes_candidate_json(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            server = McpServer(workspace=ws.path)
            server._host_supports_ui = False
            listed = server._call_tool("list_reviewable", {})
            text = listed["content"][0]["text"]
            self.assertIn("CAND-001", text)
            self.assertNotIn("_meta", listed)

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

    def test_initialize_handshake_answers_cursor_follow_ups(self):
        with TempWorkspace() as ws:
            ws.init()
            stdin = io.StringIO(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "cursor", "version": "1"},
                        },
                    }
                )
                + "\n"
                + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
                + "\n"
                + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                + "\n"
                + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
                + "\n"
                + json.dumps({"jsonrpc": "2.0", "id": 4, "method": "prompts/list"})
                + "\n"
            )
            stdout = io.StringIO()
            server = McpServer(workspace=ws.path, stdin=stdin, stdout=stdout)
            self.assertEqual(server.run(), 0)
            replies = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            by_id = {row["id"]: row for row in replies}
            self.assertEqual(by_id[1]["result"]["protocolVersion"], "2024-11-05")
            resources_cap = by_id[1]["result"]["capabilities"]["resources"]
            self.assertTrue(resources_cap.get("subscribe"))
            self.assertTrue(resources_cap.get("listChanged"))
            self.assertTrue(server._host_supports_ui)
            names = [tool["name"] for tool in by_id[2]["result"]["tools"]]
            self.assertEqual(names, ["list_reviewable", "review_candidate"])
            tools_by_name = {tool["name"]: tool for tool in by_id[2]["result"]["tools"]}
            self.assertEqual(
                tools_by_name["list_reviewable"]["_meta"]["ui"]["resourceUri"],
                "ui://bearing/reviewable-queue",
            )
            resources = by_id[3]["result"]["resources"]
            self.assertEqual(len(resources), 1)
            self.assertEqual(resources[0]["uri"], "ui://bearing/reviewable-queue")
            self.assertEqual(resources[0]["mimeType"], "text/html;profile=mcp-app")
            self.assertEqual(by_id[4]["result"], {"prompts": []})

    def test_resources_read_returns_mcp_app_html(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            server = McpServer(workspace=ws.path)
            server._call_tool("list_reviewable", {})
            result = server._read_resource("ui://bearing/reviewable-queue")
            content = result["contents"][0]
            self.assertEqual(content["mimeType"], "text/html;profile=mcp-app")
            self.assertIn("CAND-001", content["text"])
            self.assertIn("list_reviewable", content["text"])
            self.assertIn("review_candidate", content["text"])
            self.assertIn("profile=mcp-app", content["mimeType"])

    def test_resources_subscribe_and_update_notification(self):
        with TempWorkspace() as ws:
            ws.init()
            ws.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(_candidate()) + "\n",
            )
            server = McpServer(workspace=ws.path)
            server._dispatch("resources/subscribe", {"uri": "ui://bearing/reviewable-queue"})
            server._call_tool("list_reviewable", {})
            self.assertIn("ui://bearing/reviewable-queue", server._subscribed)

    def test_content_length_framing_without_trailing_newline(self):
        """Hosts often send LSP frames whose body has no trailing newline."""
        with TempWorkspace() as ws:
            ws.init()
            initialize = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "cursor", "version": "1"},
                    },
                }
            ).encode("utf-8")
            ping = json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "ping"}
            ).encode("utf-8")
            payload = (
                ("Content-Length: %d\r\n\r\n" % len(initialize)).encode("ascii")
                + initialize
                + ("Content-Length: %d\r\n\r\n" % len(ping)).encode("ascii")
                + ping
            )
            stdin = io.BytesIO(payload)
            stdout = io.BytesIO()

            class _BinaryStdio:
                def __init__(self, buf):
                    self.buffer = buf

                def flush(self):
                    self.buffer.flush()

            server = McpServer(
                workspace=ws.path,
                stdin=_BinaryStdio(stdin),
                stdout=_BinaryStdio(stdout),
            )
            self.assertEqual(server.run(), 0)
            replies = _parse_mcp_frames(stdout.getvalue())
            by_id = {row["id"]: row for row in replies}
            self.assertEqual(by_id[1]["result"]["protocolVersion"], "2025-06-18")
            self.assertEqual(by_id[2]["result"], {})
            self.assertTrue(replies[0].get("jsonrpc"))
            self.assertIn(b"Content-Length:", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
