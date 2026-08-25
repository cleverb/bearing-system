"""Durable recovery telemetry under `.bearing/runs/recovery/`.

@see ADR-0014 — the App projects this state; the model is not the heartbeat.
@see ADR-0002 — writes go to `.bearing/`, never the plugin tree.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from .config import ResolvedConfig
from .jsonschema import validate
from .paths import schema_path
from .util import BearingError, append_jsonl, dump_json, read_json, read_jsonl, read_text, write_text

STAGES = (
    ("scope_plan", "Scope & Plan"),
    ("discover", "Discover"),
    ("extract", "Extract"),
    ("identify", "Identify"),
    ("synthesize", "Synthesize"),
    ("write_persist", "Write & Persist"),
)
STAGE_IDS = [row[0] for row in STAGES]
STAGE_LABELS = {row[0]: row[1] for row in STAGES}
EVENT_FEED_LIMIT = 8
LOCATION_GRID_CAP = 32
CHECKPOINT_KINDS = ("start", "complete", "fail", "constrained", "scope_established")


def recovery_dir(config: ResolvedConfig) -> str:
    return os.path.join(config.layout.runs, "recovery")


def current_pointer_path(config: ResolvedConfig) -> str:
    return os.path.join(recovery_dir(config), "current")


def run_dir(config: ResolvedConfig, run_id: str) -> str:
    return os.path.join(recovery_dir(config), run_id)


def status_path(config: ResolvedConfig, run_id: str) -> str:
    return os.path.join(run_dir(config, run_id), "status.json")


def events_path(config: ResolvedConfig, run_id: str) -> str:
    return os.path.join(run_dir(config, run_id), "events.jsonl")


def iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def new_run_id(when: Optional[datetime.datetime] = None) -> str:
    stamp = (when or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return "recovery-%s" % stamp


def current_run_id(config: ResolvedConfig) -> Optional[str]:
    raw = read_text(current_pointer_path(config), "") or ""
    run_id = raw.strip()
    return run_id or None


def load_status(config: ResolvedConfig, run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    rid = run_id or current_run_id(config)
    if not rid:
        return None
    data = read_json(status_path(config, rid), None)
    return data if isinstance(data, dict) else None


def load_events(config: ResolvedConfig, run_id: Optional[str] = None, limit: int = EVENT_FEED_LIMIT) -> List[Dict[str, Any]]:
    rid = run_id or current_run_id(config)
    if not rid:
        return []
    rows = [row for row in read_jsonl(events_path(config, rid)) if isinstance(row, dict)]
    if limit <= 0:
        return rows
    return rows[-limit:]


def snapshot(config: ResolvedConfig, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Payload the MCP status resource and Recovery App consume."""
    status = load_status(config, run_id) or empty_status()
    events = load_events(config, status.get("run_id") if status.get("run_id") else run_id)
    locations = list((status.get("scope") or {}).get("locations") or [])
    if len(locations) > LOCATION_GRID_CAP:
        locations = locations[:LOCATION_GRID_CAP]
    out = dict(status)
    scope = dict(out.get("scope") or {})
    scope["locations"] = locations
    out["scope"] = scope
    out["recent_activity"] = events
    out["stages"] = [{"id": sid, "label": label} for sid, label in STAGES]
    return out


def empty_status() -> Dict[str, Any]:
    return {
        "run_id": "",
        "status": "running",
        "stage": STAGE_IDS[0],
        "stage_index": 1,
        "stage_count": len(STAGES),
        "stage_label": STAGE_LABELS[STAGE_IDS[0]],
        "started_at": "",
        "updated_at": "",
        "elapsed_seconds": 0,
        "eta": {
            "remaining_seconds_low": 0,
            "remaining_seconds_high": 0,
            "confidence": "low",
            "display": "—",
        },
        "scope": {
            "locations_total": 0,
            "locations_scanned": 0,
            "files_indexed": 0,
            "locations": [],
        },
        "current": {"path": "", "activity": "", "kind": "", "items": 0, "depth": 0},
        "findings": {
            "candidate_decisions": 0,
            "evidence_items": 0,
            "records_prepared": 0,
            "records_written": 0,
        },
        "budget": {
            "mode": "balanced",
            "time_budget_seconds": 600,
            "max_candidates": 60,
            "pressure": 0,
            "status": "normal",
            "constraint": None,
        },
        "rates": {},
        "message": "",
    }


