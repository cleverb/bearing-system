"""Minimal stdio MCP server for candidate disposition and recovery tally.

No third-party MCP SDK — the CLI stays dependency-free (ADR-0005).

@see ADR-0014 — recovery tally projects `.bearing/runs/recovery/`; the model is
not the heartbeat.
@see ADR-0005 — standard library only.

Tools:
  - open_recovery — Decision Recovery tally App (projects `.bearing/runs/recovery/`)
  - report_recovery — semantic checkpoints only (start/complete/fail/constrained)
  - list_reviewable — queue of surfaced shadow candidates (MCP App board)
  - review_candidate — dispose Promote|Edit|Split|Reject|Defer

`open_recovery` attaches `ui://bearing/recovery-tally`. Live numbers come from
`bearing://runs/recovery/current`, which the App polls. The model is not the
heartbeat (ADR-0014).

`list_reviewable` and `review_candidate` share `ui://bearing/reviewable-queue`.
Hosts that support Apps render the review wizard; text-only hosts still receive
JSON fallback.

Important: this server does **not** block on MCP elicitation by default.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional, TextIO

from . import __version__
from .config import resolve
from .decisions import EOCR_FUNCTIONS, LIFECYCLE_STATES
from .disposition import (
    ACTIONS,
    Judgment,
    candidate_brief,
    defaults_from_candidate,
    dispose,
    elicitation_schema,
    find_candidate,
    list_reviewable,
)
from .recovery_run import (
    CHECKPOINT_KINDS,
    checkpoint_sentence,
    complete_run,
    fail_run,
    patch_run,
    snapshot as recovery_snapshot,
    start_run,
)
from .util import BearingError

PROTOCOL_VERSION = "2025-06-18"
UI_EXTENSION = "io.modelcontextprotocol/ui"
REVIEWABLE_UI_URI = "ui://bearing/reviewable-queue"
RECOVERY_UI_URI = "ui://bearing/recovery-tally"
RECOVERY_STATUS_URI = "bearing://runs/recovery/current"
REVIEWABLE_UI_MIME = "text/html;profile=mcp-app"
_BOOT_SCRIPT = '<script type="application/json" id="boot">{}</script>'
_ICON_MARK = "<!-- BEARING:ICONS -->"


def _client_supports_ui(params: Dict[str, Any]) -> bool:
    """True when the host advertises MCP Apps or is a known App-capable client."""
    caps = params.get("capabilities")
    if isinstance(caps, dict):
        extensions = caps.get("extensions")
        if isinstance(extensions, dict):
            ui_ext = extensions.get(UI_EXTENSION)
            if isinstance(ui_ext, dict):
                mime_types = ui_ext.get("mimeTypes") or []
                if REVIEWABLE_UI_MIME in mime_types:
                    return True
    client = params.get("clientInfo")
    if isinstance(client, dict):
        name = str(client.get("name") or "").lower()
        if "cursor" in name or "claude" in name:
            return True
    return False


def _ui_meta(uri: str) -> Dict[str, Any]:
    """MCP Apps tool/result metadata. Dual keys match ext-apps registerAppTool."""
    return {
        "anthropic/expandByDefault": True,
        "ui": {
            "resourceUri": uri,
            "visibility": ["model", "app"],
            "initialState": "expanded",
            "prefersBorder": True,
        },
        "ui/resourceUri": uri,
    }


def _resource_ui_meta() -> Dict[str, Any]:
    return {"ui": {"prefersBorder": True}}


def _queue_summary_rows(structured: Dict[str, Any]) -> list:
    return [
        {
            "candidate_id": row.get("candidate_id"),
            "subject": row.get("subject"),
            "candidate_object": row.get("candidate_object"),
            "candidate_eocr_function": row.get("candidate_eocr_function"),
            "confidence": row.get("confidence"),
            "lifecycle_state": row.get("lifecycle_state"),
        }
        for row in structured.get("candidates") or []
    ]


def _queue_fallback_text(structured: Dict[str, Any]) -> str:
    """Full text for hosts that cannot render the MCP App."""
    return json.dumps(_queue_summary_rows(structured), indent=2, sort_keys=True)


def _queue_ui_ack(structured: Dict[str, Any]) -> str:
    """Minimal model-facing text when the host renders the review board App."""
    count = structured.get("count")
    if count is None:
        count = len(structured.get("candidates") or [])
    noun = "candidate" if count == 1 else "candidates"
    return (
        "Opened the BEARING review board (%d %s). Disposition happens in the "
        "MCP App only — do not list, table, or summarize candidates in chat."
        % (count, noun)
    )


def _disposition_ui_ack(candidate_id: str) -> str:
    return (
        "Opened the review form for %s in the MCP App. Do not repeat evidence "
        "or judgment fields in chat."
        % candidate_id
    )


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
        self._host_supports_ui = False
        self._subscribed: set = set()
        self._queue_payload: Dict[str, Any] = {}
        self._queue_html: Optional[str] = None
        self._recovery_html: Optional[str] = None
        self._recovery_payload: Dict[str, Any] = {}

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

        if method and str(method).startswith("notifications/"):
            return None

        if msg_id is None:
            return None

        try:
            result = self._dispatch(method, params)
            self._write({"jsonrpc": "2.0", "id": msg_id, "result": result})
        except BearingError as exc:
            text = str(exc)
            code = -32601 if text.startswith("method not found") else -32000
            if text.startswith("resource not found"):
                code = -32002
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": code, "message": text},
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
            self._host_supports_ui = _client_supports_ui(params)
            requested = params.get("protocolVersion") or PROTOCOL_VERSION
            if not isinstance(requested, str) or not requested.strip():
                requested = PROTOCOL_VERSION
            return {
                "protocolVersion": requested.strip(),
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": True, "listChanged": True},
                },
                "serverInfo": {"name": "bearing", "version": __version__},
                "instructions": (
                    "Call open_recovery to open the Decision Recovery tally. "
                    "Write progress with bearing recovery-status (or report_recovery "
                    "for start/complete/fail/constrained only). Do not dump tallies "
                    "in chat. When recovery completes, call list_reviewable immediately. "
                    "When the Review App renders, reply with at most one short sentence "
                    "— never list, table, or summarize candidates in chat. Humans dispose "
                    "in the App. Promote requires still_valid, eocr_function, "
                    "lifecycle_state, scope."
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
        if method == "resources/subscribe":
            uri = str(params.get("uri") or "")
            if uri:
                self._subscribed.add(uri)
            return {}
        if method == "resources/unsubscribe":
            self._subscribed.discard(str(params.get("uri") or ""))
            return {}
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
                "name": "open_recovery",
                "description": (
                    "Open the Decision Recovery tally App. Creates or resumes "
                    ".bearing/runs/recovery telemetry. Do not dump counters in chat."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace root.",
                        },
                        "resume": {
                            "type": "boolean",
                            "description": "If true, do not start a new run when one already exists.",
                            "default": True,
                        },
                    },
                },
                "_meta": _ui_meta(RECOVERY_UI_URI),
            },
            {
                "name": "report_recovery",
                "description": (
                    "Semantic recovery checkpoint only (start, complete, fail, "
                    "constrained, scope_established). Not a per-file heartbeat. "
                    "On complete, call list_reviewable next."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "description": "start | complete | fail | constrained | scope_established",
                        },
                        "patch": {
                            "type": "object",
                            "description": "Optional status.json merge (counters, budget, current focus).",
                        },
                        "message": {"type": "string"},
                        "workspace": {"type": "string"},
                    },
                    "required": ["kind"],
                },
                "_meta": _ui_meta(RECOVERY_UI_URI),
            },
            {
                "name": "list_reviewable",
                "description": (
                    "Open the MCP App review board for surfaced shadow candidates "
                    "(Promote / Edit / Split / Reject / Defer). When the App "
                    "renders, do not repeat the queue in chat."
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
                "_meta": _ui_meta(REVIEWABLE_UI_URI),
            },
            {
                "name": "review_candidate",
                "description": (
                    "Review one shadow candidate. Pass disposition "
                    "{action, still_valid, eocr_function, lifecycle_state, scope, ...}. "
                    "If disposition is omitted, opens the MCP App review form (or returns "
                    "the evidence brief and schema). Promote requires human judgment "
                    "fields — not confidence."
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
                "_meta": _ui_meta(REVIEWABLE_UI_URI),
            },
        ]

    def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace = arguments.get("workspace") or self.workspace
        config = resolve(workspace=workspace if workspace else None)
        config.require_initialized()
        if arguments.get("workspace"):
            self.workspace = str(arguments.get("workspace"))

        if name == "open_recovery":
            structured = self._snapshot_recovery(config, resume=arguments.get("resume", True) is not False)
            if self._host_supports_ui:
                text = _recovery_ui_ack(structured)
            else:
                text = _recovery_fallback_text(structured)
            return _tool_result(
                text,
                ui_resource=RECOVERY_UI_URI if self._host_supports_ui else None,
                structured=structured,
            )

        if name == "report_recovery":
            kind = str(arguments.get("kind") or "").strip().lower()
            if kind not in CHECKPOINT_KINDS:
                raise BearingError("kind must be one of %s" % ", ".join(CHECKPOINT_KINDS))
            patch = arguments.get("patch") if isinstance(arguments.get("patch"), dict) else {}
            message = str(arguments.get("message") or "").strip()
            if kind == "start":
                structured = start_run(config, patch)
            elif kind == "complete":
                if patch:
                    patch_run(config, patch)
                structured = complete_run(config, message or "Recovery completed")
            elif kind == "fail":
                if patch:
                    patch_run(config, patch)
                structured = fail_run(config, message or "Recovery failed")
            else:
                if message and "budget" not in patch:
                    patch = dict(patch)
                    budget = dict(patch.get("budget") or {})
                    budget["status"] = "constraining"
                    constraint = dict(budget.get("constraint") or {})
                    constraint.setdefault("reason", message)
                    budget["constraint"] = constraint
                    patch["budget"] = budget
                structured = patch_run(
                    config,
                    patch,
                    {"type": kind, "label": message or kind.replace("_", " ")},
                )
            self._store_recovery(structured)
            if self._host_supports_ui:
                text = checkpoint_sentence(kind, structured)
            else:
                text = json.dumps(
                    {
                        "kind": kind,
                        "message": checkpoint_sentence(kind, structured),
                        "run_id": structured.get("run_id"),
                        "status": structured.get("status"),
                        "findings": structured.get("findings"),
                    },
                    indent=2,
                    sort_keys=True,
                )
            return _tool_result(
                text,
                ui_resource=RECOVERY_UI_URI if self._host_supports_ui else None,
                structured=structured,
            )

        if name == "list_reviewable":
            structured = self._snapshot_queue(config)
            if self._host_supports_ui:
                text = _queue_ui_ack(structured)
            else:
                text = _queue_fallback_text(structured)
            return _tool_result(
                text,
                ui_resource=REVIEWABLE_UI_URI if self._host_supports_ui else None,
                structured=structured,
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
                        return _tool_result(
                            "Elicitation declined or cancelled; no changes written."
                        )
                else:
                    structured = self._snapshot_queue(config)
                    card = _ui_candidate(candidate)
                    ids = {row.get("candidate_id") for row in structured["candidates"]}
                    if card.get("candidate_id") not in ids:
                        structured["candidates"] = [card] + list(structured["candidates"])
                        structured["count"] = len(structured["candidates"])
                    structured.update(
                        {
                            "status": "needs_disposition",
                            "message": (
                                "Fill the MCP App review form, or pass disposition="
                                "{action, ...} on a follow-up review_candidate call "
                                "(or use bearing dispose / bearing review)."
                            ),
                            "brief": brief,
                            "schema": schema,
                            "candidate_id": candidate_id,
                            "candidate": card,
                        }
                    )
                    self._queue_payload = structured
                    self._queue_html = _resource_html("reviewable", structured)
                    self._notify_resource_updated(REVIEWABLE_UI_URI)
                    ack = (
                        _disposition_ui_ack(candidate_id)
                        if self._host_supports_ui
                        else json.dumps(
                            {
                                "status": "needs_disposition",
                                "message": structured["message"],
                                "brief": brief,
                                "schema": schema,
                                "candidate_id": candidate_id,
                            },
                            indent=2,
                            sort_keys=True,
                        )
                    )
                    return _tool_result(
                        ack,
                        ui_resource=REVIEWABLE_UI_URI if self._host_supports_ui else None,
                        structured=structured,
                    )

            if not isinstance(content, dict):
                raise BearingError("disposition must be an object")
            action = str(content.get("action") or "").strip()
            if action not in ACTIONS and action.lower() not in {a.lower() for a in ACTIONS}:
                raise BearingError("form must include action in %s" % ", ".join(ACTIONS))
            result = dispose(config, candidate_id, action, Judgment.from_mapping(content))
            payload = result.as_dict()
            structured = self._snapshot_queue(config)
            structured.update(
                {
                    "status": "disposed",
                    "result": payload,
                    "candidate_id": candidate_id,
                }
            )
            self._queue_payload = structured
            self._queue_html = _resource_html("reviewable", structured)
            self._notify_resource_updated(REVIEWABLE_UI_URI)
            return _tool_result(
                json.dumps(payload, indent=2, sort_keys=True),
                ui_resource=REVIEWABLE_UI_URI if self._host_supports_ui else None,
                structured=structured,
            )

        raise BearingError("unknown tool: %s" % name)

    def _snapshot_queue(self, config) -> Dict[str, Any]:
        rows = [_ui_candidate(row) for row in list_reviewable(config.layout)]
        structured = {
            "workspace": config.workspace,
            "count": len(rows),
            "candidates": rows,
            "enums": {
                "actions": list(ACTIONS),
                "eocr_functions": list(EOCR_FUNCTIONS),
                "lifecycle_states": list(LIFECYCLE_STATES),
            },
        }
        self._queue_payload = structured
        self._queue_html = _resource_html("reviewable", structured)
        self._notify_resource_updated(REVIEWABLE_UI_URI)
        return structured

    def _snapshot_recovery(self, config, resume: bool = True) -> Dict[str, Any]:
        from .recovery_run import current_run_id

        if resume and current_run_id(config):
            structured = recovery_snapshot(config)
        else:
            structured = start_run(config)
        return self._store_recovery(structured)

    def _store_recovery(self, structured: Dict[str, Any]) -> Dict[str, Any]:
        self._recovery_payload = structured
        self._recovery_html = _resource_html("recovery", structured)
        self._notify_resource_updated(RECOVERY_UI_URI)
        self._notify_resource_updated(RECOVERY_STATUS_URI)
        return structured

    def _resource_defs(self) -> list:
        return [
            {
                "uri": RECOVERY_UI_URI,
                "name": "Decision Recovery tally",
                "description": "MCP App projecting .bearing/runs/recovery telemetry.",
                "mimeType": REVIEWABLE_UI_MIME,
                "_meta": _resource_ui_meta(),
            },
            {
                "uri": RECOVERY_STATUS_URI,
                "name": "Current recovery status",
                "description": "JSON snapshot plus last activity events for the Recovery App to poll.",
                "mimeType": "application/json",
            },
            {
                "uri": REVIEWABLE_UI_URI,
                "name": "Reviewable UI Component",
                "description": "MCP App board of surfaced shadow candidates.",
                "mimeType": REVIEWABLE_UI_MIME,
                "_meta": _resource_ui_meta(),
            },
        ]

    def _read_resource(self, uri: str) -> Dict[str, Any]:
        if uri == RECOVERY_STATUS_URI:
            payload = self._recovery_payload
            if not payload:
                try:
                    config = resolve(workspace=self.workspace if self.workspace else None)
                    config.require_initialized()
                    payload = recovery_snapshot(config)
                    self._recovery_payload = payload
                except Exception as exc:
                    payload = {"error": str(exc), "status": "running", "recent_activity": []}
            body = json.dumps(payload, separators=(",", ":"))
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": body,
                    }
                ]
            }
        if uri == RECOVERY_UI_URI:
            html = self._recovery_html
            if html is None:
                try:
                    config = resolve(workspace=self.workspace if self.workspace else None)
                    config.require_initialized()
                    self._snapshot_recovery(config)
                    html = self._recovery_html
                except Exception as exc:
                    html = _resource_html("recovery", {"error": str(exc)})
                    self._recovery_html = html
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": REVIEWABLE_UI_MIME,
                        "text": html or _resource_html("recovery", self._recovery_payload),
                        "_meta": _resource_ui_meta(),
                    }
                ]
            }
        if uri != REVIEWABLE_UI_URI:
            raise BearingError("resource not found: %s" % uri)
        html = self._queue_html
        if html is None:
            try:
                config = resolve(workspace=self.workspace if self.workspace else None)
                config.require_initialized()
                self._snapshot_queue(config)
                html = self._queue_html
            except Exception as exc:
                html = _resource_html("reviewable", {"error": str(exc), "candidates": []})
                self._queue_html = html
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": REVIEWABLE_UI_MIME,
                    "text": html or _resource_html("reviewable", self._queue_payload),
                    "_meta": _resource_ui_meta(),
                }
            ]
        }

    def _notify_resource_updated(self, uri: str) -> None:
        """Ask the host to re-fetch App HTML or status JSON after changes."""
        if self._subscribed and uri not in self._subscribed:
            return
        if not self._subscribed:
            return
        self._write(
            {
                "jsonrpc": "2.0",
                "method": "notifications/resources/updated",
                "params": {"uri": uri},
            }
        )

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


def _ui_candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    """Fields the App needs to show evidence and pre-fill a judgment form."""
    defaults = defaults_from_candidate(row)
    evidence = []
    for item in (row.get("evidence") or [])[:16]:
        if not isinstance(item, dict):
            continue
        excerpt = str(item.get("evidence_excerpt") or "").strip().replace("\n", " ")
        if len(excerpt) > 220:
            excerpt = excerpt[:217] + "..."
        evidence.append(
            {
                "evidence_source": item.get("evidence_source") or "unknown",
                "evidence_excerpt": excerpt,
            }
        )
    return {
        "candidate_id": row.get("candidate_id"),
        "subject": row.get("subject"),
        "candidate_object": row.get("candidate_object"),
        "candidate_relation": row.get("candidate_relation"),
        "candidate_eocr_function": row.get("candidate_eocr_function"),
        "confidence": row.get("confidence"),
        "lifecycle_state": row.get("lifecycle_state"),
        "conflicts_with_accepted": row.get("conflicts_with_accepted"),
        "load_bearing": row.get("load_bearing"),
        "evidence": evidence,
        "defaults": {
            "eocr_function": defaults.eocr_function,
            "lifecycle_state": defaults.lifecycle_state,
            "scope": defaults.scope,
            "title": defaults.title,
            "trigger": defaults.trigger,
        },
    }


def _tool_result(
    text: str,
    ui_resource: Optional[str] = None,
    structured: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": False,
    }
    if ui_resource:
        payload["_meta"] = _ui_meta(ui_resource)
    if structured is not None:
        payload["structuredContent"] = structured
    return payload


def _recovery_ui_ack(structured: Dict[str, Any]) -> str:
    run_id = structured.get("run_id") or "current run"
    return (
        "Opened the Decision Recovery tally (%s). Progress lives in run-state; "
        "do not repeat counters in chat. When complete, call list_reviewable."
        % run_id
    )


def _recovery_fallback_text(structured: Dict[str, Any]) -> str:
    compact = {
        "run_id": structured.get("run_id"),
        "status": structured.get("status"),
        "stage": structured.get("stage"),
        "stage_label": structured.get("stage_label"),
        "findings": structured.get("findings"),
        "eta": structured.get("eta"),
        "budget": {
            "status": (structured.get("budget") or {}).get("status"),
            "mode": (structured.get("budget") or {}).get("mode"),
        },
        "current": structured.get("current"),
    }
    return json.dumps(compact, indent=2, sort_keys=True)


def _resource_html(kind: str, payload: Optional[Dict[str, Any]] = None) -> str:
    """App shell with boot JSON and an inline SVG sprite (CSP-safe)."""
    blob = json.dumps(payload or {}, separators=(",", ":")).replace("<", "\\u003c")
    html = _app_html(kind).replace(
        _BOOT_SCRIPT,
        '<script type="application/json" id="boot">%s</script>' % blob,
        1,
    )
    return html.replace(_ICON_MARK, _icon_sprite(), 1)


def _app_html(kind: str) -> str:
    name = "recovery-app.html" if kind == "recovery" else "reviewable-app.html"
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", name)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _icon_sprite() -> str:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mcp-icons.svg")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _log(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def main(argv: Optional[list] = None) -> int:
    import argparse

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
