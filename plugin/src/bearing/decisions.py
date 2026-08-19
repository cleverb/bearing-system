"""Reading the decision corpus: records, anchors, and the shadow graph.

One parser, used by `index`, `lint`, and `verify`, so those three can never
disagree about what a decision record says.

Two metadata styles are supported, deliberately. YAML frontmatter is canonical
and is what BEARING writes. But MADR-style bullet metadata (`* **Status:**
Accepted`) is extremely common in repositories that adopted ADRs years ago, and
demanding a bulk rewrite of an existing corpus before BEARING does anything
useful is the same adoption friction the retrospective path exists to avoid. So
bullets are read as a fallback, and `bearing lint` reports what is missing for a
complete index entry rather than refusing to work.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .paths import Layout
from .util import parse_frontmatter, read_jsonl, read_text

ACCEPTED = "Accepted"
PROPOSED = "Proposed"
DEPRECATED = "Deprecated"
SUPERSEDED = "Superseded"
LIFECYCLE_STATES = (PROPOSED, ACCEPTED, DEPRECATED, SUPERSEDED)

EOCR_FUNCTIONS = ("Entry", "Operations", "Contract", "Rationale")

# Shadow-graph lifecycle states. Kept here rather than duplicated in the linter so
# `candidate.schema.json` and `bearing lint` cannot drift into disagreeing about
# whether a candidate is valid -- a schema-valid candidate that lint rejects is the
# kind of contradiction that makes people stop trusting both.
CANDIDATE_STATES = (
    "Detected",
    "Corroborated",
    "Reviewable",
    "Promoted",
    "Rejected",
    "Insufficient Evidence",
    "Stale",
)

# States that take a candidate out of the review queue. `Insufficient Evidence` is
# among them because it is the outcome of an assessment, not a pending one:
# re-surfacing it would spend review budget on a question already answered.
_NOT_SURFACED = frozenset({"Rejected", "Promoted", "Stale", "Insufficient Evidence"})

_RECORD_RE = re.compile(r"^(\d{4,})-(.+)\.md$")
_BULLET_RE = re.compile(r"^\s*[*\-]\s*\*\*(?P<key>[A-Za-z][A-Za-z \-]*)\:?\*\*\:?\s*(?P<value>.*)$")
_TITLE_RE = re.compile(r"^#\s+(.*)$", re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

ANCHOR_RE = re.compile(r"ADR-(\d{1,6})")
SEE_TAG_RE = re.compile(r"@see\b[^\n]*")
DEPRECATED_TAG_RE = re.compile(r"@deprecated\b")

# Any line carrying this marker is skipped by the anchor scanner. Necessary
# because documentation, tests, and templates legitimately need to *show* the
# annotation syntax without claiming an anchor -- BEARING's own source is the
# first example. Without an escape hatch the alternative is excluding whole
# directories from scope, which would hide real anchors along with the examples.
IGNORE_MARKER = "bearing:ignore-anchor"

# Files worth scanning for anchors. Text formats where an annotation is plausible.
SOURCE_EXTENSIONS = frozenset(
    {
        ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".py", ".java", ".kt", ".kts", ".go", ".rs", ".rb", ".php",
        ".cs", ".swift", ".m", ".mm", ".c", ".h", ".cc", ".cpp", ".hpp",
        ".scala", ".sql", ".sh", ".vue", ".svelte", ".css", ".scss",
    }
)

_SKIP_DIRS = frozenset({".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv", "venv", ".bearing"})


class DecisionRecord:
    def __init__(self, path: str, workspace: str, decisions_rel: str) -> None:
        self.path = path
        self.filename = os.path.basename(path)
        self.rel = os.path.relpath(path, workspace).replace(os.sep, "/")
        text = read_text(path) or ""
        front, body = parse_frontmatter(text)
        self.frontmatter = front
        self.had_frontmatter = bool(front)
        bullets = _bullet_metadata(body)

        match = _RECORD_RE.match(self.filename)
        self.number = int(match.group(1)) if match else None

        self.id = str(front.get("id") or bullets.get("id") or self._derived_id())
        self.title = self._title(body)
        self.status = _normalize_status(front.get("status") or bullets.get("status"))
        self.eocr_function = _normalize_eocr(front.get("eocr_function") or bullets.get("eocr"))
        self.trigger = _clean(front.get("trigger") or bullets.get("trigger"))
        self.scope = _clean(front.get("scope") or bullets.get("scope"))
        self.superseded_by = _clean(front.get("superseded_by") or bullets.get("superseded by"))
        self.supersedes = _clean(front.get("supersedes") or bullets.get("supersedes"))
        self.date = _clean(front.get("date") or bullets.get("date"))
        self.decisions_rel = decisions_rel

    def _derived_id(self) -> str:
        if self.number is None:
            return os.path.splitext(self.filename)[0]
        return "ADR-%04d" % self.number

    @staticmethod
    def _title(body: str) -> str:
        match = _TITLE_RE.search(body)
        return match.group(1).strip() if match else ""

    @property
    def numeric_key(self) -> int:
        return self.number if self.number is not None else 10**9

    def index_entry(self) -> Dict[str, Any]:
        """One compact entry. Deliberately small: this file is loaded at session
        start, so every field here is paid for on every task."""
        return {
            "id": self.id,
            "trigger": self.trigger or self.title,
            "eocr_function": self.eocr_function or "Rationale",
            "lifecycle_state": self.status or PROPOSED,
            "scope": self.scope or "",
            "source": self.rel,
        }

    def missing_index_fields(self) -> List[str]:
        missing = []
        if not self.trigger:
            missing.append("trigger")
        if not self.eocr_function:
            missing.append("eocr_function")
        if not self.status:
            missing.append("status")
        if not self.scope:
            missing.append("scope")
        return missing


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = _HTML_COMMENT_RE.sub("", str(value)).strip()
    return text


def _normalize_status(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    lowered = text.lower()
    for state in LIFECYCLE_STATES:
        if lowered.startswith(state.lower()):
            return state
    return text


def _normalize_eocr(value: Any) -> str:
    text = _clean(value)
    for function in EOCR_FUNCTIONS:
        if text.lower() == function.lower():
            return function
    return text


def _bullet_metadata(body: str) -> Dict[str, str]:
    """Parse MADR-style `* **Key:** value` lines from the head of a record."""
    out: Dict[str, str] = {}
    for line in body.split("\n")[:40]:
        match = _BULLET_RE.match(line)
        if match:
            key = match.group("key").strip().lower().rstrip(":")
            out[key] = match.group("value").strip()
    return out


def load_records(layout: Layout) -> List[DecisionRecord]:
    directory = layout.decisions
    if not os.path.isdir(directory):
        return []
    records: List[DecisionRecord] = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".md") or filename.upper().startswith("README"):
            continue
        records.append(
            DecisionRecord(
                os.path.join(directory, filename), layout.workspace, layout.decisions_rel
            )
        )
    records.sort(key=lambda record: (record.numeric_key, record.filename))
    return records


def build_index(records: Iterable[DecisionRecord]) -> Dict[str, Any]:
    """The progressive-disclosure index.

    @see ADR-0001 — this repository records decisions as numbered files with
    indexable front matter, which is what makes a compiled index possible at all.

    Not a Projection in the technical sense used elsewhere -- there is no runtime
    format divergence being bridged, just one tool-agnostic index compiled from
    one corpus. It is shaped for Skill-style progressive disclosure: a compact
    index up front, the full record pulled only when a trigger matches.
    """
    return {
        "_generated": True,
        "_note": (
            "Compiled from decision-record front matter by `bearing index`. "
            "Do not hand-edit -- regenerate instead."
        ),
        "entries": [record.index_entry() for record in records],
    }


def estimate_index_tokens(index: Dict[str, Any]) -> int:
    """Rough token count for the disclosure budget.

    Four characters per token is a crude approximation, and that is acceptable
    here: the check exists to catch an index growing by an order of magnitude,
    not to bill anyone for it.
    """
    from .util import dump_json

    return max(1, len(dump_json(index)) // 4)


def path_matches_scope(rel_path: str, scope: str) -> bool:
    """True when a workspace-relative path falls inside a record's scope glob.

    Scope is a comma-separated list of globs (fnmatch, where `*` matches `/`).
    """
    from .util import match_any

    rel_path = rel_path.replace(os.sep, "/").lstrip("./")
    patterns = [part.strip() for part in (scope or "").replace(";", ",").split(",") if part.strip()]
    return bool(patterns) and match_any(rel_path, patterns)


def context_entries(layout: Layout, rel_path: str) -> List[Dict[str, Any]]:
    """Index entries whose scope matches `rel_path`. The generation-time slice."""
    rel_path = rel_path.replace(os.sep, "/").lstrip("./")
    entries: List[Dict[str, Any]] = []
    for record in load_records(layout):
        if record.status not in (ACCEPTED, PROPOSED):
            continue
        if path_matches_scope(rel_path, record.scope or ""):
            entries.append(record.index_entry())
    return entries


def contracts_digest(layout: Layout) -> str:
    """Compact accepted-Contract list compiled into the AGENTS.md block.

    @see ADR-0003 — this is the agent-facing half of contracts projection: the
    same records the index already lists, pushed into the constitution so an
    agent reads them before generating rather than only when CI fails.
    """
    records = [
        record
        for record in load_records(layout)
        if record.status == ACCEPTED and record.eocr_function == "Contract"
    ]
    lines = ["### Accepted Contracts", ""]
    if not records:
        lines += [
            "None recorded yet. Load the index before editing; escalate rather than guessing.",
            "Once Contracts exist, `bearing context <path>` returns the subset that governs a file.",
            "",
        ]
        return "\n".join(lines)
    lines += [
        "These are the accepted Contracts. Load the index first. `bearing context <path>`",
        "returns the subset whose scope matches the file you are editing.",
        "",
    ]
    for record in records:
        lines.append(
            "- **%s** (`%s`) — %s. Trigger: %s."
            % (
                record.id,
                record.scope or "unscoped",
                record.title or record.id,
                record.trigger or record.title or record.id,
            )
        )
    lines.append("")
    return "\n".join(lines)


class Anchor:
    def __init__(self, file: str, line: int, adr_id: str, raw: str) -> None:
        self.file = file
        self.line = line
        self.adr_id = adr_id
        self.raw = raw


def scan_anchors(
    layout: Layout, include: Optional[List[str]] = None, exclude: Optional[List[str]] = None
) -> Tuple[List[Anchor], List[Tuple[str, int]], List[Tuple[str, int, str]]]:
    """Find anchors, unanchored deprecations, and anchors into the shadow graph.

    Returns `(anchors, deprecated_without_see, shadow_pointing_anchors)`.

    The third return value is the one that matters most. The architecture asserts
    that no Anchor may ever point into the shadow graph, and that assertion is
    only real if something checks it -- otherwise a README saying "not
    authoritative" is the entire defense against inference being treated as
    decision.
    """
    from .util import match_any

    anchors: List[Anchor] = []
    orphan_deprecations: List[Tuple[str, int]] = []
    shadow_anchors: List[Tuple[str, int, str]] = []

    shadow_marker = "%s/%s" % (layout.decisions_rel.rstrip("/"), layout.shadow_name)

    for path in iter_source_files(layout.workspace, include, exclude):
        text = read_text(path)
        if text is None:
            continue
        rel_path = os.path.relpath(path, layout.workspace).replace(os.sep, "/")
        lines = text.split("\n")
        for number, line in enumerate(lines, 1):
            if IGNORE_MARKER in line:
                continue
            if SEE_TAG_RE.search(line):
                # One anchor per referenced record per line. A line naming the
                # same record twice (`ADR-0031` and a `0031-*.md` link beside it)
                # is one anchor, not two.
                for adr_id in sorted(
                    {"ADR-%04d" % int(match.group(1)) for match in ANCHOR_RE.finditer(line)}
                ):
                    anchors.append(Anchor(rel_path, number, adr_id, line.strip()))
                if shadow_marker in line:
                    shadow_anchors.append((rel_path, number, line.strip()))
            if DEPRECATED_TAG_RE.search(line):
                window = "\n".join(lines[max(0, number - 6) : number + 6])
                if not SEE_TAG_RE.search(window):
                    orphan_deprecations.append((rel_path, number))

    return anchors, orphan_deprecations, shadow_anchors


def iter_source_files(
    workspace: str, include: Optional[List[str]] = None, exclude: Optional[List[str]] = None
) -> Iterable[str]:
    from .util import match_any

    exclude = exclude or []
    for root, dirnames, filenames in os.walk(workspace):
        dirnames[:] = [name for name in sorted(dirnames) if name not in _SKIP_DIRS]
        for filename in sorted(filenames):
            _, extension = os.path.splitext(filename)
            if extension.lower() not in SOURCE_EXTENSIONS:
                continue
            path = os.path.join(root, filename)
            rel_path = os.path.relpath(path, workspace).replace(os.sep, "/")
            if exclude and match_any(rel_path, exclude):
                continue
            if include and not match_any(rel_path, include):
                continue
            yield path


def load_candidates(layout: Layout) -> List[Dict[str, Any]]:
    return [row for row in read_jsonl(layout.candidates) if isinstance(row, dict)]


def load_rejections(layout: Layout) -> List[Dict[str, Any]]:
    return [row for row in read_jsonl(layout.rejected) if isinstance(row, dict)]


def rejected_fingerprints(layout: Layout) -> Set[str]:
    out: Set[str] = set()
    for row in load_rejections(layout):
        fingerprint = row.get("rejected_evidence_fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            out.add(fingerprint)
    return out


def surfaced_candidates(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Candidates a human would actually be shown.

    MEDIUM or higher, plus the two LOW exceptions: a candidate that contradicts
    an accepted record (a contradiction with authored knowledge is informative
    even when the new evidence is weak), and a candidate on a subject flagged
    load-bearing.
    """
    out = []
    for candidate in candidates:
        if candidate.get("lifecycle_state") in _NOT_SURFACED:
            continue
        confidence = str(candidate.get("confidence", "")).upper()
        if confidence in ("MEDIUM", "HIGH"):
            out.append(candidate)
        elif candidate.get("conflicts_with_accepted") or candidate.get("load_bearing"):
            out.append(candidate)
    return out
