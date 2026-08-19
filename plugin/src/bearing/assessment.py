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
import xml.etree.ElementTree as ET
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

_QUALITY_ASSIGNMENT_RE = re.compile(
    r"(?P<key>ruleSetFiles|ruleSetConfig|configFile|config)\s*=\s*"
    r"(?P<factory>(?:rootProject\.)?(?:files?|resources\.text\.fromFile))"
    r"\s*\((?P<args>[^)]*)\)",
    re.MULTILINE,
)
_QUOTED_XML_RE = re.compile(r"[\"']([^\"']+\.xml)[\"']", re.IGNORECASE)
_GRADLE_QUALITY_CHECK_RE = re.compile(
    r"(?:\./gradlew|\bgradle)\s+(?:check\b|pmd\w*\b|checkstyle\w*\b)",
    re.IGNORECASE,
)
_CHECKSTYLE_PLUGIN_RE = re.compile(
    r"(?:id\s*\(?\s*[\"']checkstyle[\"']|"
    r"apply\s+plugin\s*:\s*[\"']checkstyle[\"']|"
    r"\bcheckstyle\s*\{)",
    re.MULTILINE,
)
_QUALITY_RULE_KEYWORDS = (
    "complexity", "npath", "methodlength", "returncount", "nestedif",
    "executablestatement", "classfanout", "illegal", "forbidden",
)

