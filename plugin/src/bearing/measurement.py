"""Schema-validated, optional measurement plumbing."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Any, Dict, List

from .config import ResolvedConfig
from .jsonschema import validate
from .paths import schema_path
from .util import BearingError, read_json, read_jsonl

OBSERVED = {
    "escalation": frozenset({"escalate", "proceed"}),
    "negative": frozenset({"decision", "none", "no_decision"}),
}


def observe(config: ResolvedConfig, set_name: str, case_id: str, observed: str) -> Dict[str, Any]:
    if observed not in OBSERVED.get(set_name, frozenset()):
        raise BearingError(
            "observed value for %s must be one of %s"
            % (set_name, ", ".join(sorted(OBSERVED.get(set_name, frozenset()))))
        )
    path = os.path.join(config.layout.eval_dir, set_name, "cases.jsonl")
    rows = read_jsonl(path)
    matching = [
        index
        for index, row in enumerate(rows)
        if isinstance(row, dict) and (row.get("id") or row.get("case_id")) == case_id
    ]
    if not matching:
        raise BearingError("no case %r in %s" % (case_id, path))
    if len(matching) > 1:
        raise BearingError("case id %r occurs more than once in %s" % (case_id, path))
    row = dict(rows[matching[0]])
    row["observed"] = observed
    errors = validate(row, _schema("observation.schema.json"))
    if errors:
        raise BearingError("invalid observation: %s" % "; ".join(errors))
    rows[matching[0]] = row
    _atomic_write(path, "".join(json.dumps(item, sort_keys=True) + "\n" for item in rows))
    return row


def add_ledger_row(config: ResolvedConfig, source: str) -> Dict[str, Any]:
    if source == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(source, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as error:
            raise BearingError("cannot read ledger row %s: %s" % (source, error))
    try:
        row = json.loads(text)
    except ValueError as error:
        raise BearingError("ledger row is not valid JSON: %s" % error)
    if not isinstance(row, dict):
        raise BearingError("ledger row must be a JSON object")
    errors = validate(row, _schema("ledger-row.schema.json"))
    if errors:
        raise BearingError("invalid ledger row: %s" % "; ".join(errors))
    os.makedirs(os.path.dirname(config.layout.cost_ledger), exist_ok=True)
    with open(config.layout.cost_ledger, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def score_set(config: ResolvedConfig, set_name: str) -> Dict[str, Any]:
    path = os.path.join(config.layout.eval_dir, set_name, "cases.jsonl")
    rows = [row for row in read_jsonl(path) if isinstance(row, dict)]
    errors: List[str] = []
    schema = _schema("observation.schema.json")
    ids = set()
    for index, row in enumerate(rows):
        errors.extend("row %d: %s" % (index + 1, error) for error in validate(row, schema))
        ident = row.get("id") or row.get("case_id")
        if ident in ids:
            errors.append("row %d: duplicate id %r" % (index + 1, ident))
        ids.add(ident)
    scored = [row for row in rows if row.get("observed") is not None]
    result: Dict[str, Any] = {
        "set": set_name,
        "path": path,
        "cases": len(rows),
        "scored": len(scored),
        "errors": errors,
        "warnings": [] if scored else ["no observations; this measurement is unmeasured, not passed"],
    }
    if set_name == "escalation":
        must = [row for row in scored if row.get("expects") == "escalate"]
        proceed = [row for row in scored if row.get("expects") == "proceed"]
        result["recall"] = (
            len([row for row in must if row.get("observed") == "escalate"]) / len(must)
            if must else None
        )
        result["false_escalation_rate"] = (
            len([row for row in proceed if row.get("observed") == "escalate"]) / len(proceed)
            if proceed else None
        )
    elif set_name == "negative":
        result["hallucination_rate"] = (
            len([row for row in scored if row.get("observed") == "decision"]) / len(scored)
            if scored else None
        )
    return result


def _schema(name: str) -> Dict[str, Any]:
    return read_json(schema_path(name), {}) or {}


def _atomic_write(path: str, content: str) -> None:
    """Replace a JSONL dataset atomically after the complete result validates."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".bearing-observe-", dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
