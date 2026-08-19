"""Locating the workspace, the plugin, and the decision corpus.

@see ADR-0002 — the plugin tree is read-only at runtime; this module finds it,
it never writes inside it.

Every path BEARING touches derives from one of three roots:

- the **plugin root** -- read-only after install, holds Skills and templates.
- the **workspace root** -- the repository being operated on.
- the **user root** -- `~/.bearing`, for operator-level config.

Nothing hardcodes `docs/decisions`. The decisions directory is always read from
resolved config, so a repository that has used `docs/adr/` for a decade keeps
using it.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Dict, List, Optional, Tuple

from .util import BearingError, read_json

# Conventions probed by `bearing init`, in the order they are reported.
# `docs/decisions` first because it is the recommended target; the rest exist
# because real repositories have them and forcing a rename is exactly the
# adoption friction the retrospective path is designed to avoid.
KNOWN_DECISION_DIRS: Tuple[str, ...] = (
    "docs/decisions",
    "docs/adr",
    "docs/adrs",
    "docs/ADR",
    "docs/ADRs",
    "doc/adr",
    "doc/decisions",
    "adr",
    "decisions",
    "architecture/decisions",
)

# Directory names that carry the acronym-plural anti-pattern the architecture
# document calls out. Detected so `init` can warn, never so it can refuse:
# renaming a legacy tree is a decision for the repository's owners.
DISCOURAGED_DECISION_DIRS = ("docs/adrs", "docs/ADRs", "adrs")

PLUGIN_SKILL_NAMES = ("decision-recovery", "decision-interview", "decision-onboarding")

_DECISION_RECORD_FILENAME_RE = re.compile(
    r"^(?:ADR-)?(?P<number>\d{4,})-(?P<slug>.+)\.md$", re.IGNORECASE
)


def decision_record_number(filename: str) -> Optional[int]:
    """Return the numeric ADR key for either supported filename convention."""
    match = _DECISION_RECORD_FILENAME_RE.match(filename)
    return int(match.group("number")) if match else None


def iter_decision_record_paths(
    directory: str, shadow_name: str = "shadow", numbered_only: bool = False
) -> List[str]:
    """Recursively list authored markdown, excluding the reserved shadow graph.

    Category directories are organizational only. IDs remain repository-wide.
    Hidden directories are ignored so tool state nested under a corpus is never
    mistaken for authored knowledge.
    """
    if not os.path.isdir(directory):
        return []
    paths: List[str] = []
    corpus_root = os.path.abspath(directory)
    for root, dirnames, filenames in os.walk(directory):
        at_corpus_root = os.path.abspath(root) == corpus_root
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".") and not (at_corpus_root and name == shadow_name)
        )
        for filename in sorted(filenames):
            is_markdown = filename.lower().endswith(".md")
            is_readme = filename.upper().startswith("README")
            if is_markdown and not is_readme and (
                not numbered_only or decision_record_number(filename) is not None
            ):
                paths.append(os.path.join(root, filename))
    return paths


def _plugin_root_from_walk(start: Optional[str] = None) -> Optional[str]:
    """Walk up from `start` (default: this package) looking for plugin.json."""
    here = start or os.path.dirname(os.path.abspath(__file__))
    cursor = here
    while True:
        manifest_path = os.path.join(cursor, "plugin.json")
        if os.path.isfile(manifest_path):
            manifest = read_json(manifest_path, {}) or {}
            if manifest.get("name") == "bearing":
                return cursor
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return None
        cursor = parent


def plugin_root() -> str:
    """The installed plugin root: the directory containing `plugin.json`.

    Resolution order:

    1. Walk up from this package (checkout, marketplace cache, or pipx wheel with
       bundled `plugin.json` and `skills/`).
    2. Operator install pointer at `~/.bearing/install.json` (ADR-0012) when the
       import package is not inside a full plugin tree.
    3. Fall back to this package directory so templates still resolve.
    """
    walked = _plugin_root_from_walk()
    if walked is not None:
        return walked

    from .enable import load_install_pointer

    pointer = load_install_pointer()
    if pointer:
        return str(pointer["plugin_root"])

    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def template_path(name: str) -> str:
    path = os.path.join(data_dir(), "templates", name)
    if not os.path.isfile(path):
        raise BearingError("missing packaged template %r (plugin install may be incomplete)" % name)
    return path


def user_root() -> str:
    override = os.environ.get("BEARING_HOME")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(os.path.expanduser("~"), ".bearing")


def operator_bin_dir() -> str:
    return os.path.join(user_root(), "bin")


def find_workspace_root(start: Optional[str] = None) -> str:
    """The repository root, by git if available and by marker file otherwise."""
    start = os.path.abspath(start or os.getcwd())
    try:
        out = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return os.path.abspath(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass

    cursor = start
    while True:
        for marker in (".bearing", ".git"):
            if os.path.exists(os.path.join(cursor, marker)):
                return cursor
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return start
        cursor = parent


def is_git_repo(workspace: str) -> bool:
    return os.path.isdir(os.path.join(workspace, ".git"))


def git_output(workspace: str, args: List[str]) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", workspace] + args, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


class Layout:
    """Resolved locations for one workspace, derived from config.

    Constructed after config resolution, so `decisions.path` is authoritative
    here and callers never re-derive it.
    """

    def __init__(self, workspace: str, config: Dict) -> None:
        self.workspace = os.path.abspath(workspace)
        decisions = (config.get("decisions") or {})
        self.decisions_rel = decisions.get("path") or "docs/decisions"
        self.shadow_name = decisions.get("shadow_dir") or "shadow"
        self.index_name = decisions.get("index_file") or "index.json"
        self.transcripts_name = decisions.get("transcripts_dir") or "transcripts"
        retention = ((config.get("interview") or {}).get("transcripts") or {}).get("retention")
        self.transcript_retention = retention or "committed"

    # -- decision content ---------------------------------------------------

    @property
    def decisions(self) -> str:
        return os.path.join(self.workspace, self.decisions_rel)

    @property
    def shadow(self) -> str:
        return os.path.join(self.decisions, self.shadow_name)

    @property
    def index(self) -> str:
        return os.path.join(self.decisions, self.index_name)

    @property
    def candidates(self) -> str:
        return os.path.join(self.shadow, "candidates.jsonl")

    @property
    def rejected(self) -> str:
        return os.path.join(self.shadow, "rejected.jsonl")

    @property
    def transcripts(self) -> str:
        """Transcripts sit with the shadow graph because a transcript *is*
        evidence, and it inherits "nothing here is authoritative" for free.

        Under `local` retention they go one level deeper into a gitignored
        subdirectory, for organizations that will not commit a named person's
        testimony to version control.
        """
        base = os.path.join(self.shadow, self.transcripts_name)
        if self.transcript_retention == "local":
            return os.path.join(base, "local")
        return base

    # -- run state ----------------------------------------------------------

    @property
    def bearing(self) -> str:
        return os.path.join(self.workspace, ".bearing")

    @property
    def config_file(self) -> str:
        return os.path.join(self.bearing, "config.json")

    @property
    def local_config_file(self) -> str:
        return os.path.join(self.bearing, "config.local.json")

    @property
    def pricing(self) -> str:
        return os.path.join(self.bearing, "pricing.json")

    @property
    def lock(self) -> str:
        return os.path.join(self.bearing, "projections.lock.json")

    @property
    def ledger_dir(self) -> str:
        return os.path.join(self.bearing, "ledger")

    @property
    def cost_ledger(self) -> str:
        return os.path.join(self.ledger_dir, "cost.jsonl")

    @property
    def pass_fail(self) -> str:
        return os.path.join(self.ledger_dir, "pass-fail-criteria.md")

    @property
    def runs(self) -> str:
        return os.path.join(self.bearing, "runs")

    @property
    def cache(self) -> str:
        return os.path.join(self.bearing, "cache")

    @property
    def eval_dir(self) -> str:
        return os.path.join(self.bearing, "eval")

    @property
    def vendored_skills(self) -> str:
        return os.path.join(self.workspace, ".agents", "skills")


def detect_decision_dirs(workspace: str) -> List[Dict[str, object]]:
    """Find existing decision-record conventions in a repository.

    Returns one entry per candidate directory with the evidence behind it, so
    `init` can present a choice rather than guess. Two signals are collected:
    a known conventional name, and the recursive presence of `NNNN-*.md` or
    `ADR-NNNN-*.md` files.
    """
    found: List[Dict[str, object]] = []
    seen = set()

    def record(relpath: str, reason: str) -> None:
        key = relpath.rstrip("/")
        if key in seen:
            for entry in found:
                if entry["path"] == key and reason not in entry["reasons"]:
                    entry["reasons"].append(reason)  # type: ignore[union-attr]
            return
        seen.add(key)
        abs_path = os.path.join(workspace, key)
        found.append(
            {
                "path": key,
                "reasons": [reason],
                "record_count": _count_numbered(abs_path),
                "discouraged": key in DISCOURAGED_DECISION_DIRS,
            }
        )

    for name in KNOWN_DECISION_DIRS:
        if os.path.isdir(os.path.join(workspace, name)):
            record(name, "known convention")

    for base in ("docs", "doc", ".", "architecture"):
        base_abs = os.path.join(workspace, base)
        if not os.path.isdir(base_abs):
            continue
        try:
            children = sorted(os.listdir(base_abs))
        except OSError:
            continue
        for child in children:
            child_abs = os.path.join(base_abs, child)
            if not os.path.isdir(child_abs) or child.startswith("."):
                continue
            relpath = child if base == "." else "%s/%s" % (base, child)
            # Do not report an ancestor such as `docs/` as a second corpus when
            # a known convention such as `docs/decisions/` already explains the
            # recursively discovered records.
            if any(str(entry["path"]).startswith(relpath.rstrip("/") + "/") for entry in found):
                continue
            if _count_numbered(child_abs) > 0:
                record(relpath, "contains numbered decision records")

    return found


def _count_numbered(directory: str) -> int:
    return len(iter_decision_record_paths(directory, numbered_only=True))


def resolve_skill_source(workspace: str) -> Dict[str, object]:
    """Report which copy of the Skills a runtime would actually load.

    A repository's own `.agents/skills/` takes discovery precedence over the
    installed plugin in both Cursor and Codex. That makes vendoring a silent
    shadowing hazard, so this is surfaced explicitly by `doctor` rather than
    left for someone to discover when an old Skill version misbehaves.
    """
    vendored = os.path.join(workspace, ".agents", "skills")
    vendored_skills = []
    if os.path.isdir(vendored):
        for name in PLUGIN_SKILL_NAMES:
            if os.path.isfile(os.path.join(vendored, name, "SKILL.md")):
                vendored_skills.append(name)

    plugin = plugin_root()
    plugin_skills = []
    for name in PLUGIN_SKILL_NAMES:
        if os.path.isfile(os.path.join(plugin, "skills", name, "SKILL.md")):
            plugin_skills.append(name)

    return {
        "vendored_dir": vendored,
        "vendored_skills": vendored_skills,
        "plugin_dir": plugin,
        "plugin_skills": plugin_skills,
        "effective": "vendored" if vendored_skills else "plugin",
        "shadowed": sorted(set(vendored_skills) & set(plugin_skills)),
    }
