"""Minimal stdio MCP server for candidate disposition.

No third-party MCP SDK — the CLI stays dependency-free (ADR-0005).

Tools:
  - list_reviewable — queue of surfaced shadow candidates (MCP App board)
  - review_candidate — dispose Promote|Edit|Split|Reject|Defer

`list_reviewable` returns an MCP App (`ui://bearing/reviewable-queue`) so
hosts that support Apps can render the queue. The board is read-only:
viewing is not disposition. Promote still requires judgment fields on
`review_candidate`. Progressive enhancement: JSON text is always returned.

Important: this server does **not** block on MCP elicitation by default.
Server-initiated `elicitation/create` mid-`tools/call` hangs many Cursor
builds when the form UI never completes the round-trip, which freezes the
agent loop and looks like “Skills autocomplete is broken.” Judgment is
collected as tool arguments (or via `bearing review` / chat) instead.
Optional `elicit: true` remains for hosts that fully support forms.
"""

from __future__ import annotations

import html as html_lib
import json
import sys
from typing import Any, Dict, List, Optional, TextIO

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
REVIEWABLE_UI_URI = "ui://bearing/reviewable-queue"
REVIEWABLE_UI_MIME = "text/html;profile=mcp-app"


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
        self._use_content_length = False
        self._queue_html: Optional[str] = None

    def run(self) -> int:
        while True:
            try:
                message = self._read_message()
            except Exception as exc:
                _log("bearing-mcp parse error: %s" % exc)
                continue
            if message is None:
                return 0
            try:
                self._dispatch_message(message)
            except Exception as exc:  # pragma: no cover - defensive
                _log("bearing-mcp error: %s" % exc)

    def _read_message(self) -> Optional[Dict[str, Any]]:
        """Read one JSON-RPC message: NDJSON or LSP Content-Length framing.

        Cursor and other hosts may use either. The body after Content-Length is
        exactly N bytes and often has no trailing newline; readline() waits
        forever on a live pipe in that case. Reply using the same framing.
        """
        first = self._readline()
        if first == b"":
            return None
        stripped = first.lstrip()
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            self._use_content_length = False
            message = json.loads(first.decode("utf-8"))
            return message if isinstance(message, dict) else None

        headers = {}
        line = first
        while line not in (b"", b"\n", b"\r\n"):
            if b":" in line:
                key, value = line.decode("utf-8").split(":", 1)
                headers[key.strip().lower()] = value.strip()
            line = self._readline()
            if line == b"":
                break

        length = int(headers.get("content-length", "0"))
        body = self._read_exact(length)
        self._use_content_length = True
        message = json.loads(body.decode("utf-8"))
        return message if isinstance(message, dict) else None

    def _dispatch_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle one inbound JSON-RPC message. Returns a matched response when nesting."""
        if "method" not in message:
            return message  # response to a server request (elicitation)

        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method in ("notifications/initialized", "initialized"):
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
            # Echo the client's version when present. A fixed newer version can
            # leave Cursor waiting on initialize, which shows as Skills "loading".
            requested = params.get("protocolVersion") or PROTOCOL_VERSION
            if not isinstance(requested, str) or not requested.strip():
                requested = PROTOCOL_VERSION
            return {
                "protocolVersion": requested.strip(),
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {},
                },
                "serverInfo": {"name": "bearing", "version": __version__},
                "instructions": (
                    "Dispose shadow candidates via review_candidate with a disposition "
                    "object (action + judgment fields). Do not rely on form elicitation. "
                    "Promote requires still_valid, eocr_function, lifecycle_state, scope."
                ),
            }
        if method == "ping":
            return {}
        if method == "logging/setLevel":
            return {}
        if method == "tools/list":
            return {"tools": self._tool_defs()}
        if method == "resources/list":
            return {"resources": self._resource_defs()}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "resources/read":
            return self._read_resource(str(params.get("uri") or ""))
        if method == "prompts/list":
            return {"prompts": []}
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
                    "(Promote / Edit / Split / Reject / Defer). Renders an MCP App "
                    "review board in hosts that support Apps; JSON is always returned."
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
                "_meta": {"ui": {"resourceUri": REVIEWABLE_UI_URI}},
            },
            {
                "name": "review_candidate",
                "description": (
                    "Review one shadow candidate. Pass disposition "
                    "{action, still_valid, eocr_function, lifecycle_state, scope, ...}. "
                    "If disposition is omitted, returns the evidence brief and form schema "
                    "without blocking. Promote requires human judgment fields — not confidence."
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
                        "disposition": {
                            "type": "object",
                            "description": (
                                "Human disposition. Required to write changes. "
                                "Keys: action (Promote|Edit|Split|Reject|Defer), "
                                "still_valid, eocr_function, lifecycle_state, scope, ..."
                            ),
                        },
                        "elicit": {
                            "type": "boolean",
                            "description": (
                                "If true, attempt MCP form elicitation. Default false — "
                                "elicitation hangs on some Cursor builds."
                            ),
                            "default": False,
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
            if arguments.get("workspace"):
                self.workspace = str(arguments.get("workspace"))
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
            self._queue_html = reviewable_queue_html(rows, workspace=config.workspace)
            return _tool_text(
                json.dumps(summary, indent=2, sort_keys=True),
                ui_resource=REVIEWABLE_UI_URI,
            )

        if name == "review_candidate":
            candidate_id = str(arguments.get("candidate_id") or "").strip()
            if not candidate_id:
                raise BearingError("candidate_id is required")
            candidate = find_candidate(config.layout, candidate_id)
            brief = candidate_brief(candidate)
            schema = elicitation_schema(candidate)

            content = arguments.get("disposition")
            if content is None and arguments.get("skip_elicit"):
                # Backward-compatible alias from the first MCP revision.
                content = {}
            if not isinstance(content, dict) or not content.get("action"):
                if arguments.get("elicit"):
                    content = self._elicit(
                        message=(
                            "Dispose this shadow candidate. Promote executes human judgment "
                            "(scope, validity, lifecycle, EOCR) — it does not approve confidence.\n\n"
                            "%s"
                        )
                        % brief,
                        schema=schema,
                    )
                    if content is None:
                        return _tool_text(
                            "Elicitation declined or cancelled; no changes written."
                        )
                else:
                    # Non-blocking path: return what the human/agent must fill in.
                    return _tool_text(
                        json.dumps(
                            {
                                "status": "needs_disposition",
                                "message": (
                                    "Pass disposition={action, ...} on a follow-up "
                                    "review_candidate call (or use bearing dispose / bearing review). "
                                    "This tool does not block on a form by default."
                                ),
                                "brief": brief,
                                "schema": schema,
                                "candidate_id": candidate_id,
                            },
                            indent=2,
                            sort_keys=True,
                        )
                    )

            if not isinstance(content, dict):
                raise BearingError("disposition must be an object")
            action = str(content.get("action") or "").strip()
            if action not in ACTIONS and action.lower() not in {a.lower() for a in ACTIONS}:
                raise BearingError("form must include action in %s" % ", ".join(ACTIONS))
            result = dispose(config, candidate_id, action, Judgment.from_mapping(content))
            return _tool_text(json.dumps(result.as_dict(), indent=2, sort_keys=True))

        raise BearingError("unknown tool: %s" % name)

    def _resource_defs(self) -> list:
        return [
            {
                "uri": REVIEWABLE_UI_URI,
                "name": "Reviewable candidates",
                "description": "Read-only MCP App board of surfaced shadow candidates.",
                "mimeType": REVIEWABLE_UI_MIME,
            }
        ]

    def _read_resource(self, uri: str) -> Dict[str, Any]:
        if uri != REVIEWABLE_UI_URI:
            raise BearingError("resource not found: %s" % uri)
        if self._queue_html is None:
            try:
                config = resolve(workspace=self.workspace if self.workspace else None)
                config.require_initialized()
                self._queue_html = reviewable_queue_html(
                    list_reviewable(config.layout), workspace=config.workspace
                )
            except Exception as exc:
                self._queue_html = reviewable_queue_html([], error=str(exc))
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": REVIEWABLE_UI_MIME,
                    "text": self._queue_html,
                }
            ]
        }

    def _elicit(self, message: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Optional elicitation/create — opt-in only; can hang hosts that never answer."""
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
            inbound = self._read_message()
            if inbound is None:
                raise BearingError("stdin closed while waiting for elicitation")
            if "method" in inbound:
                self._dispatch_message(inbound)
                continue
            if inbound.get("id") != req_id:
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

    def _in(self) -> Any:
        buf = getattr(self.stdin, "buffer", None)
        return buf if buf is not None else self.stdin

    def _out(self) -> Any:
        buf = getattr(self.stdout, "buffer", None)
        return buf if buf is not None else self.stdout

    def _readline(self) -> bytes:
        chunk = self._in().readline()
        if chunk in ("", b""):
            return b""
        return chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

    def _read_exact(self, length: int) -> bytes:
        if length <= 0:
            return b""
        data = self._in().read(length)
        if data in ("", None):
            return b""
        return data if isinstance(data, bytes) else data.encode("utf-8")

    def _write_raw(self, data: bytes) -> None:
        out = self._out()
        try:
            out.write(data)
            out.flush()
        except TypeError:
            self.stdout.write(data.decode("utf-8"))
            self.stdout.flush()

    def _write(self, message: Dict[str, Any]) -> None:
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if self._use_content_length:
            header = ("Content-Length: %d\r\n\r\n" % len(body)).encode("ascii")
            self._write_raw(header + body)
        else:
            self._write_raw(body + b"\n")


