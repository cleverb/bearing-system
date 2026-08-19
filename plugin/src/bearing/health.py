"""`bearing health`: aggregation only, never a third checking system."""

from __future__ import annotations

from typing import Any, Dict

from .compatibility import runtime_statuses
from .decisions import ACCEPTED, PROPOSED, load_candidates, load_records, scan_anchors
from .lint import run as lint_run
from .verify import run as verify_run
from .workspace import effective_workspace_files


def aggregate(config) -> Dict[str, Any]:
    """Present existing results and descriptive counts without creating checks."""
    lint_findings = lint_run(config)
    verify_results = verify_run(config)
    records = load_records(config.layout)
    scope = config.get("scope") or {}
    anchors, _, _ = scan_anchors(
        config.layout, scope.get("include") or None, scope.get("exclude") or None
    )
    files = effective_workspace_files(config)
    return {
        "findings": [
            {
                "source": "lint",
                "code": finding.code,
                "status": finding.severity,
                "message": finding.message,
                "location": finding.location,
            }
            for finding in lint_findings
        ]
        + [
            {
                "source": "verify",
                "code": "%s:%s" % (result.pillar, result.name),
                "status": result.status,
                "message": result.detail,
                "authority": "hard" if result.hard else "advisory",
            }
            for result in verify_results
            if result.status != "ok"
        ],
        "runtime_compatibility": runtime_statuses(config),
        "descriptive_counts": {
            "effective_workspace_files": len(files),
            "records": len(records),
            "accepted_records": len([record for record in records if record.status == ACCEPTED]),
            "proposed_records": len([record for record in records if record.status == PROPOSED]),
            "anchors": len(anchors),
            "shadow_candidates": len(load_candidates(config.layout)),
        },
    }


def render(result: Dict[str, Any]) -> str:
    counts = result["descriptive_counts"]
    lines = ["# BEARING health", "", "Descriptive counts"]
    for key, value in sorted(counts.items()):
        lines.append("  %-28s %s" % (key.replace("_", " "), value))
    lines += ["", "Findings (aggregated from lint/verify)"]
    if not result["findings"]:
        lines.append("  none")
    for finding in result["findings"]:
        lines.append(
            "  %-7s %-8s %s"
            % (finding["source"], finding["status"], finding["code"])
        )
    lines += ["", "Runtime compatibility"]
    for runtime in result["runtime_compatibility"]:
        lines.append(
            "  %-8s %-20s %s"
            % (runtime["runtime"], runtime["status"], runtime["discovery_mode"])
        )
    return "\n".join(lines) + "\n"
