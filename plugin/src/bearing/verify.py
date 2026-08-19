"""`bearing verify`: the mandate, as computed pass/fail.

BEARING's mandate has four pillars. Stated as prose they are aspirations that
sound good in a README and cannot be falsified. This module turns each into a
check against repository state and run logs, so "does this framework do what it
claims" has an answer that does not depend on who is asked.

Some checks are hard invariants (an anchor either resolves or it does not). Others
are thresholds read from config, because the right value genuinely varies by
repository -- but the threshold is declared in advance and committed, which is
the difference between a target and a rationalization.

A fifth group is included that the mandate does not name: usability. A system
that satisfies all four pillars while producing an unreviewable queue and a
30-minute promise it takes a day to meet has failed at something that matters
just as much.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import ResolvedConfig
from .cost import (
    acceptance_stats,
    cost_per_promoted,
    kill_switch_triggered,
    load_ledger,
    load_price_book,
)
from .decisions import (
    ACCEPTED,
    DEPRECATED,
    PROPOSED,
    SUPERSEDED,
    build_index,
    estimate_index_tokens,
    load_candidates,
    load_records,
    rejected_fingerprints,
    scan_anchors,
    surfaced_candidates,
)
from .paths import KNOWN_DECISION_DIRS, plugin_root
from .render import projection_necessity_errors, skill_projection_errors
from .util import read_json, read_jsonl, read_text

PASS = "ok"
FAIL = "fail"
WARN = "warn"
SKIP = "skip"

PILLARS = ("escalate", "anchor", "project", "evolve", "usability")


class Result:
    def __init__(
        self,
        pillar: str,
        name: str,
        status: str,
        detail: str = "",
        hard: bool = True,
    ) -> None:
        self.pillar = pillar
        self.name = name
        self.status = status
        self.detail = detail
        self.hard = hard


# ---------------------------------------------------------------------------
# ESCALATE -- if intent is missing, stop
# ---------------------------------------------------------------------------

def check_escalate(config: ResolvedConfig) -> List[Result]:
    results: List[Result] = []
    layout = config.layout

    fixtures = _load_escalation_fixtures(config)
    if fixtures is None:
        results.append(
            Result(
                "escalate",
                "escalation recall on seeded fixtures",
                SKIP,
                "no .bearing/eval/escalation/cases.jsonl. Recall cannot be asserted without "
                "tickets whose correct answer is known in advance -- seed them with "
                "deliberately missing, ambiguous, and superseded intent.",
                hard=False,
            )
        )
    else:
        recall, false_rate, counts = fixtures
        recall_min = float(config.get("verify.escalation_recall_min") or 0.9)
        false_max = float(config.get("verify.false_escalation_rate_max") or 0.15)
        results.append(
            Result(
                "escalate",
                "escalation recall on must-escalate cases",
                PASS if recall >= recall_min else FAIL,
                "%.2f against a floor of %.2f (%d of %d)"
                % (recall, recall_min, counts["caught"], counts["must_escalate"]),
            )
        )
        results.append(
            Result(
                "escalate",
                "false-escalation rate",
                PASS if false_rate <= false_max else FAIL,
                "%.2f against a ceiling of %.2f. Over-escalation is also failure: an agent "
                "that stops on everything is not cautious, it is unusable."
                % (false_rate, false_max),
            )
        )

    # Silent substitution: following a superseded record instead of its successor.
    records = load_records(layout)
    by_id = {record.id: record for record in records}
    dead_ends = [
        record.id
        for record in records
        if record.status == SUPERSEDED and not record.superseded_by
    ]
    results.append(
        Result(
            "escalate",
            "no superseded record is a dead end",
            PASS if not dead_ends else FAIL,
            "clean" if not dead_ends else "%s have no successor" % ", ".join(dead_ends),
        )
    )

    scope = config.get("scope") or {}
    anchors, orphan_deprecations, _ = scan_anchors(
        layout, scope.get("include") or None, scope.get("exclude") or None
    )
    unresolved = [anchor for anchor in anchors if anchor.adr_id not in by_id]
    results.append(
        Result(
            "escalate",
            "every anchor an agent may follow resolves",
            PASS if not unresolved else FAIL,
            "clean"
            if not unresolved
            else "%d unresolved (e.g. %s at %s:%d)"
            % (len(unresolved), unresolved[0].adr_id, unresolved[0].file, unresolved[0].line),
        )
    )

    results.append(
        Result(
            "escalate",
            "no deprecation marker without a decision to consult",  # bearing:ignore-anchor
            PASS if not orphan_deprecations else WARN,
            "clean"
            if not orphan_deprecations
            else "%d site(s); an agent is forbidden from refactoring these and has no record "
            "to consult, which is a guaranteed escalation with no resolution path"
            % len(orphan_deprecations),
            hard=False,
        )
    )

    results.append(_no_inference_blocks_merge(config))
    return results


def _no_inference_blocks_merge(config: ResolvedConfig) -> Result:
    """The hard invariant: zero merges blocked by a recovery signal.

    Checked two ways -- config, and CI workflow text. Config alone is not enough,
    because the realistic failure is not someone setting `block_on` to something
    forbidden; it is a workflow that runs recovery and gates on its exit code
    without anyone noticing that a confidence score has quietly acquired veto
    power over a merge.
    """
    block_on = config.get("enforcement.block_on") or []
    if "recovery_signal" in block_on:
        return Result(
            "escalate",
            "no inference may block a merge",
            FAIL,
            "enforcement.block_on includes 'recovery_signal'",
        )

    offenders: List[str] = []
    workflows = os.path.join(config.workspace, ".github", "workflows")
    if os.path.isdir(workflows):
        for filename in sorted(os.listdir(workflows)):
            if not filename.endswith((".yml", ".yaml")):
                continue
            text = read_text(os.path.join(workflows, filename)) or ""
            for line in text.split("\n"):
                stripped = line.strip()
                if not stripped.startswith("-") and "run:" not in stripped:
                    continue
                if re.search(r"bearing\s+(recover|extract|score|resolve)", stripped):
                    if "continue-on-error" not in text and "|| true" not in stripped:
                        offenders.append("%s: %s" % (filename, stripped[:70]))

    if offenders:
        return Result(
            "escalate",
            "no inference may block a merge",
            FAIL,
            "CI appears to gate on a recovery command: %s. A recovery signal may flag and "
            "route to review at any confidence; only structural enforcement or an accepted "
            "Contract may block." % "; ".join(offenders[:3]),
        )

    return Result(
        "escalate",
        "no inference may block a merge",
        PASS,
        "block_on = %s; no CI job gates on a recovery command" % ", ".join(block_on) or "none",
    )


def _load_escalation_fixtures(
    config: ResolvedConfig,
) -> Optional[Tuple[float, float, Dict[str, int]]]:
    path = os.path.join(config.layout.eval_dir, "escalation", "cases.jsonl")
    rows = [row for row in read_jsonl(path) if isinstance(row, dict)]
    if not rows:
        return None

    must = [row for row in rows if row.get("expects") == "escalate"]
    must_not = [row for row in rows if row.get("expects") == "proceed"]
    caught = len([row for row in must if row.get("observed") == "escalate"])
    false_positives = len([row for row in must_not if row.get("observed") == "escalate"])

    recall = (caught / len(must)) if must else 1.0
    false_rate = (false_positives / len(must_not)) if must_not else 0.0
    return recall, false_rate, {
        "caught": caught,
        "must_escalate": len(must),
        "false_positives": false_positives,
        "must_proceed": len(must_not),
    }


# ---------------------------------------------------------------------------
# ANCHOR -- wire implementation to intent
# ---------------------------------------------------------------------------

def check_anchor(config: ResolvedConfig) -> List[Result]:
    results: List[Result] = []
    layout = config.layout
    records = load_records(layout)
    by_id = {record.id: record for record in records}

    scope = config.get("scope") or {}
    include = scope.get("include") or None
    anchors, _, shadow_anchors = scan_anchors(layout, include, scope.get("exclude") or None)

    results.append(
        Result(
            "anchor",
            "no anchor points into the shadow graph",
            PASS if not shadow_anchors else FAIL,
            "clean"
            if not shadow_anchors
            else "%d site(s), e.g. %s:%d" % (len(shadow_anchors), shadow_anchors[0][0], shadow_anchors[0][1]),
        )
    )

    unresolved = [anchor for anchor in anchors if anchor.adr_id not in by_id]
    results.append(
        Result(
            "anchor",
            "100% of anchors resolve",
            PASS if not unresolved else FAIL,
            "%d anchor(s), all resolving" % len(anchors)
            if not unresolved
            else "%d of %d unresolved" % (len(unresolved), len(anchors)),
        )
    )

    # Bidirectionality: a record reachable from nothing is the original problem.
    accepted = [record for record in records if record.status == ACCEPTED]
    anchored = {anchor.adr_id for anchor in anchors}
    unanchored = [record.id for record in accepted if record.id not in anchored]
    results.append(
        Result(
            "anchor",
            "every accepted record has at least one anchor",
            PASS if not unanchored else WARN,
            "%d accepted record(s), all anchored" % len(accepted)
            if not unanchored
            else "%s reachable from no code. A record nothing points at is the original "
            "failure mode this system exists to fix." % ", ".join(unanchored[:5]),
            hard=False,
        )
    )

    # Coverage, within declared scope only. Repository-wide coverage on a legacy
    # codebase is a vanity metric: it measures the size of the backlog, not the
    # quality of the work done.
    if not include:
        results.append(
            Result(
                "anchor",
                "anchor coverage within declared scope",
                SKIP,
                "scope.include is empty, so there is no declared scope to measure against. "
                "Repository-wide coverage is deliberately not reported: on a legacy codebase "
                "it measures the backlog, not the framework.",
                hard=False,
            )
        )
    else:
        coverage, counts = _scope_coverage(config, anchors, include, scope.get("exclude") or None)
        floor = float(config.get("verify.anchor_coverage_min") or 0.6)
        results.append(
            Result(
                "anchor",
                "anchor coverage within declared scope",
                PASS if coverage >= floor else FAIL,
                "%.2f against a floor of %.2f (%d of %d in-scope files carry an anchor)"
                % (coverage, floor, counts["anchored"], counts["total"]),
            )
        )

    # Freshness as a trend rather than a threshold.
    stale = [
        record.id
        for record in records
        if record.status in (DEPRECATED, SUPERSEDED) and record.id in anchored
    ]
    results.append(
        Result(
            "anchor",
            "anchor freshness",
            PASS if not stale else WARN,
            "all anchored records are Accepted"
            if not stale
            else "%d anchored record(s) are Deprecated or Superseded: %s"
            % (len(stale), ", ".join(stale[:5])),
            hard=False,
        )
    )

    return results


def _scope_coverage(
    config: ResolvedConfig, anchors, include: Sequence[str], exclude: Optional[Sequence[str]]
) -> Tuple[float, Dict[str, int]]:
    from .decisions import iter_source_files

    anchored_files = {anchor.file for anchor in anchors}
    total = 0
    hit = 0
    for path in iter_source_files(config.workspace, list(include), list(exclude or [])):
        rel = os.path.relpath(path, config.workspace).replace(os.sep, "/")
        total += 1
        if rel in anchored_files:
            hit += 1
    coverage = (hit / total) if total else 1.0
    return coverage, {"anchored": hit, "total": total}


# ---------------------------------------------------------------------------
# PROJECT -- standardize the source, generate the adapters
# ---------------------------------------------------------------------------

def check_project(config: ResolvedConfig) -> List[Result]:
    from .agentsmd import check_block, rule_body, targets as agents_targets
    from .artifacts import apply as apply_artifacts, build_lock, read_lock
    from .render import load_subagents, render_rules, render_subagents

    results: List[Result] = []
    layout = config.layout

    subagents = load_subagents()
    body = rule_body(config)
    artifacts, skips = render_subagents(config, subagents)
    rule_artifacts, rule_skips = render_rules(config, body)
    artifacts += rule_artifacts
    skips += rule_skips

    # Determinism is a hard pass/fail, and it is cheap to test: render twice and
    # compare. A renderer that embeds a timestamp passes every other check in
    # this suite and makes `--check` useless in CI.
    first = [artifact.sha256 for artifact in artifacts]
    again, _ = render_subagents(config, load_subagents())
    again_rules, _ = render_rules(config, rule_body(config))
    second = [artifact.sha256 for artifact in again + again_rules]
    results.append(
        Result(
            "project",
            "two renders are byte-identical",
            PASS if first == second else FAIL,
            "%d artifact(s) reproducible" % len(first)
            if first == second
            else "renderer output is not deterministic, which makes `render --check` unusable",
        )
    )

    previous = read_lock(layout.lock)
    outcome = apply_artifacts(artifacts, config.workspace, check=True, previous_lock=previous)
    problems = (
        ["%s (%s)" % (path, why) for path, why in outcome.drifted]
        + ["%s missing" % path for path in outcome.missing]
        + ["%s orphaned" % path for path in outcome.orphaned]
    )
    results.append(
        Result(
            "project",
            "no drift between canonical sources and generated adapters",
            PASS if not problems else FAIL,
            "%d artifact(s) current" % len(artifacts)
            if not problems
            else "; ".join(problems[:4]),
        )
    )

    for path, block_body, _ in agents_targets(config):
        drift = check_block(path, block_body)
        results.append(
            Result(
                "project",
                "managed block current in %s" % os.path.basename(path),
                PASS if drift is None else FAIL,
                drift or "in sync",
            )
        )

    # Every artifact carries a header and appears in the lock.
    lock = read_lock(layout.lock)
    if lock is None:
        results.append(
            Result(
                "project",
                "projection lock present",
                FAIL,
                "no .bearing/projections.lock.json; run `bearing render`",
            )
        )
    else:
        recorded = {entry.get("path") for entry in lock.get("artifacts", [])}
        unrecorded = [
            artifact.lock_path(config.workspace)
            for artifact in artifacts
            if artifact.lock_path(config.workspace) not in recorded
        ]
        results.append(
            Result(
                "project",
                "every generated file is recorded in the lock",
                PASS if not unrecorded else FAIL,
                "%d recorded" % len(recorded) if not unrecorded else "missing: %s" % ", ".join(unrecorded[:4]),
            )
        )
        results.append(
            Result(
                "project",
                "deliberate skips are recorded, not merely absent",
                PASS if lock.get("skipped") is not None else FAIL,
                "%d skip(s) recorded with reasons" % len(lock.get("skipped") or []),
                hard=False,
            )
        )

    missing_header = [
        artifact.lock_path(config.workspace)
        for artifact in artifacts
        if "DO NOT EDIT" not in artifact.content
        and os.path.splitext(artifact.path)[1].lower() in (".md", ".mdc", ".toml", ".yaml", ".yml")
    ]
    results.append(
        Result(
            "project",
            "every generated file carries a DO-NOT-EDIT header",
            PASS if not missing_header else FAIL,
            "clean" if not missing_header else ", ".join(missing_header[:4]),
        )
    )

    necessity = projection_necessity_errors(config) + skill_projection_errors()
    results.append(
        Result(
            "project",
            "no projection exists without a format gap",
            PASS if not necessity else FAIL,
            "every projection bridges genuinely incompatible formats"
            if not necessity
            else necessity[0],
        )
    )

    return results


# ---------------------------------------------------------------------------
# EVOLVE -- a stateful graph, not a static library
# ---------------------------------------------------------------------------

def check_evolve(config: ResolvedConfig) -> List[Result]:
    results: List[Result] = []
    layout = config.layout
    candidates = load_candidates(layout)

    # Idempotency: cheap to test, and the single most likely regression. A
    # recovery pass that re-emits the same candidates against an unchanged corpus
    # turns the review queue into a treadmill.
    fingerprints = [
        candidate.get("evidence_fingerprint")
        for candidate in candidates
        if candidate.get("evidence_fingerprint")
    ]
    duplicates = len(fingerprints) - len(set(fingerprints))
    results.append(
        Result(
            "evolve",
            "recovery is idempotent",
            PASS if duplicates == 0 else FAIL,
            "%d candidate(s), no duplicate evidence fingerprints" % len(candidates)
            if duplicates == 0
            else "%d duplicate fingerprint(s): an unchanged corpus is re-emitting candidates"
            % duplicates,
        )
    )

    # Rejection durability.
    rejected = rejected_fingerprints(layout)
    resurfaced = [
        candidate.get("candidate_id")
        for candidate in surfaced_candidates(candidates)
        if candidate.get("evidence_fingerprint") in rejected
    ]
    results.append(
        Result(
            "evolve",
            "a rejected fingerprint never resurfaces",
            PASS if not resurfaced else FAIL,
            "%d rejection(s) held" % len(rejected)
            if not resurfaced
            else "%s reappeared after rejection" % ", ".join(str(c) for c in resurfaced[:5]),
        )
    )

    # Lifecycle honesty.
    records = load_records(layout)
    dead_ends = [r.id for r in records if r.status == SUPERSEDED and not r.superseded_by]
    results.append(
        Result(
            "evolve",
            "no Superseded record without a successor",
            PASS if not dead_ends else FAIL,
            "clean" if not dead_ends else ", ".join(dead_ends),
        )
    )

    stale_days = int(config.get("verify.proposed_stale_days") or 90)
    stale = _stale_proposed(config, records, stale_days)
    results.append(
        Result(
            "evolve",
            "no Proposed record has gone stale",
            PASS if not stale else WARN,
            "clean"
            if not stale
            else "%s untouched for over %d days; a permanently Proposed record is a decision "
            "nobody made" % (", ".join(stale[:5]), stale_days),
            hard=False,
        )
    )

    # Cost trend and the kill switch.
    book = load_price_book(config)
    rows = load_ledger(config)
    triggered, reason = kill_switch_triggered(config, book, rows)
    results.append(
        Result(
            "evolve",
            "cost per promoted candidate is not rising",
            FAIL if triggered else PASS,
            reason,
            hard=False,
        )
    )

    stats = acceptance_stats(rows)
    if stats["acceptance_rate"] is not None:
        results.append(
            Result(
                "evolve",
                "acceptance rate recorded",
                PASS,
                "%.0f%% (%d of %d) -- reported for context, never as a pass/fail on its own"
                % (
                    stats["acceptance_rate"] * 100,
                    stats["candidates_promoted"],
                    stats["candidates_reviewed"],
                ),
                hard=False,
            )
        )

    return results


def _stale_proposed(config: ResolvedConfig, records, days: int) -> List[str]:
    stale: List[str] = []
    for record in records:
        if record.status != PROPOSED:
            continue
        out = subprocess.run(
            ["git", "-C", config.workspace, "log", "-1", "--format=%ct", "--", record.rel],
            capture_output=True,
            text=True,
        )
        if out.returncode != 0 or not out.stdout.strip():
            continue
        try:
            timestamp = int(out.stdout.strip())
        except ValueError:
            continue
        import time

        if (time.time() - timestamp) > days * 86400:
            stale.append(record.id)
    return stale


# ---------------------------------------------------------------------------
# Cross-cutting usability -- what "fit and finish" actually means
# ---------------------------------------------------------------------------

def check_usability(config: ResolvedConfig) -> List[Result]:
    results: List[Result] = []
    layout = config.layout

    # Disclosure budget.
    index = build_index(load_records(layout))
    tokens = estimate_index_tokens(index)
    budget = int(config.get("verify.index_token_budget") or 4000)
    results.append(
        Result(
            "usability",
            "disclosure index within token budget",
            PASS if tokens <= budget else FAIL,
            "roughly %d tokens against a ceiling of %d. This file is loaded on every task, so "
            "unbounded growth silently reverses the framework's value." % (tokens, budget),
        )
    )

    # Review-queue tractability.
    candidates = load_candidates(layout)
    surfaced = len(surfaced_candidates(candidates))
    seconds = int(config.get("review.seconds_per_candidate_estimate") or 85)
    budget_minutes = int(config.get("review.budget_minutes_per_session") or 90)
    affordable = max(1, (budget_minutes * 60) // max(seconds, 1))
    results.append(
        Result(
            "usability",
            "review queue is clearable in the declared budget",
            PASS if surfaced <= affordable else FAIL,
            "%d surfaced, %d clearable in %d min at %ds each. A queue larger than one person "
            "clears does not get reviewed carefully, it gets rubber-stamped."
            % (surfaced, affordable, budget_minutes, seconds),
        )
    )

    # Negative Set hallucination rate -- the trust-critical metric.
    hallucination = _negative_set_rate(config)
    ceiling = float(config.get("verify.negative_set_hallucination_rate_max") or 0.02)
    if hallucination is None:
        results.append(
            Result(
                "usability",
                "Negative Set hallucination rate",
                SKIP,
                "no results in .bearing/eval/negative/cases.jsonl. This is the metric that "
                "gates every extractor or model change: the risk is not only missing real "
                "decisions, it is inventing convincing fictional ones.",
                hard=False,
            )
        )
    else:
        results.append(
            Result(
                "usability",
                "Negative Set hallucination rate",
                PASS if hallucination <= ceiling else FAIL,
                "%.3f against a ceiling of %.3f" % (hallucination, ceiling),
            )
        )

    # Time to first value.
    ttfv = _time_to_first_value(config)
    promised = int(config.get("verify.time_to_first_value_minutes") or 30)
    if ttfv is None:
        results.append(
            Result(
                "usability",
                "time to first value",
                SKIP,
                "no measured run yet. QUICKSTART.md promises %d minutes; that number is held "
                "as a measured criterion, so either measure it or change the promise."
                % promised,
                hard=False,
            )
        )
    else:
        results.append(
            Result(
                "usability",
                "time to first value",
                PASS if ttfv <= promised else FAIL,
                "%d min measured against a documented promise of %d min" % (ttfv, promised),
            )
        )

    results.append(_uninstall_cleanliness(config))
    results.extend(check_docs(config))
    return results


def _negative_set_rate(config: ResolvedConfig) -> Optional[float]:
    path = os.path.join(config.layout.eval_dir, "negative", "cases.jsonl")
    rows = [row for row in read_jsonl(path) if isinstance(row, dict)]
    scored = [row for row in rows if row.get("observed") is not None]
    if not scored:
        return None
    fabricated = len([row for row in scored if row.get("observed") == "decision"])
    return fabricated / len(scored)


def _time_to_first_value(config: ResolvedConfig) -> Optional[int]:
    rows = load_ledger(config)
    for row in rows:
        if row.get("stage") == "onboarding" and row.get("minutes_to_first_anchor") is not None:
            return int(row["minutes_to_first_anchor"])
    return None


def _uninstall_cleanliness(config: ResolvedConfig) -> Result:
    """Can BEARING be removed without taking decision content with it?

    This is the answer to the lock-in objection, and it has to be a test rather
    than a promise. The check is static: every path `uninstall` would remove is
    a generated adapter or run state, and no path it would remove is authored
    decision content.
    """
    from .uninstall import removable_paths

    removable = removable_paths(config)
    layout = config.layout
    protected = os.path.abspath(layout.decisions)
    violations = [
        path
        for path in removable
        if os.path.abspath(path).startswith(protected + os.sep) or os.path.abspath(path) == protected
    ]
    return Result(
        "usability",
        "uninstall leaves decision content intact",
        PASS if not violations else FAIL,
        "%d generated path(s) would be removed, none inside %s"
        % (len(removable), layout.decisions_rel)
        if not violations
        else "would remove decision content: %s" % ", ".join(violations[:3]),
    )


# ---------------------------------------------------------------------------
# Docs conformance
# ---------------------------------------------------------------------------

_PATH_TOKEN_RE = re.compile(r"`([A-Za-z0-9_./{}<>\-]+)`")

_DOC_FILES = ("BEARING.md", "QUICKSTART.md", "README.md", "AGENTS.md")

# Opt out one line of prose from path checking. For paths a document has to name
# without claiming this repository has them -- an optional projection target that
# is currently switched off, for instance.
_IGNORE_PATHS_MARKER = "bearing:ignore-paths"


def check_docs(config: ResolvedConfig) -> List[Result]:
    """Every path a document names must exist.

    This framework's credibility rests entirely on its own documents being
    trustworthy. A spec that references a filename the repository does not ship
    teaches a reader that the specs are approximately true, and after that no
    amount of correctness elsewhere recovers their attention.

    Tokens containing placeholders are skipped, as are bare command words and
    globs -- the check targets concrete paths, and a check with false positives
    gets switched off.
    """
    workspace = config.workspace
    missing: List[str] = []
    checked = 0

    doc_paths = [os.path.join(workspace, name) for name in _DOC_FILES]
    specs_dir = os.path.join(workspace, "docs", "specs")
    if os.path.isdir(specs_dir):
        doc_paths += [
            os.path.join(specs_dir, name)
            for name in sorted(os.listdir(specs_dir))
            if name.endswith(".md")
        ]

    # Alternative decision-directory conventions are named in these documents to
    # describe *other* repositories. They are correctly absent here, and treating
    # their absence as a documentation defect would make the check unusable in the
    # one document that has to discuss them.
    configured = config.layout.decisions_rel.rstrip("/")
    other_conventions = {
        name.rstrip("/") for name in KNOWN_DECISION_DIRS if name.rstrip("/") != configured
    }

    for doc_path in doc_paths:
        text = read_text(doc_path)
        if text is None:
            continue
        doc_rel = os.path.relpath(doc_path, workspace).replace(os.sep, "/")
        for line in text.split("\n"):
            if _IGNORE_PATHS_MARKER in line:
                continue
            for token in set(_PATH_TOKEN_RE.findall(line)):
                if not _is_checkable_path(token, workspace):
                    continue
                # A leading slash in prose means "from the repository root", not
                # the filesystem root.
                relative = token.lstrip("/").rstrip("/")
                if relative in other_conventions:
                    continue
                checked += 1
                if not os.path.exists(os.path.join(workspace, relative)):
                    missing.append("%s references %s" % (doc_rel, token))

    return [
        Result(
            "usability",
            "documented paths exist",
            PASS if not missing else FAIL,
            "%d path reference(s) verified" % checked
            if not missing
            else "%d broken: %s" % (len(missing), "; ".join(sorted(missing)[:6])),
        )
    ]


_ROOT_FILES = ("BEARING.md", "QUICKSTART.md", "AGENTS.md", "README.md", "LICENSE")

# Top-level directories BEARING documents and therefore owns the accuracy of.
# Listed explicitly rather than derived from what exists on disk, so a reference
# to a directory that has been *moved* is still reported as broken -- which is
# the single most valuable thing this check catches.
_DOCUMENTED_ROOTS = (
    ".agents",
    ".bearing",
    ".claude",
    ".claude-plugin",
    ".codex",
    ".codex-plugin",
    ".cursor",
    ".cursor-plugin",
    ".github",
    "dist",
    "doc",
    "docs",
    "plugin",
    "tests",
)


def _is_checkable_path(token: str, workspace: str) -> bool:
    """Is this token a concrete repository path whose existence is assertable?

    Conservative on purpose. A check that produces false positives gets switched
    off, and then the real broken references stop being caught -- so anything
    ambiguous is skipped rather than guessed at.
    """
    if any(char in token for char in "{}<>*"):
        return False
    if token.startswith(("http", "@", "$", "-")) or " " in token:
        return False
    if token.endswith((".com", ".org", ".dev", ".io")):
        return False

    bare = token.lstrip("/").rstrip("/")
    if not bare:
        return False

    # A `../` path is relative to something the prose is describing, never to the
    # workspace root, and `os.path.isdir("..")` would otherwise make every such
    # token look workspace-rooted. Escaping relative paths are policed by the
    # packaging suite, which is the check that can actually judge them.
    if bare.split("/")[0] == "..":
        return False

    if "/" not in bare:
        # A bare dotted name like `plugin.json` or `index.json` could live
        # anywhere, so only the known root documents are assertable.
        return bare in _ROOT_FILES

    first = bare.split("/")[0]
    if first in _DOCUMENTED_ROOTS:
        return True
    # Otherwise require the first segment to exist at top level. This is what
    # lets prose mention a path relative to some other directory -- `shadow/`,
    # `scripts/` -- without the checker treating it as workspace-rooted.
    return os.path.isdir(os.path.join(workspace, first))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

_CHECKS = {
    "escalate": check_escalate,
    "anchor": check_anchor,
    "project": check_project,
    "evolve": check_evolve,
    "usability": check_usability,
}


def run(config: ResolvedConfig, pillars: Optional[Sequence[str]] = None) -> List[Result]:
    selected = list(pillars) if pillars else list(PILLARS)
    results: List[Result] = []
    for pillar in selected:
        check = _CHECKS.get(pillar)
        if check is None:
            continue
        results.extend(check(config))
    return results


def pillar_verdicts(results: Sequence[Result]) -> Dict[str, str]:
    verdicts: Dict[str, str] = {}
    for pillar in PILLARS:
        subset = [result for result in results if result.pillar == pillar]
        if not subset:
            continue
        if any(result.status == FAIL and result.hard for result in subset):
            verdicts[pillar] = FAIL
        elif any(result.status == FAIL for result in subset):
            verdicts[pillar] = WARN
        elif any(result.status == WARN for result in subset):
            verdicts[pillar] = WARN
        else:
            verdicts[pillar] = PASS
    return verdicts
