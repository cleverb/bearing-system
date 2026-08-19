"""`bearing lint`: structural integrity of the decision graph.

@see ADR-0004 — this is the *only* class of check permitted to block a merge,
alongside violation of an accepted Contract. A recovery confidence score may
not.

This is the *only* class of check permitted to block a merge, alongside violation
of an accepted Contract. Everything here is a broken link or a dead end -- a
verifiable structural fact, not a judgment about evidence.

The line matters. A recovery pass's confidence score, however high, may only flag
and route to review. A broken anchor is different in kind: it is not an opinion
about whether a decision exists, it is a pointer to a decision that does not.
"""

from __future__ import annotations

import os
import ntpath
import re
from typing import Dict, List, Optional, Tuple

from .config import ResolvedConfig
from .decisions import (
    ACCEPTED,
    CANDIDATE_STATES,
    DEPRECATED,
    PROPOSED,
    SUPERSEDED,
    build_index,
    estimate_index_tokens,
    load_candidates,
    load_records,
    scan_anchors,
    surfaced_candidates,
    path_matches_scope,
)
from .util import read_json
from .workspace import effective_workspace_files


class Finding:
    def __init__(self, severity: str, code: str, message: str, location: str = "") -> None:
        self.severity = severity  # "error" | "warning"
        self.code = code
        self.message = message
        self.location = location

    def render(self) -> str:
        prefix = "%s [%s]" % (self.severity.upper(), self.code)
        if self.location:
            return "%s %s: %s" % (prefix, self.location, self.message)
        return "%s %s" % (prefix, self.message)


def run(config: ResolvedConfig) -> List[Finding]:
    layout = config.layout
    findings: List[Finding] = []
    records = load_records(layout)
    by_id = {record.id: record for record in records}
    effective_files = effective_workspace_files(config)

    by_record_id: Dict[str, List] = {}
    for record in records:
        by_record_id.setdefault(record.id, []).append(record)
    for record_id, duplicates in sorted(by_record_id.items()):
        if len(duplicates) > 1:
            findings.append(
                Finding(
                    "error",
                    "duplicate-record-id",
                    "%s is defined by multiple records: %s. Category directories do not "
                    "create separate ADR namespaces."
                    % (record_id, ", ".join(record.rel for record in duplicates)),
                )
            )

    scope = config.get("scope") or {}
    anchors, orphan_deprecations, shadow_anchors = scan_anchors(
        layout, scope.get("include") or None, scope.get("exclude") or None
    )

    # --- anchor integrity: a hard failure, because it is a broken pointer ----
    for anchor in anchors:
        if anchor.adr_id not in by_id:
            findings.append(
                Finding(
                    "error",
                    "anchor-unresolved",
                    "@see %s does not resolve to any record in %s"
                    % (anchor.adr_id, layout.decisions_rel),
                    "%s:%d" % (anchor.file, anchor.line),
                )
            )
            continue
        record = by_id[anchor.adr_id]
        if record.status == SUPERSEDED and not record.superseded_by:
            findings.append(
                Finding(
                    "error",
                    "anchor-dead-end",
                    "@see %s points at a Superseded record with no successor, so an agent "
                    "following it is stopped with nowhere to go" % anchor.adr_id,
                    "%s:%d" % (anchor.file, anchor.line),
                )
            )
        elif record.status == DEPRECATED:
            findings.append(
                Finding(
                    "warning",
                    "anchor-deprecated",
                    "@see %s points at a Deprecated record" % anchor.adr_id,
                    "%s:%d" % (anchor.file, anchor.line),
                )
            )

    for path, line, raw in shadow_anchors:
        findings.append(
            Finding(
                "error",
                "anchor-into-shadow",
                "anchor points into the shadow graph. A candidate is a claim about evidence, "
                "not a decision; anchoring to one grants inference an authority nobody "
                "conferred.",
                "%s:%d" % (path, line),
            )
        )

    for path, line in orphan_deprecations:
        findings.append(
            Finding(
                "warning",
                "deprecated-without-anchor",
                "@deprecated with no nearby @see. An agent is forbidden from refactoring this "
                "and has no record to consult, which is a guaranteed escalation with no "
                "resolution path.",
                "%s:%d" % (path, line),
            )
        )

    # --- record-level lifecycle honesty -------------------------------------
    for record in records:
        if record.status == SUPERSEDED and not record.superseded_by:
            findings.append(
                Finding(
                    "error",
                    "superseded-without-successor",
                    "status is Superseded but no `superseded_by` is set",
                    record.rel,
                )
            )
        if record.superseded_by and record.superseded_by not in by_id:
            findings.append(
                Finding(
                    "error",
                    "successor-unresolved",
                    "`superseded_by: %s` does not resolve to a record" % record.superseded_by,
                    record.rel,
                )
            )
        if not record.status:
            findings.append(
                Finding("error", "missing-status", "no Status; lifecycle state is unknowable", record.rel)
            )
        missing = record.missing_index_fields()
        if missing:
            findings.append(
                Finding(
                    "warning",
                    "incomplete-front-matter",
                    "missing %s, so its index entry is incomplete and it may never surface "
                    "when relevant" % ", ".join(missing),
                    record.rel,
                )
            )

    findings.extend(_scope_findings(records, anchors, by_id, effective_files))

    # --- bidirectionality ---------------------------------------------------
    anchored_ids = {anchor.adr_id for anchor in anchors}
    for record in records:
        if record.status == ACCEPTED and record.id not in anchored_ids:
            findings.append(
                Finding(
                    "warning",
                    "record-without-anchor",
                    "accepted record with no anchor in the codebase. A record reachable from "
                    "nothing is the original failure mode this system exists to fix.",
                    record.rel,
                )
            )

    # --- index freshness ----------------------------------------------------
    findings.extend(_index_findings(config, records))

    # --- shadow graph hygiene -----------------------------------------------
    findings.extend(_shadow_findings(config))
    findings.extend(_candidate_schema_findings(config))

    return findings


