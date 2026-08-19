"""Operator-scope CLI enablement after a marketplace plugin install.

@see ADR-0012 — user distribution is the plugin; PATH CLI is derived here.

Writes only under `user_root()` (~/.bearing). Never writes inside the plugin
tree (ADR-0002). Called from workspaceOpen, MCP start, and `bearing enable`.
"""

from __future__ import annotations

import datetime
import os
import shutil
import stat
import sys
from typing import Dict, List, Optional

from . import __version__
from .paths import operator_bin_dir, user_root
from .util import dump_json, read_json, write_text

_LAUNCHERS = ("bearing", "bearing-mcp")

_SHIM_MARKER = "BEARING operator shim — generated; do not edit."

_SHIM_UNIX = (
    '''#!/usr/bin/env python3
"""'''
    + _SHIM_MARKER
    + '''"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_LAUNCHER = {launcher!r}


def main() -> int:
    home = os.environ.get("BEARING_HOME") or os.path.join(os.path.expanduser("~"), ".bearing")
    pointer = os.path.join(home, "install.json")
    with open(pointer, encoding="utf-8") as handle:
        data = json.load(handle)
    plugin_root = data["plugin_root"]
    python = data["python"]
    script = os.path.join(plugin_root, "bin", _LAUNCHER)
    if not os.path.isfile(script):
        raise SystemExit("%s: missing plugin launcher at %s" % (_LAUNCHER, script))
    argv = [python, script] + sys.argv[1:]
    if os.name == "nt":
        raise SystemExit(subprocess.call(argv))
    os.execv(python, argv)


if __name__ == "__main__":
    raise SystemExit(main())
'''
)

_SHIM_WINDOWS = '''@echo off
REM ''' + _SHIM_MARKER + '''
REM Delegates through install.json via the Python shim beside this file.
setlocal
where py >nul 2>&1 && (
  py -3 "%~dp0{launcher}" %*
  exit /b %ERRORLEVEL%
)
python "%~dp0{launcher}" %*
'''


def load_install_pointer(home: Optional[str] = None) -> Optional[Dict[str, object]]:
    """Return install.json when it points at a tree that can still launch the CLI."""
    root = home or user_root()
    path = os.path.join(root, "install.json")
    data = read_json(path, None)
    if not isinstance(data, dict):
        return None
    plugin_root = data.get("plugin_root")
    if not plugin_root or not isinstance(plugin_root, str):
        return None
    if not _is_bearing_plugin_root(plugin_root):
        return None
    return data


def install_pointer_path() -> str:
    return os.path.join(user_root(), "install.json")


def is_operator_shim(path: str) -> bool:
    """True when `path` is a generated launcher that reads ~/.bearing/install.json."""
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as handle:
            sample = handle.read(2048)
    except OSError:
        return False
    return _SHIM_MARKER in sample and "install.json" in sample


def is_legacy_package_install(path: str) -> bool:
    """True for pipx/uv wheel console scripts, not plugin-derived shims."""
    if not path:
        return False
    resolved = os.path.realpath(path).lower()
    if "pipx" in resolved and "venvs" in resolved:
        return True
    return "site-packages" in resolved


def _is_bearing_plugin_root(path: str) -> bool:
    """True for a complete BEARING plugin tree that can run the terminal CLI.

    Marketplace copies that lack `bin/bearing` (or are marked orphaned) still
    contain `plugin.json` + Skills, but operator shims cannot launch them.
    """
    if os.path.isfile(os.path.join(path, ".orphaned_at")):
        return False
    manifest = read_json(os.path.join(path, "plugin.json"), {}) or {}
    if manifest.get("name") != "bearing":
        return False
    if not os.path.isfile(os.path.join(path, "skills", "decision-recovery", "SKILL.md")):
        return False
    return os.path.isfile(os.path.join(path, "bin", "bearing"))


