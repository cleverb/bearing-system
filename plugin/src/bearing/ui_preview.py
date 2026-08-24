"""Local HTTP mock host for Recovery and Reviewable MCP Apps.

@see ADR-0002 — this command never writes the plugin tree.
@see ADR-0005 — stdlib only (http.server, json).
@see ADR-0007 — preview settings are catalog + CLI flags, not workspace config.
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple, Type
from urllib.parse import parse_qs, unquote, urlparse

from .jsonschema import validate
from .mcp_server import RECOVERY_STATUS_URI, _BOOT_SCRIPT, _ICON_MARK
from .paths import data_dir
from .util import BearingError, read_json

DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_SIM_MS = 5000
REQUIRED_STORY_IDS = (
    "recovery-run-empty",
    "recovery-run-few",
    "recovery-run-dense",
    "recovery-run-constrained",
    "recovery-run-failed",
    "recovery-idle",
    "recovery-constrained",
    "recovery-failed",
    "recovery-few-midscan",
    "review-empty",
    "review-few",
    "review-dense",
    "review-needs-disposition",
    "review-promote-invalid",
    "review-dispositions",
)
REVIEW_CANDIDATE_FIELDS = (
    "candidate_id",
    "subject",
    "candidate_object",
    "candidate_eocr_function",
    "confidence",
    "evidence",
    "defaults",
)


def preview_root(html_root=None):
    return os.path.join(html_root or data_dir(), "ui-preview")


def default_catalog_path(html_root=None):
    return os.path.join(preview_root(html_root), "catalog.json")


def default_fixtures_dir(html_root=None):
    return os.path.join(preview_root(html_root), "fixtures")


def default_host_path(html_root=None):
    return os.path.join(preview_root(html_root), "host.html")


def load_catalog(path):
    data = read_json(path, None)
    if not isinstance(data, dict):
        raise BearingError("preview catalog is missing or not a JSON object: %s" % path)
    stories = data.get("stories")
    if not isinstance(stories, list) or not stories:
        raise BearingError("preview catalog has no stories: %s" % path)
    return data


def list_stories(catalog):
    rows = []
    for story in catalog.get("stories") or []:
        if isinstance(story, dict) and story.get("id"):
            rows.append(story)
    return rows


def story_by_id(catalog, story_id):
    for story in list_stories(catalog):
        if story.get("id") == story_id:
            return story
    raise BearingError("unknown preview story %r" % story_id)


def _safe_join(root, relative):
    rel = relative.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise BearingError("preview path may not contain ..: %s" % relative)
    path = os.path.normpath(os.path.join(root, rel))
    root_abs = os.path.abspath(root)
    if path != root_abs and not path.startswith(root_abs + os.sep):
        raise BearingError("preview path escapes root: %s" % relative)
    return path


def resolve_fixture(catalog_dir, fixtures_dir, relpath):
    rel = relpath.replace("\\", "/")
    if fixtures_dir and rel.startswith("fixtures/"):
        return _safe_join(fixtures_dir, rel.split("/", 1)[1])
    return _safe_join(catalog_dir, rel)


def story_fixture_paths(story, catalog_dir, fixtures_dir):
    paths = []
    fixture = story.get("fixture")
    if isinstance(fixture, str) and fixture:
        paths.append(resolve_fixture(catalog_dir, fixtures_dir, fixture))
    simulation = story.get("simulation") or {}
    for frame in simulation.get("frames") or []:
        if isinstance(frame, str) and frame:
            paths.append(resolve_fixture(catalog_dir, fixtures_dir, frame))
    return paths


def recovery_schema():
    path = os.path.join(data_dir(), "recovery-status.schema.json")
    schema = read_json(path, None)
    if not isinstance(schema, dict):
        raise BearingError("missing recovery-status.schema.json")
    return schema


def validate_recovery_fixture(payload):
    errors = list(validate(payload, recovery_schema()))
    if not isinstance(payload.get("stages"), list):
        errors.append("recovery fixture missing stages[] (App pipeline)")
    if "recent_activity" not in payload:
        errors.append("recovery fixture missing recent_activity (App feed)")
    scope = payload.get("scope") or {}
    if not isinstance(scope, dict):
        errors.append("recovery fixture scope must be an object")
    elif "locations" not in scope:
        errors.append("recovery fixture missing scope.locations (App grid)")
    return errors


def validate_review_fixture(payload):
    errors = []
    if not isinstance(payload, dict):
        return ["review fixture must be a JSON object"]
    if "candidates" not in payload:
        errors.append("review fixture missing candidates")
    candidates = payload.get("candidates") or []
    if not isinstance(candidates, list):
        errors.append("review fixture candidates must be an array")
        return errors
    for index, row in enumerate(candidates):
        if not isinstance(row, dict):
            errors.append("candidates[%d] must be an object" % index)
            continue
        for field in REVIEW_CANDIDATE_FIELDS:
            if field not in row:
                errors.append("candidates[%d] missing %s" % (index, field))
        evidence = row.get("evidence")
        if evidence is not None and not isinstance(evidence, list):
            errors.append("candidates[%d].evidence must be an array" % index)
        defaults = row.get("defaults")
        if defaults is not None and not isinstance(defaults, dict):
            errors.append("candidates[%d].defaults must be an object" % index)
    enums = payload.get("enums")
    if enums is not None and not isinstance(enums, dict):
        errors.append("review fixture enums must be an object")
    return errors


def catalog_issues(catalog, catalog_path, fixtures_dir=None):
    catalog_dir = os.path.dirname(os.path.abspath(catalog_path))
    issues = []
    seen = set()
    for story in list_stories(catalog):
        sid = str(story.get("id"))
        if sid in seen:
            issues.append("duplicate story id %r" % sid)
        seen.add(sid)
        app = story.get("app")
        if app not in ("recovery", "reviewable"):
            issues.append("%s: app must be recovery or reviewable" % sid)
        paths = story_fixture_paths(story, catalog_dir, fixtures_dir)
        if not paths:
            issues.append("%s: no fixture or simulation.frames" % sid)
            continue
        for path in paths:
            if not os.path.isfile(path):
                issues.append("%s: missing fixture %s" % (sid, path))
                continue
            payload = read_json(path, None)
            if not isinstance(payload, dict):
                issues.append("%s: fixture is not an object: %s" % (sid, path))
                continue
            if app == "recovery":
                for error in validate_recovery_fixture(payload):
                    issues.append("%s (%s): %s" % (sid, os.path.basename(path), error))
            elif app == "reviewable":
                for error in validate_review_fixture(payload):
                    issues.append("%s (%s): %s" % (sid, os.path.basename(path), error))
    for required in REQUIRED_STORY_IDS:
        if required not in seen:
            issues.append("catalog missing required story %r" % required)
    return issues


def inject_app_html(kind, payload, html_root):
    name = "recovery-app.html" if kind == "recovery" else "reviewable-app.html"
    html_path = os.path.join(html_root, name)
    sprite_path = os.path.join(html_root, "mcp-icons.svg")
    if not os.path.isfile(html_path):
        raise BearingError("missing App HTML %s" % html_path)
    if not os.path.isfile(sprite_path):
        raise BearingError("missing icon sprite %s" % sprite_path)
    with open(html_path, encoding="utf-8") as handle:
        html = handle.read()
    with open(sprite_path, encoding="utf-8") as handle:
        sprite = handle.read()
    blob = json.dumps(payload or {}, separators=(",", ":")).replace("<", "\\u003c")
    html = html.replace(
        _BOOT_SCRIPT,
        '<script type="application/json" id="boot">%s</script>' % blob,
        1,
    )
    return html.replace(_ICON_MARK, sprite, 1)


def tool_result(structured, text="ok", is_error=False):
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
        "structuredContent": structured,
    }


def resource_contents(uri, payload):
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(payload, separators=(",", ":")),
            }
        ]
    }


class PreviewSession:
    def __init__(self, story, fixtures):
        self.story = story
        self.fixtures = [deepcopy(row) for row in fixtures]
        self.frame_index = 0
        self.fail_next = False
        self.session_approved = 0
        self._review = deepcopy(fixtures[0]) if fixtures else {"candidates": []}
        if story.get("app") == "reviewable":
            self._review.setdefault("candidates", [])
            self._review.setdefault("enums", {})
            self._review.setdefault("workspace", "")

    def current_recovery(self):
        if not self.fixtures:
            return {}
        index = max(0, min(self.frame_index, len(self.fixtures) - 1))
        return deepcopy(self.fixtures[index])

    def advance(self):
        if self.fixtures:
            self.frame_index = (self.frame_index + 1) % len(self.fixtures)
        return self.current_recovery()

    def reset(self):
        self.frame_index = 0
        return self.current_recovery()

    def handle_rpc(self, method, params=None):
        params = params or {}
        if method == "resources/read":
            uri = str(params.get("uri") or "")
            if uri and uri != RECOVERY_STATUS_URI and "recovery" not in uri:
                raise BearingError("unknown resource %s" % uri)
            return resource_contents(uri or RECOVERY_STATUS_URI, self.current_recovery())
        if method == "tools/call":
            return self._call_tool(str(params.get("name") or ""), params.get("arguments") or {})
        raise BearingError("method not found: %s" % method)

    def _call_tool(self, name, arguments):
        if self.fail_next:
            self.fail_next = False
            return tool_result(
                {"error": "preview forced tools/call failure"},
                "preview forced tools/call failure",
                True,
            )
        if name == "list_reviewable":
            payload = deepcopy(self._review)
            payload["count"] = len(payload.get("candidates") or [])
            payload["status"] = payload.get("status") or "ok"
            return tool_result(payload, "listed %d candidates" % payload["count"])
        if name == "review_candidate":
            return self._review_candidate(arguments if isinstance(arguments, dict) else {})
        raise BearingError("unknown tool: %s" % name)

    def _review_candidate(self, arguments):
        candidate_id = str(arguments.get("candidate_id") or "").strip()
        if not candidate_id:
            return tool_result({"error": "candidate_id is required"}, "candidate_id is required", True)
        candidates = list(self._review.get("candidates") or [])
        match = None
        for row in candidates:
            if row.get("candidate_id") == candidate_id:
                match = row
                break
        if match is None:
            return tool_result({"error": "unknown candidate %s" % candidate_id}, "unknown candidate", True)
        disposition = arguments.get("disposition")
        if not isinstance(disposition, dict) or not disposition.get("action"):
            payload = deepcopy(self._review)
            payload.update(
                {
                    "status": "needs_disposition",
                    "candidate_id": candidate_id,
                    "candidate": deepcopy(match),
                }
            )
            return tool_result(payload, "needs disposition")
        action = str(disposition.get("action") or "")
        if action == "Promote":
            if not disposition.get("still_valid"):
                return tool_result(
                    {"error": "Promote requires affirming still valid today."},
                    "Promote requires affirming still valid today.",
                    True,
                )
            if not str(disposition.get("scope") or "").strip():
                return tool_result(
                    {"error": "Promote requires a non-empty scope."},
                    "Promote requires a non-empty scope.",
                    True,
                )
            self.session_approved += 1
        self._review["candidates"] = [row for row in candidates if row.get("candidate_id") != candidate_id]
        payload = deepcopy(self._review)
        payload.update(
            {
                "status": "disposed",
                "candidate_id": candidate_id,
                "session_approved": self.session_approved,
                "result": {
                    "action": action,
                    "candidate_id": candidate_id,
                    "message": "Preview recorded %s (no files written)." % action,
                },
            }
        )
        payload["count"] = len(payload["candidates"])
        return tool_result(payload, "disposed")


def _session_from_story(story, catalog_dir, fixtures_dir):
    payloads = []
    for path in story_fixture_paths(story, catalog_dir, fixtures_dir):
        loaded = read_json(path, {})
        payloads.append(loaded if isinstance(loaded, dict) else {})
    return PreviewSession(story, payloads)


def make_handler(catalog, catalog_path, html_root, fixtures_dir, host_html, default_story, sim_ms):
    catalog_dir = os.path.dirname(os.path.abspath(catalog_path))
    preview_dir = os.path.dirname(os.path.abspath(host_html))
    fixture_root = fixtures_dir or os.path.join(preview_dir, "fixtures")

    class PreviewHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, fmt, *args):
            return

        def _send(self, status, body, content_type, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload, status=200):
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def _send_text(self, text, content_type, status=200):
            self._send(status, text.encode("utf-8"), content_type)

        def do_GET(self):
            parsed = urlparse(self.path)
            route = unquote(parsed.path)
            try:
                if route in ("/", "/host.html"):
                    with open(host_html, encoding="utf-8") as handle:
                        self._send_text(handle.read(), "text/html; charset=utf-8")
                    return
                if route == "/catalog.json":
                    self._send_json(catalog)
                    return
                if route == "/preview-config.json":
                    stories = list_stories(catalog)
                    defaults = catalog.get("defaults") or {}
                    simulation = defaults.get("simulation") or {}
                    self._send_json(
                        {
                            "story": default_story or defaults.get("story") or stories[0]["id"],
                            "sim_ms": sim_ms or simulation.get("interval_ms", DEFAULT_SIM_MS),
                            "status_uri": RECOVERY_STATUS_URI,
                        }
                    )
                    return
                if route.startswith("/fixtures/"):
                    path = _safe_join(fixture_root, route[len("/fixtures/"):])
                    if not os.path.isfile(path):
                        self._send_text("not found", "text/plain; charset=utf-8", 404)
                        return
                    with open(path, "rb") as handle:
                        self._send(200, handle.read(), "application/json; charset=utf-8")
                    return
                if route in ("/app/recovery.html", "/app/reviewable.html"):
                    kind = "recovery" if "recovery" in route else "reviewable"
                    query = parse_qs(parsed.query)
                    story_id = (query.get("story") or [default_story or ""])[0]
                    payload = {}
                    if story_id:
                        story = story_by_id(catalog, story_id)
                        paths = story_fixture_paths(story, catalog_dir, fixtures_dir)
                        if paths:
                            loaded = read_json(paths[0], {})
                            if isinstance(loaded, dict):
                                payload = loaded
                    html = inject_app_html(kind, payload, html_root)
                    self._send_text(html, "text/html; charset=utf-8")
                    return
                self._send_text("not found", "text/plain; charset=utf-8", 404)
            except BearingError as exc:
                self._send_text(str(exc), "text/plain; charset=utf-8", 400)

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != "/rpc":
                self._send_text("not found", "text/plain; charset=utf-8", 404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                message = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json({"error": "invalid JSON"}, 400)
                return
            story_id = str(message.get("story") or default_story or list_stories(catalog)[0]["id"])
            try:
                story = story_by_id(catalog, story_id)
                session = _session_from_story(story, catalog_dir, fixtures_dir)
                if message.get("frame_index") is not None:
                    session.frame_index = int(message.get("frame_index") or 0)
                if message.get("fail_next"):
                    session.fail_next = True
                result = session.handle_rpc(
                    str(message.get("method") or ""),
                    message.get("params") if isinstance(message.get("params"), dict) else {},
                )
                self._send_json({"jsonrpc": "2.0", "id": message.get("id"), "result": result})
            except BearingError as exc:
                self._send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {"code": -32000, "message": str(exc)},
                    }
                )

    return PreviewHandler


def serve(bind, port, catalog_path, html_root, fixtures_dir, host_html, default_story, sim_ms, open_browser):
    catalog = load_catalog(catalog_path)
    issues = catalog_issues(catalog, catalog_path, fixtures_dir)
    if issues:
        raise BearingError("preview catalog is not usable:\n  - %s" % "\n  - ".join(issues))
    handler = make_handler(
        catalog, catalog_path, html_root, fixtures_dir, host_html, default_story, sim_ms
    )
    httpd = ThreadingHTTPServer((bind, port), handler)
    url = "http://%s:%d/" % (bind, httpd.server_address[1])
    if default_story:
        url += "?story=%s" % default_story
    if open_browser:
        webbrowser.open(url)
    return url, httpd


def cmd_ui_preview(args):
    html_root = os.path.abspath(args.html_root or data_dir())
    catalog_path = os.path.abspath(args.catalog or default_catalog_path(html_root))
    fixtures_dir = os.path.abspath(args.fixtures) if args.fixtures else default_fixtures_dir(html_root)
    host_html = default_host_path(html_root)
    if not os.path.isfile(catalog_path):
        raise BearingError("preview catalog not found: %s" % catalog_path)
    if not os.path.isfile(host_html):
        raise BearingError("preview host.html not found: %s" % host_html)
    catalog = load_catalog(catalog_path)
    if args.list:
        for story in list_stories(catalog):
            print("%s\t%s\t%s" % (story.get("id"), story.get("app"), story.get("title") or ""))
        return 0
    if args.story:
        story_by_id(catalog, args.story)
    url, httpd = serve(
        bind=args.bind,
        port=int(args.port),
        catalog_path=catalog_path,
        html_root=html_root,
        fixtures_dir=fixtures_dir,
        host_html=host_html,
        default_story=args.story,
        sim_ms=int(args.sim_ms) if args.sim_ms is not None else None,
        open_browser=bool(args.open),
    )
    print("bearing ui-preview  %s" % url)
    print("Ctrl-C to stop. Catalog: %s" % catalog_path)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return 0


def start_background(catalog_path, html_root, fixtures_dir=None, port=0, bind=DEFAULT_BIND, story=None, sim_ms=None):
    host_html = os.path.join(os.path.dirname(catalog_path), "host.html")
    url, httpd = serve(
        bind=bind,
        port=port,
        catalog_path=catalog_path,
        html_root=html_root,
        fixtures_dir=fixtures_dir,
        host_html=host_html,
        default_story=story,
        sim_ms=sim_ms,
        open_browser=False,
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return url, httpd, thread
