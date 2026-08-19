"""Human disposition of shadow candidates: Promote, Edit, Split, Reject, Defer.

BEARING permits one-click *execution* of a human promotion decision. It forbids
one-click *substitution* for that decision. Promote therefore requires explicit
judgment fields (scope, present validity, authored lifecycle, EOCR function);
confidence alone never authorizes writing into the decision graph.

@see docs/specs/decision-recovery-skill-spec.md — Candidate disposition
"""

from __future__ import annotations

import datetime
import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .config import ResolvedConfig
from .decisions import (
    ACCEPTED,
    EOCR_FUNCTIONS,
    LIFECYCLE_STATES,
    PROPOSED,
    load_candidates,
    load_records,
    surfaced_candidates,
)
from .paths import Layout
from .util import (
    BearingError,
    append_jsonl,
    dump_json,
    emit_frontmatter,
    write_json,
    write_jsonl,
    write_text,
)

ACTIONS = ("Promote", "Edit", "Split", "Reject", "Defer")


@dataclass
class Judgment:
    """Human-determined fields that accompany a disposition action."""

    eocr_function: str = ""
    lifecycle_state: str = PROPOSED
    scope: str = ""
    still_valid: Optional[bool] = None
    title: str = ""
    trigger: str = ""
    anchor_targets: List[str] = field(default_factory=list)
    rejection_reason: str = ""
    defer_note: str = ""
    edit_object: str = ""
    split_brief: str = ""

    @classmethod
    def from_mapping(cls, data: Optional[Dict[str, Any]]) -> "Judgment":
        data = data or {}
        still = data.get("still_valid")
        if isinstance(still, str):
            lowered = still.strip().lower()
            if lowered in ("true", "yes", "1"):
                still = True
            elif lowered in ("false", "no", "0"):
                still = False
            elif lowered == "":
                still = None
        anchors = data.get("anchor_targets") or []
        if isinstance(anchors, str):
            anchors = [part.strip() for part in anchors.replace(";", ",").split(",") if part.strip()]
        return cls(
            eocr_function=str(data.get("eocr_function") or "").strip(),
            lifecycle_state=str(data.get("lifecycle_state") or PROPOSED).strip() or PROPOSED,
            scope=str(data.get("scope") or "").strip(),
            still_valid=still if isinstance(still, bool) else None,
            title=str(data.get("title") or "").strip(),
            trigger=str(data.get("trigger") or "").strip(),
            anchor_targets=list(anchors),
            rejection_reason=str(data.get("rejection_reason") or "").strip(),
            defer_note=str(data.get("defer_note") or "").strip(),
            edit_object=str(data.get("edit_object") or "").strip(),
            split_brief=str(data.get("split_brief") or "").strip(),
        )


@dataclass
class DispositionResult:
    action: str
    candidate_id: str
    message: str
    promoted_to: str = ""
    adr_path: str = ""
    suggested_anchors: List[str] = field(default_factory=list)
    candidate: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "candidate_id": self.candidate_id,
            "message": self.message,
            "promoted_to": self.promoted_to,
            "adr_path": self.adr_path,
            "suggested_anchors": list(self.suggested_anchors),
            "candidate": self.candidate,
        }


def list_reviewable(layout: Layout) -> List[Dict[str, Any]]:
    """Surfaced candidates still waiting on human disposition."""
    return surfaced_candidates(load_candidates(layout))


def find_candidate(layout: Layout, candidate_id: str) -> Dict[str, Any]:
    for candidate in load_candidates(layout):
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    raise BearingError("no candidate with id %r" % candidate_id)