def discover_plugin_roots(
    max_depth: int = 8,
    bases: Optional[List[str]] = None,
) -> List[str]:
    """Find marketplace-installed plugin trees under known client cache locations."""
    found: List[str] = []
    home = os.path.expanduser("~")
    search_bases = bases or [
        os.path.join(home, ".cursor", "plugins"),
        os.path.join(home, ".claude", "plugins"),
    ]
    for base in search_bases:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            rel = os.path.relpath(dirpath, base)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > max_depth:
                dirnames.clear()
                continue
            if "plugin.json" not in filenames:
                continue
            if _is_bearing_plugin_root(dirpath):
                found.append(os.path.abspath(dirpath))
    found.sort(
        key=lambda path: os.path.getmtime(os.path.join(path, "plugin.json")),
        reverse=True,
    )
    unique: List[str] = []
    seen = set()
    for path in found:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def resolve_enable_plugin_root(
    explicit: Optional[str] = None,
    discover: bool = False,
    start: Optional[str] = None,
) -> Optional[str]:
    """Pick which plugin tree `bearing enable` should target."""
    override = explicit or os.environ.get("BEARING_PLUGIN_ROOT")
    if override:
        path = os.path.abspath(os.path.expanduser(override))
        return path if _is_bearing_plugin_root(path) else None
    if discover:
        found = discover_plugin_roots()
        return found[0] if found else None
    if start and _is_bearing_plugin_root(start):
        return os.path.abspath(start)
    cursor = os.path.abspath(start or os.path.dirname(__file__))
    while True:
        if _is_bearing_plugin_root(cursor):
            return cursor
        parent = os.path.dirname(cursor)
        if parent == cursor:
            break
        cursor = parent
    return None


def _plugin_version(plugin_root: str) -> str:
    manifest = read_json(os.path.join(plugin_root, "plugin.json"), {}) or {}
    return str(manifest.get("version") or __version__)


def _write_executable(path: str, content: str) -> None:
    write_text(path, content)
    if os.name != "nt":
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_shims(bin_dir: str) -> List[str]:
    written: List[str] = []
    for name in _LAUNCHERS:
        unix_path = os.path.join(bin_dir, name)
        _write_executable(unix_path, _SHIM_UNIX.format(launcher=name))
        written.append(unix_path)
        if os.name == "nt":
            cmd_path = unix_path + ".cmd"
            write_text(cmd_path, _SHIM_WINDOWS.format(launcher=name))
            written.append(cmd_path)
    return written


def _mirror_to_local_bin(bin_dir: str) -> List[str]:
    """Copy shims into ~/.local/bin when that directory already exists."""
    local_bin = os.path.join(os.path.expanduser("~"), ".local", "bin")
    if not os.path.isdir(local_bin) or not os.access(local_bin, os.W_OK):
        return []
    mirrored: List[str] = []
    for name in _LAUNCHERS:
        source = os.path.join(bin_dir, name)
        if not os.path.isfile(source):
            continue
        target = os.path.join(local_bin, name)
        shutil.copy2(source, target)
        if os.name != "nt":
            mode = os.stat(target).st_mode
            os.chmod(target, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        mirrored.append(target)
    return mirrored


def ensure_enabled(
    plugin_root: str,
    python: Optional[str] = None,
    home: Optional[str] = None,
) -> Dict[str, object]:
    """Write install.json and operator shims. Failures are returned, not raised."""
    plugin_root = os.path.abspath(plugin_root)
    if not _is_bearing_plugin_root(plugin_root):
        return {
            "ok": False,
            "errors": [
                "not a complete BEARING plugin tree (need plugin.json, skills/, and "
                "bin/bearing): %s" % plugin_root
            ],
        }
    python = python or sys.executable
    bearing_home = home or user_root()
    bin_dir = os.path.join(bearing_home, "bin")
    errors: List[str] = []
    written: List[str] = []

    try:
        os.makedirs(bin_dir, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "errors": ["cannot create %s: %s" % (bin_dir, exc)]}

    pointer = {
        "plugin_root": plugin_root,
        "python": python,
        "version": _plugin_version(plugin_root),
        "updated_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    try:
        write_text(os.path.join(bearing_home, "install.json"), dump_json(pointer))
        written.append(os.path.join(bearing_home, "install.json"))
    except OSError as exc:
        errors.append("cannot write install.json: %s" % exc)

    try:
        written.extend(_write_shims(bin_dir))
    except OSError as exc:
        errors.append("cannot write operator shims: %s" % exc)

    try:
        written.extend(_mirror_to_local_bin(bin_dir))
    except OSError as exc:
        errors.append("cannot mirror to ~/.local/bin: %s" % exc)

    return {
        "ok": not errors,
        "plugin_root": plugin_root,
        "bin_dir": bin_dir,
        "written": written,
        "errors": errors,
    }
