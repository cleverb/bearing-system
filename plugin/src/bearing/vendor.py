"""`bearing vendor`: copy the Skills into the repository, deliberately.

@see ADR-0002 — vendored copies live in the workspace, never inside the plugin.

The default is the installed plugin, and vendoring is not a "safer" alternative
that people should reach for by habit. It is right in four specific situations:

- **Air-gapped environments** where a marketplace is unreachable.
- **Audit contexts** that need a pinned version so a candidate's provenance is
  reconstructible years later -- "which extractor produced this?" has no answer
  if the Skill silently upgraded in between.
- **CI runners** that must not depend on user-level plugin state.
- **Forked Skills**, where an organization has added local instructions.

And there is a trap worth being loud about: a repository's `.agents/skills/`
takes discovery precedence over the installed plugin in both Cursor and Codex, so
vendoring **silently shadows** the plugin. Someone upgrades BEARING, nothing
changes, and the reason is a copy they forgot about. So `vendor` pins the version
into config and `doctor` prints which copy won on every run.
"""

from __future__ import annotations

import os
import shutil
from typing import Dict, List, Tuple

from . import __version__
from .config import ResolvedConfig
from .paths import PLUGIN_SKILL_NAMES, plugin_root
from .util import BearingError, ensure_dir, read_json, write_json


def vendor(config: ResolvedConfig, force: bool = False) -> Dict[str, object]:
    source_root = os.path.join(plugin_root(), "skills")
    if not os.path.isdir(source_root):
        raise BearingError("no skills found in the installed plugin at %s" % source_root)

    destination_root = config.layout.vendored_skills
    copied: List[str] = []

    for name in PLUGIN_SKILL_NAMES:
        source = os.path.join(source_root, name)
        if not os.path.isdir(source):
            continue
        destination = os.path.join(destination_root, name)
        if os.path.isdir(destination):
            if not force:
                raise BearingError(
                    "%s already exists. Re-run with --force to replace it, which is the right "
                    "move after a plugin upgrade -- a stale vendored copy keeps running and "
                    "shadows the version you just installed."
                    % os.path.relpath(destination, config.workspace)
                )
            shutil.rmtree(destination)
        ensure_dir(os.path.dirname(destination))
        shutil.copytree(source, destination)
        copied.append(os.path.relpath(destination, config.workspace).replace(os.sep, "/"))

    _pin(config)
    return {
        "copied": copied,
        "pinned_version": __version__,
        "note": (
            "These copies now take discovery precedence over the installed plugin in both "
            "Cursor and Codex. `bearing doctor` reports which copy is in effect."
        ),
    }


def pin(config: ResolvedConfig) -> Dict[str, object]:
    """Record source and version without copying. Copies must already exist."""
    if not os.path.isdir(config.layout.vendored_skills):
        raise BearingError(
            "no .agents/skills/ to pin. Run `bearing vendor` to copy the Skills first, "
            "or delete a stray copy so the installed plugin is used."
        )
    _pin(config)
    return {"pinned_version": __version__, "copied": []}


def unvendor(config: ResolvedConfig) -> List[str]:
    removed: List[str] = []
    root = config.layout.vendored_skills
    for name in PLUGIN_SKILL_NAMES:
        path = os.path.join(root, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
            removed.append(os.path.relpath(path, config.workspace).replace(os.sep, "/"))
    if os.path.isdir(root) and not os.listdir(root):
        os.rmdir(root)
        parent = os.path.dirname(root)
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    _unpin(config)
    return removed


def _pin(config: ResolvedConfig) -> None:
    """Record source and version in committed config.

    The version is the point. Without it, a promoted decision record's provenance
    trail ends at "some version of decision-recovery", which is not an audit
    trail, it is a shrug.
    """
    path = config.layout.config_file
    data = read_json(path, {}) or {}
    skills = dict(data.get("skills") or {})
    skills["source"] = "vendored"
    skills["vendored_version"] = __version__
    data["skills"] = skills
    write_json(path, data)


def _unpin(config: ResolvedConfig) -> None:
    path = config.layout.config_file
    data = read_json(path, {}) or {}
    skills = dict(data.get("skills") or {})
    skills["source"] = "plugin"
    skills["vendored_version"] = None
    data["skills"] = skills
    write_json(path, data)