def start_run(config: ResolvedConfig, patch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    run_id = new_run_id()
    now = iso_now()
    status = empty_status()
    status.update(
        {
            "run_id": run_id,
            "status": "running",
            "started_at": now,
            "updated_at": now,
        }
    )
    if patch:
        status = merge_status(status, patch)
    _finalize(status, started_at=now)
    _write_status(config, status)
    write_text(current_pointer_path(config), run_id + "\n")
    append_event(config, run_id, {"type": "start", "label": "Recovery started"})
    return snapshot(config, run_id)


def patch_run(
    config: ResolvedConfig,
    patch: Optional[Dict[str, Any]] = None,
    event: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    current = load_status(config, run_id)
    if current is None:
        return start_run(config, patch)
    status = merge_status(current, patch or {})
    _finalize(status, started_at=str(current.get("started_at") or iso_now()))
    _write_status(config, status)
    if event:
        append_event(config, str(status["run_id"]), event)
    return snapshot(config, str(status["run_id"]))


def complete_run(config: ResolvedConfig, message: str = "Recovery completed") -> Dict[str, Any]:
    return _finish(config, "completed", message, {"type": "complete", "label": message})


def fail_run(config: ResolvedConfig, message: str = "Recovery failed") -> Dict[str, Any]:
    return _finish(config, "failed", message, {"type": "fail", "label": message})


def checkpoint_sentence(kind: str, snap: Dict[str, Any]) -> str:
    findings = snap.get("findings") or {}
    if kind == "start":
        return "Opened the Decision Recovery tally for %s." % (snap.get("run_id") or "this run")
    if kind == "complete":
        return (
            "Recovery completed (%s candidate decisions found). Call list_reviewable next."
            % findings.get("candidate_decisions", 0)
        )
    if kind == "fail":
        return "Recovery failed: %s" % (snap.get("message") or "see run status")
    if kind in ("constrained", "scope_established"):
        budget = snap.get("budget") or {}
        constraint = budget.get("constraint") or {}
        if constraint:
            return "Scope constrained: %s" % (constraint.get("reason") or "budget pressure")
        return "Recovery checkpoint: %s." % kind.replace("_", " ")
    return "Recovery checkpoint recorded."


def merge_status(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if key in ("scope", "current", "findings", "budget", "rates", "eta") and isinstance(value, dict):
            merged = dict(out.get(key) or {})
            if key == "scope" and "locations" in value:
                merged["locations"] = list(value.get("locations") or [])
                nested = dict(value)
                nested.pop("locations", None)
                merged.update(nested)
            else:
                merged.update(value)
            out[key] = merged
        else:
            out[key] = value
    return out


def append_event(config: ResolvedConfig, run_id: str, event: Dict[str, Any]) -> None:
    row = dict(event)
    row.setdefault("at", iso_now())
    row.setdefault("type", "info")
    row.setdefault("label", "")
    append_jsonl(events_path(config, run_id), row)


def parse_json_arg(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if text == "-" or text == "":
        import sys

        text = sys.stdin.read()
    elif os.path.isfile(text):
        loaded = read_json(text, None)
        if not isinstance(loaded, dict):
            raise BearingError("JSON file must contain an object: %s" % text)
        return loaded
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BearingError("invalid JSON: %s" % exc)
    if not isinstance(data, dict):
        raise BearingError("JSON must be an object")
    return data


def _finish(config: ResolvedConfig, status_name: str, message: str, event: Dict[str, Any]) -> Dict[str, Any]:
    current = load_status(config)
    if current is None:
        current = start_run(config)
        current = load_status(config) or empty_status()
    status = merge_status(current, {"status": status_name, "message": message})
    if status_name == "completed":
        status["stage"] = STAGE_IDS[-1]
    _finalize(status, started_at=str(current.get("started_at") or iso_now()))
    _write_status(config, status)
    append_event(config, str(status["run_id"]), event)
    return snapshot(config, str(status["run_id"]))


def _finalize(status: Dict[str, Any], started_at: str) -> None:
    stage = str(status.get("stage") or STAGE_IDS[0])
    if stage not in STAGE_IDS:
        if str(status.get("stage_index") or "").isdigit():
            idx = max(1, min(int(status["stage_index"]), len(STAGE_IDS)))
            stage = STAGE_IDS[idx - 1]
        else:
            stage = STAGE_IDS[0]
    status["stage"] = stage
    status["stage_index"] = STAGE_IDS.index(stage) + 1
    status["stage_count"] = len(STAGES)
    status["stage_label"] = STAGE_LABELS[stage]
    status["started_at"] = started_at
    status["updated_at"] = iso_now()
    status["elapsed_seconds"] = _elapsed_seconds(started_at, status["updated_at"])
    status["eta"] = compute_eta(status)
    errors = validate(status, _schema())
    if errors:
        raise BearingError("invalid recovery status: %s" % "; ".join(errors))


def _elapsed_seconds(started_at: str, updated_at: str) -> int:
    try:
        start = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        return max(0, int((end - start).total_seconds()))
    except (TypeError, ValueError):
        return 0


def compute_eta(status: Dict[str, Any]) -> Dict[str, Any]:
    """Per-stage rates plus remaining-stage ranges — never locations/total * stages."""
    stage = str(status.get("stage") or STAGE_IDS[0])
    rates = status.get("rates") or {}
    stage_rate = rates.get(stage) if isinstance(rates.get(stage), dict) else {}
    samples = int(stage_rate.get("samples") or 0)
    per_minute = float(stage_rate.get("per_minute") or 0)
    remaining_units = _remaining_units(status)
    if per_minute > 0 and remaining_units is not None:
        current_seconds = remaining_units / per_minute * 60.0
    else:
        remaining_stages = len(STAGE_IDS) - STAGE_IDS.index(stage) + 1
        current_seconds = remaining_stages * 90.0
    later = _later_stage_seconds(status)
    low = max(0, int(current_seconds * 0.7 + later * 0.5))
    high = max(low, int(current_seconds * 1.4 + later * 1.5))
    if samples < 3:
        confidence = "low"
    elif samples < 8:
        confidence = "medium"
    else:
        confidence = "high"
        mid = max(1, (low + high) // 2)
        low = int(mid * 0.85)
        high = max(low, int(mid * 1.15))
    return {
        "remaining_seconds_low": low,
        "remaining_seconds_high": high,
        "confidence": confidence,
        "display": _format_eta(low, high, confidence, status.get("status") == "completed"),
    }


def _remaining_units(status: Dict[str, Any]) -> Optional[float]:
    stage = status.get("stage")
    scope = status.get("scope") or {}
    findings = status.get("findings") or {}
    if stage == "discover":
        total = float(scope.get("locations_total") or 0)
        scanned = float(scope.get("locations_scanned") or 0)
        return max(0.0, total - scanned) if total else None
    if stage == "extract":
        queued = float(findings.get("candidate_decisions") or 0)
        evidence = float(findings.get("evidence_items") or 0)
        return max(0.0, queued * 2 - evidence) if queued else None
    if stage in ("identify", "synthesize"):
        prepared = float(findings.get("records_prepared") or 0)
        decisions = float(findings.get("candidate_decisions") or 0)
        return max(0.0, decisions - prepared) if decisions else None
    if stage == "write_persist":
        prepared = float(findings.get("records_prepared") or 0)
        written = float(findings.get("records_written") or 0)
        return max(0.0, prepared - written)
    return None


def _later_stage_seconds(status: Dict[str, Any]) -> float:
    stage = str(status.get("stage") or STAGE_IDS[0])
    idx = STAGE_IDS.index(stage)
    defaults = {
        "scope_plan": 30,
        "discover": 120,
        "extract": 180,
        "identify": 90,
        "synthesize": 90,
        "write_persist": 45,
    }
    return float(sum(defaults[sid] for sid in STAGE_IDS[idx + 1 :]))


def _format_eta(low: int, high: int, confidence: str, done: bool) -> str:
    if done:
        return "Done"
    if high <= 0 and low <= 0:
        return "—"
    if confidence == "high" and abs(high - low) < 45:
        return "~%s" % _human_seconds((low + high) // 2)
    return "%s–%s" % (_human_seconds(low), _human_seconds(high))


def _human_seconds(value: int) -> str:
    if value < 60:
        return "%ds" % value
    minutes, seconds = divmod(value, 60)
    if minutes < 60:
        if seconds and minutes < 10:
            return "%dm %ds" % (minutes, seconds)
        return "%dm" % minutes
    hours, minutes = divmod(minutes, 60)
    return "%dh %dm" % (hours, minutes)


def _schema() -> Dict[str, Any]:
    return read_json(schema_path("recovery-status.schema.json"), {}) or {}


def _write_status(config: ResolvedConfig, status: Dict[str, Any]) -> None:
    path = status_path(config, str(status["run_id"]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = dump_json(status)
    descriptor, temporary = tempfile.mkstemp(prefix=".bearing-recovery-", dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass
