"""The single definition of BEARING's effective workspace file universe.

@see ADR-0010 — Discover resolves decisions against the same file universe in
every consumer; lint, context, assessment, and verify must not each invent one.
"""

from __future__ import annotations

import os
import subprocess
from typing import Iterable, List, Optional, Sequence

from .util import match_any

_FALLBACK_SKIP_DIRS = frozenset(
    {".git", ".bearing", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv", "venv"}
)


def effective_workspace_files(
    workspace: object,
    include: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
) -> List[str]:
    """Return normalized paths in BEARING's effective workspace.

    In a Git repository, Git owns the base universe: tracked and untracked,
    non-ignored files. A non-Git directory uses a deterministic filesystem walk.
    Both paths then apply BEARING's include/exclude rules identically.
    Only currently existing, workspace-contained files are returned.
    """
    if not isinstance(workspace, str):
        config = workspace
        workspace = str(config.workspace)
        if include is None and exclude is None:
            scope = config.get("scope") or {}
            include = scope.get("include") or None
            exclude = scope.get("exclude") or None
    workspace = os.path.abspath(workspace)
    candidates = _git_files(workspace)
    if candidates is None:
        candidates = _fallback_files(workspace)

    includes = list(include or [])
    excludes = list(exclude or [])
    found: List[str] = []
    for raw in candidates:
        rel = _normalize(raw)
        if not rel or rel == ".." or rel.startswith("../"):
            continue
        absolute = os.path.abspath(os.path.join(workspace, rel.replace("/", os.sep)))
        if not _contained(absolute, workspace) or not os.path.isfile(absolute):
            continue
        if excludes and match_any(rel, excludes):
            continue
        if includes and not match_any(rel, includes):
            continue
        found.append(rel)
    return sorted(set(found))


def effective_source_files(
    workspace: str,
    extensions: Iterable[str],
    include: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
) -> List[str]:
    allowed = {extension.lower() for extension in extensions}
    return [
        path
        for path in effective_workspace_files(workspace, include, exclude)
        if os.path.splitext(path)[1].lower() in allowed
    ]


def _git_files(workspace: str) -> Optional[List[str]]:
    if not os.path.isdir(os.path.join(workspace, ".git")):
        return None
    try:
        result = subprocess.run(
            ["git", "-C", workspace, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [part.decode("utf-8", "surrogateescape") for part in result.stdout.split(b"\0") if part]


def _fallback_files(workspace: str) -> List[str]:
    found: List[str] = []
    for root, dirnames, filenames in os.walk(workspace):
        dirnames[:] = sorted(name for name in dirnames if name not in _FALLBACK_SKIP_DIRS)
        for filename in sorted(filenames):
            found.append(os.path.relpath(os.path.join(root, filename), workspace))
    return found


def _normalize(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _contained(path: str, workspace: str) -> bool:
    try:
        return os.path.commonpath((os.path.realpath(path), os.path.realpath(workspace))) == os.path.realpath(workspace)
    except ValueError:
        return False