def _scope_findings(records, anchors, by_id, effective_files: List[str]) -> List[Finding]:
    """Scope is a Discover edge, so stale or dishonest scope is structural."""
    findings: List[Finding] = []
    for record in records:
        if not record.scope:
            if record.scope_allow_empty or record.scope_empty_reason:
                findings.append(
                    Finding(
                        "error",
                        "scope-empty-exception-without-scope",
                        "scope_allow_empty and scope_empty_reason require an explicit scope",
                        record.rel,
                    )
                )
            continue

        invalid = _invalid_scope_patterns(record.scope)
        if invalid:
            findings.append(
                Finding(
                    "error",
                    "scope-invalid",
                    "; ".join(invalid),
                    record.rel,
                )
            )
            continue

        matches = [path for path in effective_files if path_matches_scope(path, record.scope)]
        if record.scope_empty_reason and not record.scope_allow_empty:
            findings.append(
                Finding(
                    "warning",
                    "scope-empty-reason-without-exception",
                    "scope_empty_reason has no effect unless scope_allow_empty is true",
                    record.rel,
                )
            )
        if record.scope_allow_empty and (
            record.status != ACCEPTED or record.eocr_function != "Contract"
        ):
            findings.append(
                Finding(
                    "error",
                    "scope-empty-exception-non-contract",
                    "scope_allow_empty is valid only for an Accepted Contract",
                    record.rel,
                )
            )
        if record.scope_allow_empty and not record.scope_empty_reason:
            findings.append(
                Finding(
                    "error",
                    "scope-empty-reason-missing",
                    "scope_allow_empty requires a non-empty scope_empty_reason",
                    record.rel,
                )
            )
        if matches and record.scope_allow_empty:
            findings.append(
                Finding(
                    "warning",
                    "scope-empty-exception-stale",
                    "scope now matches %d effective workspace file(s); remove scope_allow_empty"
                    % len(matches),
                    record.rel,
                )
            )
        elif not matches:
            if record.scope_allow_empty and record.scope_empty_reason:
                findings.append(
                    Finding(
                        "warning",
                        "scope-intentionally-empty",
                        "scope matches no effective workspace files: %s"
                        % record.scope_empty_reason,
                        record.rel,
                    )
                )
            else:
                hard = record.status == ACCEPTED and record.eocr_function == "Contract"
                findings.append(
                    Finding(
                        "error" if hard else "warning",
                        "scope-no-matches",
                        "scope %r matches no effective workspace files" % record.scope,
                        record.rel,
                    )
                )

    for anchor in anchors:
        record = by_id.get(anchor.adr_id)
        if (
            record is not None
            and record.status == ACCEPTED
            and record.eocr_function == "Contract"
            and record.scope
            and not path_matches_scope(anchor.file, record.scope)
        ):
            findings.append(
                Finding(
                    "error",
                    "anchor-outside-contract-scope",
                    "@see %s is a governing Anchor, but %s is outside Contract scope %r"
                    % (record.id, anchor.file, record.scope),
                    "%s:%d" % (anchor.file, anchor.line),
                )
            )
    return findings


def _invalid_scope_patterns(scope: str) -> List[str]:
    errors: List[str] = []
    patterns = [part.strip() for part in scope.replace(";", ",").split(",")]
    for pattern in patterns:
        if not pattern:
            errors.append("scope contains an empty pattern")
            continue
        normalized = pattern.replace("\\", "/")
        if normalized.startswith("/") or ntpath.isabs(pattern):
            errors.append("scope pattern %r must be workspace-relative" % pattern)
        if ".." in normalized.split("/"):
            errors.append("scope pattern %r may not traverse through '..'" % pattern)
        if re.search(r"\[[^\]]*$", normalized):
            errors.append("scope pattern %r has an unterminated character class" % pattern)
    return errors


