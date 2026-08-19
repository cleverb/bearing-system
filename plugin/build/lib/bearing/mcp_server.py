"""Minimal stdio MCP server for candidate disposition with form elicitation.

No third-party MCP SDK — the CLI stays dependency-free (ADR-0005). This module
speaks enough JSON-RPC for Cursor to list tools, call them, and answer
`elicitation/create` forms.

Tools:
  - list_reviewable — queue of surfaced shadow candidates
  - review_candidate — elicit Promote|Edit|Split|Reject|Defer, then dispose

BEARING permits one-click execution of human judgment; Promote still requires
scope, present validity, authored lifecycle, and EOCR function in the form.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional, TextIO

from . import __version__
from .config import resolve
from .disposition import (
    ACTIONS,
    Judgment,
    candidate_brief,
    dispose,
    elicitation_schema,
    find_candidate,
    list_reviewable,
)
from .util import BearingError

PROTOCOL_VERSION = "2025-06-18"


class McpServer:
    def __init__(
        self,
        workspace: Optional[str] = None,
        stdin: Optional[TextIO] = None,
        stdout: Optional[TextIO] = None,
    ) -> None:
        self.workspace = workspace
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self._next_id = 1
        self._initialized = False

    def run(self) -> int:
        while True:
            line = self.stdin.readline()
            if line == "":
                return 0
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                self._write(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "parse error: %s" % exc},
                    }
                )
                continue
            self._dispatch_message(message)

    def _dispatch_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle one inbound JSON-RPC message. Returns a matched response when nesting."""
        if "method" not in message:
            return message  # response to a server request (elicitation)

        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method == "notifications/initialized":
            self._initialized = True
            return None

        if msg_id is None:
            return None  # other notifications

        try:
            result = self._dispatch(method, params)
            self._write({"jsonrpc": "2.0", "id": msg_id, "result": result})
        except BearingError as exc:
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32000, "message": str(exc)},
                }
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32603, "message": "internal error: %s" % exc},
                }
            )
        return None

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "elicitation": {"form": {}},
                },
                "serverInfo": {"name": "bearing", "version": __version__},
                "instructions": (
                    "Dispose shadow candidates via review_candidate. "
                    "Promote requires human judgment fields; confidence alone is not enough."
                ),
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self._tool_defs()}
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            return self._call_tool(str(name), arguments if isinstance(arguments, dict) else {})
        raise BearingError("method not found: %s" % method)

    def _tool_defs(self) -> list:
        return [
            {
                "name": "list_reviewable",
                "description": (
                    "List surfaced shadow candidates waiting on human disposition "
                    "(Promote / Edit / Split / Reject / Defer)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace root; defaults to process cwd / BEARING_WORKSPACE.",
                        }
                    },
                },
            },
            {
                "name": "review_candidate",
                "description": (
                    "Review one shadow candidate. Elicits a disposition form "
                    "(Promote|Edit|Split|Reject|Defer). Promote requires still_valid, "
                    "eocr_function, lifecycle_state, and scope — one-click execution of "
                    "judgment, not ceremonial confidence-approve."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {
                            "type": "string",
                            "description": "Shadow candidate id, e.g. CAND-20260818-auth-lock-defer",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace root.",
                        },
                        "skip_elicit": {
                            "type": "boolean",
                            "description": (
                                "If true, use `disposition` arguments directly "
                                "(for hosts without elicitation). Default false."
                            ),
                        },
                        "disposition": {
                            "type": "object",
                            "description": "Pre-filled disposition when skip_elicit is true.",
                        },
                    },
                    "required": ["candidate_id"],
                },
            },
        ]

    def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace = arguments.get("workspace") or self.workspace
        config = resolve(workspace=workspace if workspace else None)
        config.require_initialized()

        if name == "list_reviewable":
            rows = list_reviewable(config.layout)
            summary = [
                {
                    "candidate_id": row.get("candidate_id"),
                    "subject": row.get("subject"),
                    "candidate_object": row.get("candidate_object"),
                    "candidate_eocr_function": row.get("candidate_eocr_function"),
                    "confidence": row.get("confidence"),
                    "lifecycle_state": row.get("lifecycle_state"),
                }
                for row in rows
            ]
            return _tool_text(json.dumps(summary, indent=2, sort_keys=True))

        if name == "review_candidate":
            candidate_id = str(arguments.get("candidate_id") or "").strip()
            if not candidate_id:
                raise BearingError("candidate_id is required")
            candidate = find_candidate(config.layout, candidate_id)
            brief = candidate_brief(candidate)
            schema = elicitation_schema(candidate)

            if arguments.get("skip_elicit"):
                content = arguments.get("disposition") or {}
                if not isinstance(content, dict):
                    raise BearingError("disposition must be an object when skip_elicit is true")
            else:
                elicit = self._elicit(
                    message=(
                        "Dispose this shadow candidate. Promote executes human judgment "
                        "(scope, validity, lifecycle, EOCR) — it does not approve confidence.\n\n"
                        "%s"
                    )
                    % brief,
                    schema=schema,
                )
                if elicit is None:
                    return _tool_text("Elicitation declined or cancelled; no changes written.")
                content = elicit

            action = str(content.get("action") or "").strip()
            if action not in ACTIONS and action.lower() not in {a.lower() for a in ACTIONS}:
                raise BearingError("form must include action in %s" % ", ".join(ACTIONS))
            result = dispose(config, candidate_id, action, Judgment.from_mapping(content))
            return _tool_text(json.dumps(result.as_dict(), indent=2, sort_keys=True))

        raise BearingError("unknown tool: %s" % name)

    def _elicit(self, message: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send elicitation/create and keep reading stdin until that id responds.

        Must nest-read: a blocking wait without reading would deadlock the stdio
        transport (the client's form answer arrives on the same stream).
        """
        req_id = self._alloc_id()
        self._write(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "elicitation/create",
                "params": {
                    "mode": "form",
                    "message": message,
                    "requestedSchema": schema,
                },
            }
        )
        while True:
            line = self.stdin.readline()
            if line == "":
                raise BearingError("stdin closed while waiting for elicitation")
            line = line.strip()
            if not line:
                continue
            try:
                inbound = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BearingError("invalid JSON while awaiting elicitation: %s" % exc)
            # Nested client request while we wait — answer it, then keep waiting.
            if "method" in inbound:
                self._dispatch_message(inbound)
                continue
            if inbound.get("id") != req_id:
                # Unrelated response; ignore and keep waiting for ours.
                continue
            if inbound.get("error"):
                err = inbound["error"]
                raise BearingError(
                    "elicitation failed: %s"
                    % (err.get("message") if isinstance(err, dict) else err)
                )
            result = inbound.get("result") or {}
            action = result.get("action")
            if action in ("decline", "cancel"):
                return None
            content = result.get("content")
            return content if isinstance(content, dict) else {}

    def _alloc_id(self) -> int:
        req_id = self._next_id
        self._next_id += 1
        return req_id

    def _write(self, message: Dict[str, Any]) -> None:
        self.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.stdout.flush()


def _tool_text(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def main(argv: Optional[list] = None) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="bearing-mcp", description="BEARING MCP disposition server")
    parser.add_argument(
        "-C",
        "--workspace",
        default=os.environ.get("BEARING_WORKSPACE"),
        help="default workspace for tools",
    )
    args = parser.parse_args(argv)
    return McpServer(workspace=args.workspace).run()


if __name__ == "__main__":
    sys.exit(main())