def candidate_brief(candidate: Dict[str, Any]) -> str:
    """Human-readable evidence summary for elicitation / CLI prompts."""
    evidence = candidate.get("evidence") or []
    lines = [
        "Candidate: %s" % candidate.get("candidate_id"),
        "Subject: %s" % candidate.get("subject"),
        "Relation: %s" % candidate.get("candidate_relation"),
        "Proposed: %s" % candidate.get("candidate_object"),
        "Suggested EOCR: %s" % candidate.get("candidate_eocr_function"),
        "Confidence: %s" % candidate.get("confidence"),
        "Lifecycle: %s" % candidate.get("lifecycle_state"),
    ]
    if candidate.get("conflicts_with_accepted"):
        lines.append("Conflicts: %s" % candidate.get("conflicts_with_accepted"))
    else:
        lines.append("Conflicts: None")
    lines.append("Evidence (%d):" % len(evidence))
    for index, item in enumerate(evidence[:6], 1):
        if not isinstance(item, dict):
            continue
        excerpt = str(item.get("evidence_excerpt") or "").strip().replace("\n", " ")
        if len(excerpt) > 160:
            excerpt = excerpt[:157] + "..."
        lines.append(
            "  %d. [%s] %s"
            % (index, item.get("evidence_source") or "unknown", excerpt or "(empty)")
        )
    if len(evidence) > 6:
        lines.append("  … %d more" % (len(evidence) - 6))
    return "\n".join(lines)


def elicitation_schema(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """JSON Schema for MCP form elicitation / structured CLI collection."""
    suggested_eocr = candidate.get("candidate_eocr_function") or "Rationale"
    if suggested_eocr not in EOCR_FUNCTIONS:
        suggested_eocr = "Rationale"
    suggested_scope = str(candidate.get("subject") or "").strip()
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "title": "Disposition",
                "description": (
                    "Promote executes a human judgment (not confidence). "
                    "Edit revises the candidate. Split returns a brief. "
                    "Reject records a durable fingerprint. Defer leaves it queued."
                ),
                "enum": list(ACTIONS),
            },
            "still_valid": {
                "type": "boolean",
                "title": "Still valid today?",
                "description": "Required for Promote: is this still organizational intent?",
            },
            "eocr_function": {
                "type": "string",
                "title": "EOCR function",
                "enum": list(EOCR_FUNCTIONS),
                "default": suggested_eocr,
            },
            "lifecycle_state": {
                "type": "string",
                "title": "Authored lifecycle status",
                "enum": list(LIFECYCLE_STATES),
                "default": ACCEPTED,
                "description": "Status for the authored decision record (not the shadow lifecycle).",
            },
            "scope": {
                "type": "string",
                "title": "Scope",
                "description": "Comma-separated globs the decision governs.",
                "default": suggested_scope,
            },
            "title": {
                "type": "string",
                "title": "ADR title",
                "description": "Optional; defaults from the candidate object.",
            },
            "trigger": {
                "type": "string",
                "title": "Index trigger",
                "description": "Situation when an agent needs this record.",
            },
            "anchor_targets": {
                "type": "string",
                "title": "Suggested anchor files",
                "description": "Optional comma-separated paths for @see placement (not auto-written).",
            },
            "edit_object": {
                "type": "string",
                "title": "Revised candidate_object",
                "description": "Used by Edit to replace the proposed statement.",
            },
            "rejection_reason": {
                "type": "string",
                "title": "Rejection reason",
            },
            "defer_note": {
                "type": "string",
                "title": "Defer note",
            },
            "split_brief": {
                "type": "string",
                "title": "Split notes",
                "description": "How the evidence should be split into multiple decisions.",
            },
        },
        "required": ["action"],
    }


def dispose(
    config: ResolvedConfig,
    candidate_id: str,
    action: str,
    judgment: Optional[Judgment] = None,
    *,
    rebuild_index: bool = True,
) -> DispositionResult:
    """Apply a human disposition. Mechanical execution; judgment must already be present."""
    layout = config.layout
    action = _normalize_action(action)
    judgment = judgment or Judgment()
    candidates = load_candidates(layout)
    index = _index_of(candidates, candidate_id)
    candidate = dict(candidates[index])

    if action == "Promote":
        result = _promote(config, candidate, judgment, rebuild_index=rebuild_index)
    elif action == "Reject":
        result = _reject(layout, candidate, judgment)
    elif action == "Edit":
        result = _edit(layout, candidate, judgment)
    elif action == "Defer":
        result = _defer(layout, candidate, judgment)
    elif action == "Split":
        result = _split(layout, candidate, judgment)
    else:  # pragma: no cover - guarded by _normalize_action
        raise BearingError("unknown disposition action %r" % action)

    candidates[index] = result.candidate
    write_jsonl(layout.candidates, candidates)
    return result