def _index_findings(config: ResolvedConfig, records) -> List[Finding]:
    layout = config.layout
    findings: List[Finding] = []
    expected = build_index(records)
    actual = read_json(layout.index)

    if actual is None:
        findings.append(
            Finding("error", "index-missing", "no %s; run `bearing index`" % layout.index_name)
        )
        return findings

    if actual.get("entries") != expected.get("entries"):
        findings.append(
            Finding(
                "error",
                "index-stale",
                "%s does not match the records on disk; run `bearing index`" % layout.index_name,
            )
        )

    budget = int(config.get("verify.index_token_budget") or 4000)
    tokens = estimate_index_tokens(expected)
    if tokens > budget:
        findings.append(
            Finding(
                "error",
                "index-over-budget",
                "index is roughly %d tokens against a budget of %d. This file is loaded on "
                "every task, so unbounded growth silently reverses the framework's value -- "
                "shorten triggers or raise the budget deliberately." % (tokens, budget),
            )
        )
    elif tokens > budget * 0.8:
        findings.append(
            Finding(
                "warning",
                "index-near-budget",
                "index is roughly %d tokens, over 80%% of the %d budget" % (tokens, budget),
            )
        )

    return findings


def _shadow_findings(config: ResolvedConfig) -> List[Finding]:
    layout = config.layout
    findings: List[Finding] = []
    candidates = load_candidates(layout)

    surfaced = surfaced_candidates(candidates)
    wave_size = int(config.get("review.wave_size") or 25)
    if len(surfaced) > wave_size:
        findings.append(
            Finding(
                "warning",
                "review-queue-over-wave",
                "%d candidates would surface at once against a wave size of %d. A queue larger "
                "than one person clears in the declared budget does not get reviewed carefully, "
                "it gets rubber-stamped." % (len(surfaced), wave_size),
            )
        )

    for candidate in candidates:
        state = candidate.get("lifecycle_state")
        if state is not None and state not in CANDIDATE_STATES:
            findings.append(
                Finding(
                    "error",
                    "candidate-bad-state",
                    "candidate %s has unknown lifecycle_state %r"
                    % (candidate.get("candidate_id", "?"), state),
                )
            )
        if state == "Promoted" and not candidate.get("promoted_to"):
            findings.append(
                Finding(
                    "warning",
                    "promotion-without-target",
                    "candidate %s is Promoted but records no `promoted_to`, so the audit trail "
                    "from evidence to record is broken" % candidate.get("candidate_id", "?"),
                )
            )

    return findings


def _candidate_schema_findings(config: ResolvedConfig) -> List[Finding]:
    """Validate shadow-graph JSONL against the packaged candidate schema.

    Agents write these rows by hand. The CLI's job is to catch a malformed
    object before a reviewer spends time on it.
    """
    from .jsonschema import validate
    from .paths import plugin_root
    from .util import read_json

    layout = config.layout
    findings: List[Finding] = []
    candidates = load_candidates(layout)
    if not candidates:
        return findings

    root = plugin_root()
    schema = read_json(
        os.path.join(root, "skills", "decision-recovery", "schemas", "candidate.schema.json")
    )
    evidence = read_json(
        os.path.join(root, "skills", "decision-recovery", "schemas", "evidence.schema.json")
    )
    if not isinstance(schema, dict):
        return findings
    items = ((schema.get("properties") or {}).get("evidence") or {}).get("items")
    if isinstance(items, dict) and items.get("$ref") == "evidence.schema.json" and isinstance(
        evidence, dict
    ):
        schema = dict(schema)
        properties = dict(schema.get("properties") or {})
        evidence_prop = dict(properties.get("evidence") or {})
        evidence_prop["items"] = evidence
        properties["evidence"] = evidence_prop
        schema["properties"] = properties

    location = os.path.relpath(layout.candidates, config.workspace).replace(os.sep, "/")
    for candidate in candidates:
        ident = candidate.get("candidate_id") or "?"
        for error in validate(candidate, schema):
            findings.append(
                Finding(
                    "error",
                    "candidate-schema",
                    "candidate %s: %s" % (ident, error),
                    location,
                )
            )
    return findings


def summarize(findings: List[Finding]) -> Tuple[int, int]:
    errors = len([finding for finding in findings if finding.severity == "error"])
    warnings = len([finding for finding in findings if finding.severity == "warning"])
    return errors, warnings
