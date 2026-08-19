"""`bearing uninstall`: leave cleanly.

@see ADR-0002 — generated adapters and run state go; decision content stays.

A framework you cannot back out of is a framework people are unwilling to try, so
removal is a first-class operation with a test behind it rather than a paragraph
in a FAQ.

The rule is a straight line: **generated adapters and run state go; decision
content stays.** Every ADR, the index, the shadow graph, the rejection ledger, and
the transcripts survive uninstall untouched. They are the repository's knowledge,
not BEARING's, and the whole argument for adopting BEARING is that this knowledge
outlives the tooling that captured it.

`verify` checks statically that nothing this module would remove lives inside the
decisions directory, so the promise is enforced rather than asserted.
"""

from __future__ import annotations

import os
import shutil
from typing import Dict, List

from .artifacts import read_lock
from .config import ResolvedConfig
from .util import read_text


def removable_paths(config: ResolvedConfig) -> List[str]:
    """Every path uninstall would delete, resolved absolute.

    Sourced from the projection lock rather than from a hardcoded list, so a
    target configured today is removed tomorrow without anyone remembering to
    update this function. That is the second reason the lock file exists: it is
    the only complete record of what BEARING put on disk.
    """
    layout = config.layout
    paths: List[str] = []

    lock = read_lock(layout.lock)
    for entry in (lock or {}).get("artifacts", []):
        recorded = entry.get("path")
        if not recorded:
            continue
        if recorded.startswith("~/"):
            paths.append(os.path.join(os.path.expanduser("~"), recorded[2:]))
        else:
            paths.append(os.path.join(config.workspace, recorded))

    for relative in (
        ".bearing/runs",
        ".bearing/cache",
        ".bearing/projections.lock.json",
    ):
        paths.append(os.path.join(config.workspace, relative))

    return [path for path in paths if os.path.exists(path)]


def preserved_paths(config: ResolvedConfig) -> List[str]:
    layout = config.layout
    candidates = [
        layout.decisions,
        layout.shadow,
        layout.transcripts,
        layout.cost_ledger,
        layout.pass_fail,
        layout.eval_dir,
        layout.config_file,
        layout.pricing,
    ]
    return [path for path in candidates if os.path.exists(path)]


def uninstall(config: ResolvedConfig, keep_config: bool = True) -> Dict[str, List[str]]:
    from .agentsmd import strip_block

    removed: List[str] = []
    for path in removable_paths(config):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        removed.append(_rel(path, config.workspace))

    _prune_empty_dirs(config.workspace)

    blocks: List[str] = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = os.path.join(config.workspace, name)
        if os.path.isfile(path) and strip_block(path):
            blocks.append(name)

    kept = [_rel(path, config.workspace) for path in preserved_paths(config)]

    if not keep_config:
        for path in (config.layout.config_file, config.layout.local_config_file):
            if os.path.isfile(path):
                os.remove(path)
                removed.append(_rel(path, config.workspace))
        kept = [entry for entry in kept if not entry.endswith("config.json")]

    return {
        "removed": sorted(removed),
        "blocks_stripped": blocks,
        "preserved": sorted(kept),
    }


def _rel(path: str, workspace: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home + os.sep) and not path.startswith(workspace + os.sep):
        return "~/" + os.path.relpath(path, home).replace(os.sep, "/")
    return os.path.relpath(path, workspace).replace(os.sep, "/")


def _prune_empty_dirs(workspace: str) -> None:
    """Remove adapter directories left empty, but never the repository's own.

    `.cursor/` may hold a user's own rules; only the subdirectories BEARING
    creates are candidates, and only while empty.
    """
    for relative in (
        ".cursor/agents",
        ".cursor/rules",
        ".claude/agents",
        ".codex/agents",
        ".cursor",
        ".claude",
        ".codex",
    ):
        path = os.path.join(workspace, relative)
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