def defaults_from_candidate(candidate: Dict[str, Any]) -> Judgment:
    """Pre-fill elicitation defaults from the candidate (editable by the human)."""
    eocr = str(candidate.get("candidate_eocr_function") or "Rationale")
    if eocr not in EOCR_FUNCTIONS:
        eocr = "Rationale"
    return Judgment(
        eocr_function=eocr,
        lifecycle_state=ACCEPTED,
        scope=str(candidate.get("subject") or ""),
        title=_default_title(candidate),
        trigger=str(candidate.get("candidate_object") or "")[:120],
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _promote(
    config: ResolvedConfig,
    candidate: Dict[str, Any],
    judgment: Judgment,
    *,
    rebuild_index: bool,
) -> DispositionResult:
    _require_promote_judgment(judgment)
    if judgment.still_valid is not True:
        raise BearingError(
            "Promote requires still_valid=true; declining present validity is Reject or Defer, not Promote"
        )
    if judgment.eocr_function not in EOCR_FUNCTIONS:
        raise BearingError(
            "Promote requires eocr_function in %s" % ", ".join(EOCR_FUNCTIONS)
        )
    if judgment.lifecycle_state not in LIFECYCLE_STATES:
        raise BearingError(
            "Promote requires lifecycle_state in %s" % ", ".join(LIFECYCLE_STATES)
        )
    if not judgment.scope.strip():
        raise BearingError("Promote requires a non-empty scope")

    layout = config.layout
    number = _next_record_number(layout)
    adr_id = "ADR-%04d" % number
    title = judgment.title or _default_title(candidate)
    trigger = judgment.trigger or str(candidate.get("candidate_object") or title)
    slug = _slug(title)
    filename = "%04d-%s.md" % (number, slug)
    adr_path = os.path.join(layout.decisions, filename)
    if os.path.isfile(adr_path):
        raise BearingError("refusing to overwrite existing record %s" % filename)

    body = _render_adr(
        number=number,
        adr_id=adr_id,
        title=title,
        status=judgment.lifecycle_state,
        eocr=judgment.eocr_function,
        trigger=trigger,
        scope=judgment.scope,
        candidate=candidate,
        judgment=judgment,
    )
    write_text(adr_path, body)

    updated = dict(candidate)
    updated["lifecycle_state"] = "Promoted"
    updated["promoted_to"] = adr_id
    updated["candidate_eocr_function"] = judgment.eocr_function

    if rebuild_index:
        from .decisions import build_index

        write_json(layout.index, build_index(load_records(layout)))

    suggested = [
        "%s  # @see %s" % (path, adr_id) for path in judgment.anchor_targets
    ]
    if not suggested and candidate.get("subject"):
        suggested = ["%s  # @see %s" % (candidate["subject"], adr_id)]

    rel = os.path.relpath(adr_path, layout.workspace).replace(os.sep, "/")
    return DispositionResult(
        action="Promote",
        candidate_id=str(candidate.get("candidate_id")),
        message="Promoted %s → %s (%s). Place @see anchors in governed code."
        % (candidate.get("candidate_id"), adr_id, rel),
        promoted_to=adr_id,
        adr_path=rel,
        suggested_anchors=suggested,
        candidate=updated,
    )


def _reject(
    layout: Layout, candidate: Dict[str, Any], judgment: Judgment
) -> DispositionResult:
    fingerprint = _fingerprint(candidate)
    row = {
        "candidate_id": candidate.get("candidate_id"),
        "rejected_evidence_fingerprint": fingerprint,
        "rejected_at": datetime.date.today().isoformat(),
        "reason": judgment.rejection_reason or "",
    }
    append_jsonl(layout.rejected, row)
    updated = dict(candidate)
    updated["lifecycle_state"] = "Rejected"
    updated["evidence_fingerprint"] = fingerprint
    return DispositionResult(
        action="Reject",
        candidate_id=str(candidate.get("candidate_id")),
        message="Rejected %s; fingerprint recorded so recovery will not re-litigate it."
        % candidate.get("candidate_id"),
        candidate=updated,
    )


def _edit(layout: Layout, candidate: Dict[str, Any], judgment: Judgment) -> DispositionResult:
    updated = dict(candidate)
    if judgment.edit_object:
        updated["candidate_object"] = judgment.edit_object
    if judgment.eocr_function:
        if judgment.eocr_function not in EOCR_FUNCTIONS:
            raise BearingError("edit eocr_function must be one of %s" % ", ".join(EOCR_FUNCTIONS))
        updated["candidate_eocr_function"] = judgment.eocr_function
    if judgment.scope:
        updated["subject"] = judgment.scope if not updated.get("subject") else updated["subject"]
        updated["disposition_scope"] = judgment.scope
    if judgment.defer_note:
        updated["disposition_note"] = judgment.defer_note
    updated["lifecycle_state"] = updated.get("lifecycle_state") or "Reviewable"
    if updated["lifecycle_state"] in ("Promoted", "Rejected", "Stale", "Insufficient Evidence"):
        updated["lifecycle_state"] = "Reviewable"
    return DispositionResult(
        action="Edit",
        candidate_id=str(candidate.get("candidate_id")),
        message="Revised %s; still Reviewable until Promote or Reject."
        % candidate.get("candidate_id"),
        candidate=updated,
    )


def _defer(layout: Layout, candidate: Dict[str, Any], judgment: Judgment) -> DispositionResult:
    updated = dict(candidate)
    updated["lifecycle_state"] = "Reviewable"
    if judgment.defer_note:
        updated["disposition_note"] = judgment.defer_note
    updated["deferred_at"] = datetime.date.today().isoformat()
    return DispositionResult(
        action="Defer",
        candidate_id=str(candidate.get("candidate_id")),
        message="Deferred %s; remains in the review queue."
        % candidate.get("candidate_id"),
        candidate=updated,
    )


def _split(layout: Layout, candidate: Dict[str, Any], judgment: Judgment) -> DispositionResult:
    updated = dict(candidate)
    updated["lifecycle_state"] = "Reviewable"
    brief = judgment.split_brief or (
        "Human requested split; prepare separate candidates before Promote."
    )
    updated["disposition_note"] = brief
    updated["split_requested"] = True
    return DispositionResult(
        action="Split",
        candidate_id=str(candidate.get("candidate_id")),
        message=(
            "Split requested for %s. Candidate stays Reviewable; "
            "author additional candidates then Promote each separately. Notes: %s"
        )
        % (candidate.get("candidate_id"), brief),
        candidate=updated,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_action(action: str) -> str:
    text = (action or "").strip()
    for name in ACTIONS:
        if text.lower() == name.lower():
            return name
    raise BearingError(
        "action must be one of %s (got %r)" % (", ".join(ACTIONS), action)
    )


def _require_promote_judgment(judgment: Judgment) -> None:
    missing = []
    if not judgment.eocr_function:
        missing.append("eocr_function")
    if not judgment.lifecycle_state:
        missing.append("lifecycle_state")
    if not judgment.scope:
        missing.append("scope")
    if judgment.still_valid is None:
        missing.append("still_valid")
    if missing:
        raise BearingError(
            "Promote refuses ceremonial approval: human must set %s"
            % ", ".join(missing)
        )


def _index_of(candidates: Sequence[Dict[str, Any]], candidate_id: str) -> int:
    for index, candidate in enumerate(candidates):
        if candidate.get("candidate_id") == candidate_id:
            return index
    raise BearingError("no candidate with id %r" % candidate_id)


def _next_record_number(layout: Layout) -> int:
    records = load_records(layout)
    return max([record.number or 0 for record in records] + [0]) + 1


def _default_title(candidate: Dict[str, Any]) -> str:
    obj = str(candidate.get("candidate_object") or candidate.get("subject") or "Recovered decision")
    obj = re.sub(r"\s+", " ", obj).strip()
    if len(obj) > 72:
        obj = obj[:69].rstrip() + "..."
    return obj


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return (slug or "decision")[:60]


def _fingerprint(candidate: Dict[str, Any]) -> str:
    existing = candidate.get("evidence_fingerprint")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()
    key = candidate.get("idempotency_key")
    if isinstance(key, str) and key.strip():
        return "idem:%s" % key.strip()
    payload = dump_json(
        {
            "subject": candidate.get("subject"),
            "object": candidate.get("candidate_object"),
            "evidence": candidate.get("evidence"),
        }
    )
    return "sha256:%s" % hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _render_adr(
    *,
    number: int,
    adr_id: str,
    title: str,
    status: str,
    eocr: str,
    trigger: str,
    scope: str,
    candidate: Dict[str, Any],
    judgment: Judgment,
) -> str:
    today = datetime.date.today().isoformat()
    front = {
        "id": adr_id,
        "status": status,
        "eocr_function": eocr,
        "trigger": trigger,
        "scope": scope,
    }
    evidence_lines = []
    for item in candidate.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        evidence_lines.append(
            "* [%s] %s"
            % (
                item.get("evidence_source") or "unknown",
                str(item.get("evidence_excerpt") or "").strip() or "(empty)",
            )
        )
    if not evidence_lines:
        evidence_lines = ["* (no evidence excerpts recorded on the candidate)"]

    deletion = (
        "If this constraint were removed, the behavior documented in the candidate "
        "object would no longer be protected. Confirm the concrete breakage before "
        "treating this as a Contract."
        if eocr == "Contract"
        else "Recorded as %s; strengthen to Contract only if a concrete deletion failure is named."
        % eocr
    )

    body = "\n".join(
        [
            "# %s: %s" % (adr_id, title),
            "",
            "* **Date:** %s" % today,
            "* **Promoted from:** %s" % candidate.get("candidate_id"),
            "* **Subject:** %s" % candidate.get("subject"),
            "",
            "## Context and Problem Statement",
            "",
            "Recovered from shadow-graph evidence. Proposed relation: **%s**."
            % (candidate.get("candidate_relation") or "governed_by"),
            "",
            "Proposed decision object:",
            "",
            "> %s" % (candidate.get("candidate_object") or ""),
            "",
            "## Decision Drivers",
            "",
            "* Human validation of present validity, scope, lifecycle, and EOCR function.",
            "* Evidence confidence was %s (evidence quality, not authority)."
            % candidate.get("confidence"),
            "",
            "## Considered Options",
            "",
            "1. Leave undocumented (continue relying on tribal knowledge).",
            "2. Promote this candidate into an authored decision record.",
            "",
            "## Decision Outcome",
            "",
            "Chosen option: **2**. Human disposition promoted this candidate.",
            "",
            "## Evidence",
            "",
            *evidence_lines,
            "",
            "## Consequences",
            "",
            "* Agents can discover this constraint via the decision index and `@see` anchors.",
            "* Scope: `%s`." % scope,
            "",
            "## Deletion test",
            "",
            deletion,
            "",
            "## Suggested anchors",
            "",
        ]
    )
    targets = judgment.anchor_targets or (
        [str(candidate["subject"])] if candidate.get("subject") else []
    )
    if targets:
        for path in targets:
            body += "* `%s` — add `@see %s`\n" % (path, adr_id)
    else:
        body += "* (none specified at promotion time)\n"
    body += "\n"
    return emit_frontmatter(front) + "\n" + body
