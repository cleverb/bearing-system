"""`bearing assessment`: agentic decision-readiness scorecard.

@see ADR-0009 — informational; always exits 0; runs without init.
@see ADR-0002 — stdout only; this command writes nothing.
@see ADR-0005 — standard library filesystem and regex scans.

`doctor` asks whether this BEARING install resolves. This command asks a
different question: how ready is the clone for agents to discover and respect
decisions, with or without BEARING. An unreadiness finding is a description of
the tree, not a merge gate.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import __version__
from .config import ResolvedConfig
from .decisions import DecisionRecord, load_records, scan_anchors
from .paths import Layout, detect_decision_dirs
from .util import parse_frontmatter, read_text

# Readiness bands, independent of whether BEARING is installed.
BAND_UNPREPARED = "unprepared"
BAND_RECORDED = "recorded"
BAND_DISCOVERABLE = "discoverable"
BAND_ANCHORED = "anchored"
BAND_REVIEW_AWARE = "review-aware"

# Overlay: what BEARING itself has done to this clone.
OVERLAY_ABSENT = "absent"
OVERLAY_INITIALIZED = "initialized"
OVERLAY_PROJECTED = "projected"

PRESENT = "present"
PARTIAL = "partial"
ABSENT = "absent"

_DISCOVERY_RE = re.compile(
    r"\bADRs?\b"
    r"|docs/decisions"
    r"|docs/adr"
    r"|architecture decision"
    r"|decision records?",
    re.IGNORECASE,
)
_REVIEW_EXTRA_RE = re.compile(
    r"@see|bearing context|bearing lint|decision integrity",
    re.IGNORECASE,
)

_STUB_BODY_CHARS = 250

# Fixed table. Order is the order recommendations print. Only fired ids emit.
_RECOMMENDATIONS: Tuple[Tuple[str, str], ...] = (
    (
        "corpus-missing",
        "Add numbered decision records under docs/decisions/ (or run `bearing init` "
        "to adopt an existing convention).",
    ),
    (
        "corpus-split",
        "Pick one decision directory; institutional memory split across two trees "
        "is worse than either location.",
    ),
    (
        "agents-md-nested",
        "Move AGENTS.md from .agents/ to the repository root so root-walking "
        "runtimes (Codex, others) load it.",
    ),
    (
        "agents-md-missing",
        "Add a root AGENTS.md that names the decision directory and tells agents "
        "to load it before generating code.",
    ),
    (
        "agents-md-no-pointer",
        "Reference the decision directory from AGENTS.md so agents discover it "
        "at generation time.",
    ),
    (
        "baseline-silent",
        "Point existing agent instruction files at the decision corpus so they "
        "do not load a constitution that never mentions ADRs.",
    ),
    (
        "anchors-missing",
        "Add `@see ADR-NNNN` on implementation that depends on a recorded decision.",
    ),
    (
        "review-template-missing",
        "Add .github/PULL_REQUEST_TEMPLATE.md with a decision-integrity checklist.",
    ),
    (
        "review-template-silent",
        "Mention ADRs, `@see`, or `bearing lint` in the pull-request template so "
        "review asks about decisions.",
    ),
    (
        "contributing-missing",
        "Add CONTRIBUTING.md that tells contributors to load the decision index "
        "before changing governed code.",
    ),
    (
        "contributing-silent",
        "Mention the decision directory or `@see` annotations in CONTRIBUTING.md.",
    ),
    (
        "bearing-uninitialized",
        "Run `bearing init` to scaffold config, project a constitution block, "
        "and enable lint/index.",
    ),
    (
        "bearing-unprojected",
        "Run `bearing render` so AGENTS.md carries the managed constitution block.",
    ),
    (
        "index-missing",
        "Run `bearing index` (or add an index next to the records) so agents can "
        "load a cheap summary before reading the corpus.",
    ),
    (
        "ci-missing",
        "After init, mention `bearing lint` in CI for structural checks. Do not "
        "gate merges on assessment or on a recovery signal.",
    ),
)


def assess(config: ResolvedConfig) -> Dict[str, Any]:
    """Scan the workspace. Pure function of the tree plus resolved config."""
    workspace = config.workspace
    detected = detect_decision_dirs(workspace)
    primary, competing = _primary_corpus(config, detected)
    records = _load_numbered(workspace, primary) if primary else []
    record_count = len(records)
    with_status = sum(1 for record in records if record.title and record.status)
    stubs = sum(1 for record in records if _is_stub(record))

    corpus_status, corpus_detail = _corpus_status(
        primary, record_count, with_status, stubs, competing
    )

    agents_root = os.path.join(workspace, "AGENTS.md")
    agents_nested = os.path.join(workspace, ".agents", "AGENTS.md")
    agents_text = read_text(agents_root)
    nested_only = os.path.isfile(agents_nested) and not os.path.isfile(agents_root)

    baselines = _agent_baselines(workspace, primary)
    names_corpus = any(item["present"] and item["mentions_corpus"] for item in baselines)
    discovery_status, discovery_detail = _discovery_status(
        os.path.isfile(agents_root), nested_only, names_corpus, primary
    )

    anchors, _, _ = _scan(config)
    anchor_count = len(anchors)
    unique_ids = sorted({anchor.adr_id for anchor in anchors})

    pr_paths = _pr_template_paths(workspace)
    pr_text = _concat_files(workspace, pr_paths)
    pr_related = _is_adr_related(pr_text, primary) if pr_text else False
    contributing_rel = "CONTRIBUTING.md" if os.path.isfile(
        os.path.join(workspace, "CONTRIBUTING.md")
    ) else None
    contributing_text = read_text(os.path.join(workspace, "CONTRIBUTING.md")) if contributing_rel else None
    contributing_related = _is_adr_related(contributing_text, primary) if contributing_text else False
    review_related = pr_related or contributing_related
    review_status, review_detail = _review_status(
        pr_paths, pr_related, contributing_rel, contributing_related
    )

    has_block = bool(agents_text and "BEARING:START" in agents_text)
    if has_block:
        overlay = OVERLAY_PROJECTED
    elif config.initialized:
        overlay = OVERLAY_INITIALIZED
    else:
        overlay = OVERLAY_ABSENT

    index_rel = _index_rel(config, primary)
    has_index = bool(index_rel and os.path.isfile(os.path.join(workspace, index_rel)))
    ci_mentions = _ci_mentions_bearing(workspace)

    band = _band(
        record_count=record_count,
        discoverable=discovery_status == PRESENT,
        anchored=anchor_count > 0,
        review_related=review_related,
    )

    findings = _findings(
        record_count=record_count,
        competing=competing,
        nested_only=nested_only,
        has_agents=os.path.isfile(agents_root),
        names_corpus=names_corpus,
        agents_mentions=bool(agents_text and _names_corpus(agents_text, primary)),
        silent_baselines=[item["id"] for item in baselines if item["present"] and not item["mentions_corpus"]],
        anchor_count=anchor_count,
        pr_paths=pr_paths,
        pr_related=pr_related,
        contributing_rel=contributing_rel,
        contributing_related=contributing_related,
        initialized=config.initialized,
        overlay=overlay,
        has_index=has_index,
        ci_mentions=ci_mentions,
    )
    recommendations = [
        {"id": finding_id, "text": text}
        for finding_id, text in _RECOMMENDATIONS
        if finding_id in findings
    ]

    return {
        "band": band,
        "bearing": overlay,
        "initialized": config.initialized,
        "dimensions": {
            "corpus": {
                "status": corpus_status,
                "detail": corpus_detail,
                "path": primary,
                "paths": [entry["path"] for entry in detected],
                "record_count": record_count,
                "with_status": with_status,
                "stubs": stubs,
            },
            "discovery": {
                "status": discovery_status,
                "detail": discovery_detail,
            },
            "anchors": {
                "status": PRESENT if anchor_count else ABSENT,
                "detail": (
                    "%d @see ADR-N annotation(s) (%s)"
                    % (anchor_count, ", ".join(unique_ids[:8]))
                    if anchor_count
                    else "0 @see ADR-N annotations in scanned sources"
                ),
                "count": anchor_count,
                "ids": unique_ids,
            },
            "review": {
                "status": review_status,
                "detail": review_detail,
                "pull_request_templates": pr_paths,
                "contributing": contributing_rel,
            },
            "baselines": baselines,
            "bearing": {
                "overlay": overlay,
                "index": index_rel if has_index else None,
                "ci": ci_mentions,
            },
        },
        "findings": [{"id": finding_id} for finding_id in findings],
        "recommendations": recommendations,
    }


def render_text(result: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# BEARING assessment  (bearing %s)" % __version__,
        "",
        "Readiness: %s" % result["band"],
        "BEARING:    %s" % result["bearing"],
        "",
    ]
    dims = result["dimensions"]
    lines.extend(_section("Corpus", dims["corpus"]["status"], dims["corpus"]["detail"]))
    lines.extend(_section("Discovery", dims["discovery"]["status"], dims["discovery"]["detail"]))
    lines.extend(_section("Anchors", dims["anchors"]["status"], dims["anchors"]["detail"]))
    lines.extend(_section("Review", dims["review"]["status"], dims["review"]["detail"]))

    lines.append("## Agent baselines")
    for item in dims["baselines"]:
        extra = item.get("detail") or ""
        if item["present"] and not item["mentions_corpus"]:
            note = "does not mention the corpus"
            extra = ("%s; %s" % (extra, note) if extra else note)
        lines.append("  %-8s  %s%s" % (
            PRESENT if item["present"] else ABSENT,
            item["id"],
            ("  (%s)" % extra) if extra else "",
        ))
    lines.append("")

    bearing = dims["bearing"]
    index_detail = bearing["index"] or "no disclosure index"
    ci_detail = "CI mentions bearing lint/verify" if bearing["ci"] else "CI does not mention bearing lint/verify"
    lines.extend(
        _section(
            "BEARING overlay",
            PRESENT if result["bearing"] == OVERLAY_PROJECTED else (
                PARTIAL if result["bearing"] == OVERLAY_INITIALIZED else ABSENT
            ),
            "%s; %s; %s" % (result["bearing"], index_detail, ci_detail),
        )
    )

    lines.append("## Recommendations")
    recs = result["recommendations"]
    if not recs:
        lines.append("None. The surfaces this command knows how to score are in place.")
    else:
        for index, rec in enumerate(recs, 1):
            lines.append("%d. %s" % (index, rec["text"]))
    lines.append("")
    lines.append("_Informational. This command always exits 0._")
    lines.append("")
    return "\n".join(lines)


def _section(title: str, status: str, detail: str) -> List[str]:
    return ["## %s" % title, "  %-8s  %s" % (status, detail), ""]


def _band(record_count: int, discoverable: bool, anchored: bool, review_related: bool) -> str:
    if record_count <= 0:
        return BAND_UNPREPARED
    if discoverable and anchored and review_related:
        return BAND_REVIEW_AWARE
    if discoverable and anchored:
        return BAND_ANCHORED
    if discoverable:
        return BAND_DISCOVERABLE
    return BAND_RECORDED


def _primary_corpus(
    config: ResolvedConfig, detected: List[Dict[str, object]]
) -> Tuple[Optional[str], List[str]]:
    with_records = [
        str(entry["path"]) for entry in detected if int(entry["record_count"]) > 0  # type: ignore[arg-type]
    ]
    competing = with_records if len(with_records) > 1 else []
    if config.initialized:
        return config.layout.decisions_rel.rstrip("/"), competing
    if with_records:
        return with_records[0], competing
    return None, competing


def _load_numbered(workspace: str, decisions_rel: str) -> List[DecisionRecord]:
    layout = Layout(workspace, {"decisions": {"path": decisions_rel}})
    return [record for record in load_records(layout) if record.number is not None]


def _is_stub(record: DecisionRecord) -> bool:
    text = read_text(record.path) or ""
    _front, body = parse_frontmatter(text)
    return len(body.strip()) < _STUB_BODY_CHARS


def _corpus_status(
    primary: Optional[str],
    record_count: int,
    with_status: int,
    stubs: int,
    competing: Sequence[str],
) -> Tuple[str, str]:
    if record_count <= 0:
        if primary:
            return ABSENT, "%s exists but has no numbered NNNN-*.md records" % primary
        return ABSENT, "no numbered decision records in a known location"
    location = primary or "?"
    detail = "%s  (%d numbered record(s), %d with title and status" % (
        location,
        record_count,
        with_status,
    )
    if stubs:
        detail += ", %d short enough to look like stubs" % stubs
    detail += ")"
    if competing:
        return PARTIAL, detail + "; competing trees: %s" % ", ".join(competing)
    return PRESENT, detail


def _discovery_status(
    has_agents: bool, nested_only: bool, names_corpus: bool, primary: Optional[str]
) -> Tuple[str, str]:
    if names_corpus:
        target = primary or "the decision corpus"
        return PRESENT, "an agent instruction file names %s" % target
    if nested_only:
        return PARTIAL, "found .agents/AGENTS.md instead of a root AGENTS.md"
    if has_agents:
        return PARTIAL, "AGENTS.md exists; does not name the decision directory"
    return ABSENT, "no root AGENTS.md (and no other agent file names a corpus)"


def _review_status(
    pr_paths: Sequence[str],
    pr_related: bool,
    contributing_rel: Optional[str],
    contributing_related: bool,
) -> Tuple[str, str]:
    if pr_related or contributing_related:
        bits = []
        if pr_related:
            bits.append("PR template mentions decisions (%s)" % pr_paths[0])
        if contributing_related:
            bits.append("%s mentions decisions" % contributing_rel)
        return PRESENT, "; ".join(bits)
    if pr_paths or contributing_rel:
        bits = []
        if pr_paths:
            bits.append("PR template present but silent on ADRs")
        if contributing_rel:
            bits.append("%s present but silent on ADRs" % contributing_rel)
        return PARTIAL, "; ".join(bits)
    return ABSENT, "no pull-request template and no CONTRIBUTING.md"


def _scan(config: ResolvedConfig):
    include = None
    exclude = None
    if config.initialized:
        scope = config.get("scope") or {}
        include = scope.get("include") or None
        exclude = scope.get("exclude") or None
    return scan_anchors(config.layout, include, exclude)


def _agent_baselines(workspace: str, primary: Optional[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    def add(baseline_id: str, rel_paths: List[str], detail: str = "") -> None:
        texts = []
        present_paths = []
        for rel in rel_paths:
            path = os.path.join(workspace, rel)
            if os.path.isfile(path):
                present_paths.append(rel)
                texts.append(read_text(path) or "")
        present = bool(present_paths)
        blob = "\n".join(texts)
        items.append(
            {
                "id": baseline_id,
                "present": present,
                "mentions_corpus": bool(present and _names_corpus(blob, primary)),
                "paths": present_paths,
                "detail": detail,
            }
        )

    add("AGENTS.md", ["AGENTS.md"])
    add("CLAUDE.md", ["CLAUDE.md"])

    cursor_files = _cursor_rule_files(workspace)
    cursor_detail = "%d file(s)" % len(cursor_files) if cursor_files else ""
    add("cursor-rules", cursor_files, cursor_detail)

    add(".github/copilot-instructions.md", [".github/copilot-instructions.md"])
    add("GEMINI.md", ["GEMINI.md"])
    return items


def _cursor_rule_files(workspace: str) -> List[str]:
    files: List[str] = []
    if os.path.isfile(os.path.join(workspace, ".cursorrules")):
        files.append(".cursorrules")
    rules_dir = os.path.join(workspace, ".cursor", "rules")
    if os.path.isdir(rules_dir):
        try:
            names = sorted(os.listdir(rules_dir))
        except OSError:
            names = []
        for name in names:
            if name.endswith(".mdc") or name.endswith(".md"):
                files.append(".cursor/rules/%s" % name)
    return files


def _pr_template_paths(workspace: str) -> List[str]:
    found: List[str] = []
    for rel in (
        "PULL_REQUEST_TEMPLATE.md",
        "pull_request_template.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/pull_request_template.md",
        "docs/PULL_REQUEST_TEMPLATE.md",
        "docs/pull_request_template.md",
    ):
        if os.path.isfile(os.path.join(workspace, rel)):
            found.append(rel)
    for dirname in (".github/PULL_REQUEST_TEMPLATE", ".github/pull_request_template"):
        directory = os.path.join(workspace, dirname)
        if not os.path.isdir(directory):
            continue
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            if name.endswith(".md"):
                found.append("%s/%s" % (dirname, name))
    return found


def _concat_files(workspace: str, rel_paths: Sequence[str]) -> str:
    parts = []
    for rel in rel_paths:
        text = read_text(os.path.join(workspace, rel))
        if text:
            parts.append(text)
    return "\n".join(parts)


def _names_corpus(text: Optional[str], primary: Optional[str]) -> bool:
    if not text:
        return False
    normalized = text.replace("\\", "/")
    if primary and primary.rstrip("/") in normalized:
        return True
    return bool(_DISCOVERY_RE.search(text))


def _is_adr_related(text: Optional[str], primary: Optional[str]) -> bool:
    if not text:
        return False
    return _names_corpus(text, primary) or bool(_REVIEW_EXTRA_RE.search(text))


def _index_rel(config: ResolvedConfig, primary: Optional[str]) -> Optional[str]:
    if config.initialized:
        return "%s/%s" % (config.layout.decisions_rel.rstrip("/"), config.layout.index_name)
    if primary:
        return "%s/index.json" % primary.rstrip("/")
    return None


def _ci_mentions_bearing(workspace: str) -> bool:
    wf = os.path.join(workspace, ".github", "workflows")
    if not os.path.isdir(wf):
        return False
    try:
        names = os.listdir(wf)
    except OSError:
        return False
    for name in names:
        if not (name.endswith(".yml") or name.endswith(".yaml")):
            continue
        text = read_text(os.path.join(wf, name)) or ""
        if "bearing lint" in text or "bearing verify" in text:
            return True
    return False


def _findings(
    record_count: int,
    competing: Sequence[str],
    nested_only: bool,
    has_agents: bool,
    names_corpus: bool,
    agents_mentions: bool,
    silent_baselines: Sequence[str],
    anchor_count: int,
    pr_paths: Sequence[str],
    pr_related: bool,
    contributing_rel: Optional[str],
    contributing_related: bool,
    initialized: bool,
    overlay: str,
    has_index: bool,
    ci_mentions: bool,
) -> List[str]:
    fired: List[str] = []
    if record_count <= 0:
        fired.append("corpus-missing")
    if competing:
        fired.append("corpus-split")
    if nested_only:
        fired.append("agents-md-nested")
    elif not has_agents:
        fired.append("agents-md-missing")
    elif record_count > 0 and not agents_mentions:
        fired.append("agents-md-no-pointer")
    extra_silent = [name for name in silent_baselines if name != "AGENTS.md"]
    if record_count > 0 and extra_silent:
        fired.append("baseline-silent")
    if record_count > 0 and anchor_count <= 0:
        fired.append("anchors-missing")
    if not pr_paths:
        fired.append("review-template-missing")
    elif not pr_related:
        fired.append("review-template-silent")
    if not contributing_rel:
        fired.append("contributing-missing")
    elif not contributing_related:
        fired.append("contributing-silent")
    if not initialized:
        fired.append("bearing-uninitialized")
    elif overlay != OVERLAY_PROJECTED:
        fired.append("bearing-unprojected")
    if record_count > 0 and not has_index:
        fired.append("index-missing")
    if initialized and not ci_mentions:
        fired.append("ci-missing")
    return fired