# Fixed table. Order is the order recommendations print. Only fired ids emit.
_RECOMMENDATIONS: Tuple[Tuple[str, str], ...] = (
    (
        "corpus-missing",
        "Add numbered decision records under docs/decisions/ or its category "
        "subdirectories (or run `bearing init` to adopt an existing convention).",
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
    (
        "build-rules-missing",
        "Fix Gradle references to missing PMD or Checkstyle XML files so the "
        "machine-enforced rules can be inspected and run.",
    ),
    (
        "build-rules-unwired",
        "Review PMD or Checkstyle XML that is present but not selected by Gradle. "
        "Its presence is configuration evidence, not proof that the rules are active; "
        "wire it into the build, surface it if otherwise operative, or remove stale configuration.",
    ),
    (
        "build-rules-unsurfaced",
        "Surface configured PMD and Checkstyle rules before generation: name "
        "their XML paths in an agent instruction file and summarize consequential "
        "thresholds such as cyclomatic complexity. A Gradle check command remains "
        "useful as verification, but does not make a rule visible before code is written. "
        "Treat customized thresholds as evidence to review for decision ancestry, not "
        "as decisions inferred from configuration.",
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
    build_rules = _build_quality_contracts(workspace, baselines)
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
        build_contracts_ready=(
            not build_rules["configured_count"] or build_rules["status"] == PRESENT
        ),
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
        build_rules=build_rules,
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
            "build_quality_contracts": build_rules,
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
    lines.extend(
        _section(
            "Build quality evidence",
            dims["build_quality_contracts"]["status"],
            dims["build_quality_contracts"]["detail"],
        )
    )
    for item in dims["build_quality_contracts"]["files"]:
        selected = [
            rule for rule in item["rules"]
            if rule["name"] in item["consequential_rules"]
        ] or item["rules"][:5]
        rule_summaries = []
        for rule in selected:
            properties = ", ".join(
                "%s=%s" % pair for pair in sorted(rule["properties"].items())
            )
            rule_summaries.append(
                "%s%s" % (rule["name"], " [%s]" % properties if properties else "")
            )
        rule_detail = ", ".join(rule_summaries) if rule_summaries else "no rules parsed"
        lines.append(
            "  %-10s  %s  (%s; evidence: %s; surfaced: %s%s)"
            % (
                item["tool"],
                item["path"],
                rule_detail,
                item["evidence"],
                item["surfacing"],
                "; missing" if not item["exists"] else (
                    "; XML parse error" if item["parse_error"] else ""
                ),
            )
        )
    if dims["build_quality_contracts"]["files"]:
        lines.append("")
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


def render_build_quality_advisory(result: Dict[str, Any]) -> str:
    """Render bootstrap findings without changing guidance or decision content."""
    quality = result["dimensions"]["build_quality_contracts"]
    if not quality["evidence_count"]:
        return ""

    lines = ["Build quality rule evidence discovered:"]
    for item in quality["files"]:
        if not item["wired"]:
            state = "file evidence only; not selected by Gradle"
            source = "workspace scan"
        else:
            state = "missing" if not item["exists"] else (
                "surfaced to agents" if item["surfaced"] else "not surfaced to agents"
            )
            source = "selected by %s" % item["build_script"]
        lines.append(
            "  %s  %s  (%s; %s)"
            % (item["tool"], item["path"], state, source)
        )
        selected = [
            rule for rule in item["rules"]
            if rule["name"] in item["consequential_rules"]
        ]
        for rule in selected:
            properties = ", ".join(
                "%s=%s" % pair for pair in sorted(rule["properties"].items())
            )
            lines.append(
                "    %s%s"
                % (rule["name"], " [%s]" % properties if properties else "")
            )

    if quality["configured_count"] and quality["status"] != PRESENT:
        lines.extend(
            [
                "  Surface relevant paths or consequential thresholds in agent instructions",
                "  so they are available before generation, not only when Gradle runs later.",
                "  Gradle selection is a stronger decision-recovery signal than file presence,",
                "  but it is not proof that an architectural decision was made. Review",
                "  customized values separately before",
                "  creating or accepting any decision record.",
            ]
        )
    elif quality["unwired_count"]:
        lines.extend(
            [
                "  File presence is configuration evidence only. Confirm whether these rules",
                "  are operative before surfacing them or reviewing their decision ancestry.",
            ]
        )
    return "\n".join(lines) + "\n"


def _section(title: str, status: str, detail: str) -> List[str]:
    return ["## %s" % title, "  %-8s  %s" % (status, detail), ""]


def _band(
    record_count: int,
    discoverable: bool,
    anchored: bool,
    review_related: bool,
    build_contracts_ready: bool,
) -> str:
    if record_count <= 0:
        return BAND_UNPREPARED
    if discoverable and anchored and review_related and build_contracts_ready:
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
            return ABSENT, (
                "%s exists but has no numbered NNNN-*.md or ADR-NNNN-*.md records "
                "in its directory tree" % primary
            )
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


def _build_quality_contracts(
    workspace: str, baselines: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """Discover PMD/Checkstyle XML, Gradle selection, and agent visibility.

    This is deliberately static. Assessment must work before init and must not
    execute a repository's build. Literal Gradle file references and
    Checkstyle's conventional location are enough to identify the common case;
    dynamic paths are left unclaimed rather than guessed.
    """
    baseline_text = _baseline_text(workspace, baselines)
    files: List[Dict[str, Any]] = []
    seen = set()

    for script in _gradle_build_scripts(workspace):
        text = read_text(script) or ""
        script_dir = os.path.dirname(script)
        found_checkstyle = False
        for match in _QUALITY_ASSIGNMENT_RE.finditer(text):
            key = match.group("key")
            tool = "pmd" if key.startswith("ruleSet") else "checkstyle"
            found_checkstyle = found_checkstyle or tool == "checkstyle"
            for literal in _QUOTED_XML_RE.findall(match.group("args")):
                base = workspace if match.group("factory").startswith("rootProject.") else script_dir
                _add_quality_file(
                    files, seen, workspace, base, literal, tool,
                    os.path.relpath(script, workspace), baseline_text, wired=True
                )

        # Gradle's Checkstyle convention is config/checkstyle/checkstyle.xml.
        # Recognize it only when the plugin is applied and no explicit config in
        # this build script already identified the source.
        if not found_checkstyle and _CHECKSTYLE_PLUGIN_RE.search(text):
            conventional = os.path.join(workspace, "config", "checkstyle", "checkstyle.xml")
            if os.path.isfile(conventional):
                _add_quality_file(
                    files,
                    seen,
                    workspace,
                    workspace,
                    "config/checkstyle/checkstyle.xml",
                    "checkstyle",
                    os.path.relpath(script, workspace),
                    baseline_text,
                    wired=True,
                )

    # An unreferenced ruleset is still useful evidence, but Gradle wiring is the
    # stronger signal that the repository actively selected it for enforcement.
    for absolute, tool in _quality_xml_candidates(workspace):
        _add_quality_file(
            files,
            seen,
            workspace,
            workspace,
            os.path.relpath(absolute, workspace),
            tool,
            "",
            baseline_text,
            wired=False,
        )

    wired = [item for item in files if item["wired"]]
    unwired = [item for item in files if not item["wired"]]
    missing = [item for item in wired if not item["exists"]]
    surfaced = [item for item in wired if item["surfaced"]]
    check_guidance = bool(_GRADLE_QUALITY_CHECK_RE.search(baseline_text))

    if not files:
        status = ABSENT
        detail = "no custom PMD or Checkstyle XML evidence discovered"
    elif not wired:
        status = PARTIAL
        detail = "%d XML ruleset file(s) found as evidence; none selected by Gradle" % len(files)
    elif not missing and len(surfaced) == len(wired):
        status = PRESENT
        detail = "%d Gradle-selected XML file(s); all are named or summarized for agents" % len(wired)
        if unwired:
            detail += "; %d additional unwired file(s) found" % len(unwired)
    elif surfaced or check_guidance:
        status = PARTIAL
        detail = "%d Gradle-selected XML file(s); %d surfaced to agents" % (len(wired), len(surfaced))
        if check_guidance:
            detail += "; a Gradle quality check is documented, but checks run after generation"
        if missing:
            detail += "; %d referenced file(s) missing" % len(missing)
    else:
        status = ABSENT
        detail = "%d Gradle-selected XML file(s) enforce rules, but none are surfaced to agents" % len(wired)
        if missing:
            detail += "; %d referenced file(s) missing" % len(missing)

    return {
        "status": status,
        "detail": detail,
        "files": files,
        "evidence_count": len(files),
        "configured_count": len(wired),
        "unwired_count": len(unwired),
        "surfaced_count": len(surfaced),
        "missing_count": len(missing),
        "agent_check_guidance": check_guidance,
    }


def _gradle_build_scripts(workspace: str) -> List[str]:
    scripts: List[str] = []
    skipped = {".git", ".gradle", ".bearing", "build", "dist", "node_modules", "vendor", ".venv", "venv"}
    for root, dirnames, filenames in os.walk(workspace):
        dirnames[:] = sorted(name for name in dirnames if name not in skipped and not name.startswith("."))
        for filename in ("build.gradle", "build.gradle.kts"):
            if filename in filenames:
                scripts.append(os.path.join(root, filename))
    return sorted(scripts)


def _quality_xml_candidates(workspace: str) -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    skipped = {".git", ".gradle", ".bearing", "build", "dist", "node_modules", "vendor", ".venv", "venv"}
    for root, dirnames, filenames in os.walk(workspace):
        dirnames[:] = sorted(name for name in dirnames if name not in skipped and not name.startswith("."))
        for filename in sorted(filenames):
            lower = filename.lower()
            if not lower.endswith(".xml") or ("pmd" not in lower and "checkstyle" not in lower):
                continue
            tool = "checkstyle" if "checkstyle" in lower else "pmd"
            candidates.append((os.path.join(root, filename), tool))
    return candidates


def _add_quality_file(
    files: List[Dict[str, Any]],
    seen: set,
    workspace: str,
    base: str,
    literal: str,
    tool: str,
    build_script: str,
    baseline_text: str,
    wired: bool,
) -> None:
    if "$" in literal or "{" in literal:
        return
    absolute = os.path.abspath(os.path.join(base, literal))
    try:
        inside = os.path.commonpath((os.path.abspath(workspace), absolute)) == os.path.abspath(workspace)
    except ValueError:
        inside = False
    if not inside:
        return
    rel = os.path.relpath(absolute, workspace).replace(os.sep, "/")
    key = (tool, rel)
    if key in seen:
        return
    seen.add(key)
    exists = os.path.isfile(absolute)
    rules, parse_error = _parse_quality_rules(absolute, tool) if exists else ([], None)
    salient = [rule for rule in rules if _is_consequential_rule(rule["name"])]
    path_named = rel.lower() in baseline_text or os.path.basename(rel).lower() in baseline_text
    summarized = bool(salient) and all(_rule_is_named(rule, baseline_text) for rule in salient)
    files.append(
        {
            "tool": tool,
            "path": rel,
            "build_script": build_script.replace(os.sep, "/"),
            "wired": wired,
            "evidence": "gradle-selected" if wired else "file-only",
            "exists": exists,
            "parse_error": parse_error,
            "rule_count": len(rules),
            "rules": rules,
            "consequential_rules": [rule["name"] for rule in salient],
            "surfaced": bool(path_named or summarized),
            "surfacing": "path" if path_named else ("summary" if summarized else "none"),
        }
    )


def _parse_quality_rules(path: str, tool: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return [], str(exc)

    rules: List[Dict[str, Any]] = []
    if tool == "pmd":
        elements = [element for element in root.iter() if _xml_name(element.tag) == "rule"]
        for element in elements:
            ref = element.attrib.get("ref", "")
            name = element.attrib.get("name") or ref.rsplit("/", 1)[-1]
            if name:
                rules.append({"name": name, "ref": ref, "properties": _xml_properties(element)})
    else:
        ignored = {"Checker", "TreeWalker"}
        elements = [element for element in root.iter() if _xml_name(element.tag) == "module"]
        for element in elements:
            name = element.attrib.get("name", "")
            if name and name not in ignored:
                rules.append({"name": name, "ref": "", "properties": _xml_properties(element)})
    return rules, None


def _xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_properties(element: ET.Element) -> Dict[str, str]:
    properties: Dict[str, str] = {}
    for child in element:
        if _xml_name(child.tag) != "properties":
            continue
        for prop in child:
            if _xml_name(prop.tag) != "property" or not prop.attrib.get("name"):
                continue
            value = prop.attrib.get("value")
            if value is None:
                for value_node in prop:
                    if _xml_name(value_node.tag) == "value":
                        value = "".join(value_node.itertext()).strip()
                        break
            properties[prop.attrib["name"]] = value or ""
    # Checkstyle places property elements directly under modules.
    for child in element:
        if _xml_name(child.tag) == "property" and child.attrib.get("name"):
            properties[child.attrib["name"]] = child.attrib.get("value", "")
    return properties


def _baseline_text(workspace: str, baselines: Sequence[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    for baseline in baselines:
        for rel in baseline.get("paths") or []:
            chunks.append(read_text(os.path.join(workspace, rel)) or "")
    return "\n".join(chunks).replace("\\", "/").lower()


def _is_consequential_rule(name: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", name.lower())
    return any(keyword in compact for keyword in _QUALITY_RULE_KEYWORDS)


def _rule_is_named(rule: Dict[str, Any], baseline_text: str) -> bool:
    name = str(rule["name"])
    phrase = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).lower()
    compact = re.sub(r"[^a-z0-9]", "", name.lower())
    baseline_compact = re.sub(r"[^a-z0-9]", "", baseline_text)
    if phrase not in baseline_text and compact not in baseline_compact:
        return False
    values = [value for value in (rule.get("properties") or {}).values() if value]
    return not values or any(str(value).lower() in baseline_text for value in values)


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
    build_rules: Dict[str, Any],
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
    if build_rules["missing_count"]:
        fired.append("build-rules-missing")
    if build_rules["unwired_count"]:
        fired.append("build-rules-unwired")
    if build_rules["configured_count"] and build_rules["status"] != PRESENT:
        fired.append("build-rules-unsurfaced")
    return fired