def _tool_text(text: str, ui_resource: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": False,
    }
    if ui_resource:
        payload["_meta"] = {"ui": {"resourceUri": ui_resource}}
    return payload


def _esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value), quote=True)


def reviewable_queue_html(
    rows: List[Dict[str, Any]],
    workspace: str = "",
    error: str = "",
) -> str:
    """Read-only review board. Does not dispose candidates."""
    cards = []
    for row in rows:
        flags = []
        if row.get("load_bearing"):
            flags.append("load-bearing")
        if row.get("conflicts_with_accepted"):
            flags.append("conflicts %s" % row.get("conflicts_with_accepted"))
        flag_html = (
            "".join('<span class="flag">%s</span>' % _esc(item) for item in flags)
            if flags
            else ""
        )
        cards.append(
            """
<article class="card">
  <header>
    <code>%s</code>
    <span class="pill">%s</span>
    <span class="pill muted">%s</span>
  </header>
  <p class="subject">%s</p>
  <p class="object">%s</p>
  %s
</article>"""
            % (
                _esc(row.get("candidate_id")),
                _esc(row.get("confidence") or "—"),
                _esc(row.get("candidate_eocr_function") or "—"),
                _esc(row.get("subject")),
                _esc(row.get("candidate_object")),
                flag_html,
            )
        )
    body = "".join(cards) if cards else '<p class="empty">No reviewable candidates.</p>'
    err = ('<p class="error">%s</p>' % _esc(error)) if error else ""
    return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #1e1e1e; color: #e8e8e8; }
    h1 { font-size: 16px; font-weight: 600; margin: 0 0 4px; }
    .sub { font-size: 12px; color: #9a9a9a; margin: 0 0 16px; }
    .card { border: 1px solid #3a3a3a; border-radius: 6px; padding: 12px; margin: 0 0 10px; background: #252525; }
    header { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
    code { font-size: 12px; }
    .pill { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: #007acc; color: #fff; }
    .pill.muted { background: #3a3a3a; color: #ccc; }
    .subject { font-size: 13px; margin: 0 0 6px; color: #c8c8c8; }
    .object { font-size: 13px; margin: 0; line-height: 1.45; }
    .flag { display: inline-block; font-size: 11px; margin: 8px 8px 0 0; color: #f0c674; }
    .empty, .error { font-size: 13px; color: #9a9a9a; }
    .error { color: #e07a7a; }
    footer { font-size: 11px; color: #7a7a7a; margin-top: 14px; }
  </style>
</head>
<body>
  <h1>Reviewable decision candidates</h1>
  <p class="sub">Shadow graph — evidence, not decisions. %s · %d surfaced</p>
  %s
  %s
  <footer>Disposition stays on review_candidate / bearing review. This board does not Promote.</footer>
</body>
</html>
""" % (_esc(workspace) if workspace else "workspace unset", len(rows), err, body)


def _log(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


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
    # Hosts sometimes append extra argv; rejecting them prints to stdout/exits
    # and kills the initialize handshake.
    args, _unknown = parser.parse_known_args(argv)
    return McpServer(workspace=args.workspace).run()


if __name__ == "__main__":
    sys.exit(main())
