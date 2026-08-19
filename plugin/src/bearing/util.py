"""Small shared helpers. Standard library only, Python 3.9 compatible."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple


class BearingError(Exception):
    """A user-facing failure. The CLI prints these without a traceback."""


# --------------------------------------------------------------------------
# JSON / JSONL
# --------------------------------------------------------------------------

def read_json(path: str, default: Any = None) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise BearingError("%s is not valid JSON: %s" % (path, exc))


def dump_json(data: Any) -> str:
    """Canonical JSON: sorted keys, two-space indent, trailing newline.

    Deterministic by construction, because generated JSON is compared byte for
    byte by `render --check` and `package --check`.
    """
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: str, data: Any) -> bool:
    return write_text(path, dump_json(data))


def read_jsonl(path: str) -> List[Any]:
    rows: List[Any] = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise BearingError("%s line %d is not valid JSON: %s" % (path, lineno, exc))
    return rows


def append_jsonl(path: str, row: Any) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# Filesystem
# --------------------------------------------------------------------------

def ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)


def read_text(path: str, default: Optional[str] = None) -> Optional[str]:
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write_text(path: str, content: str) -> bool:
    """Write only when content differs. Returns True when the file changed.

    The no-op-on-identical behaviour is what keeps `render` idempotent and keeps
    mtimes stable, so re-rendering does not churn build caches.
    """
    existing = read_text(path)
    if existing == content:
        return False
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return True


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def rel(path: str, start: str) -> str:
    """Repo-relative POSIX path. Used in every generated artifact so output is
    identical regardless of where the workspace is checked out."""
    return os.path.relpath(path, start).replace(os.sep, "/")


# --------------------------------------------------------------------------
# Dict flattening, used by config resolution
# --------------------------------------------------------------------------

def flatten(data: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dicts to dotted paths. Lists are leaves, not recursed."""
    out: Dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "$schema":
                continue
            path = "%s.%s" % (prefix, key) if prefix else str(key)
            if isinstance(value, dict):
                nested = flatten(value, path)
                if nested:
                    out.update(nested)
                else:
                    out[path] = {}
            else:
                out[path] = value
    elif prefix:
        out[prefix] = data
    return out


def unflatten(flat: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for path, value in flat.items():
        parts = path.split(".")
        cursor = out
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
            if not isinstance(cursor, dict):  # pragma: no cover - defensive
                raise BearingError("conflicting config shape at %r" % path)
        cursor[parts[-1]] = value
    return out


def get_path(data: Any, dotted: str, default: Any = None) -> Any:
    cursor = data
    for part in dotted.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return default
        cursor = cursor[part]
    return cursor


# --------------------------------------------------------------------------
# Frontmatter (a deliberately small YAML subset)
# --------------------------------------------------------------------------

_SCALAR_TRUE = ("true", "yes", "on")
_SCALAR_FALSE = ("false", "no", "off")


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Split leading `---` frontmatter from a markdown body.

    Supports the subset that Agent Skills and subagent definitions actually
    use: scalars, one level of nesting, and inline `[a, b]` lists. A real YAML
    parser is a dependency, and this project stays dependency-free on purpose.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}, text
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}, text

    data: Dict[str, Any] = {}
    container: Optional[Dict[str, Any]] = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indented = raw.startswith((" ", "\t"))
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        target = container if (indented and container is not None) else data
        if not indented:
            container = None
        if value == "":
            if not indented:
                container = {}
                data[key] = container
            continue
        target[key] = _coerce_scalar(value)

    body = "\n".join(lines[end + 1:])
    return data, body.lstrip("\n")


def _coerce_scalar(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(part.strip()) for part in inner.split(",")]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    low = value.lower()
    if low in _SCALAR_TRUE:
        return True
    if low in _SCALAR_FALSE:
        return False
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def emit_frontmatter(data: Dict[str, Any]) -> str:
    """Serialize a flat mapping back to YAML frontmatter, key order preserved."""
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append("%s:" % key)
            for sub_key, sub_value in value.items():
                lines.append("  %s: %s" % (sub_key, _emit_scalar(sub_value)))
        else:
            lines.append("%s: %s" % (key, _emit_scalar(value)))
    lines.append("---")
    return "\n".join(lines) + "\n"


def _emit_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[%s]" % ", ".join(_emit_scalar(item) for item in value)
    return str(value)


# --------------------------------------------------------------------------
# Minimal TOML emitter
# --------------------------------------------------------------------------

def toml_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def toml_value(value: Any) -> str:
    """Emit a TOML scalar. Multi-line strings use basic-string escaping rather
    than literal blocks so round-tripping stays byte-stable."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[%s]" % ", ".join(toml_value(item) for item in value)
    return '"%s"' % toml_escape(str(value))


# --------------------------------------------------------------------------
# Terminal output
# --------------------------------------------------------------------------

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

_CODES = {"ok": "32", "warn": "33", "fail": "31", "dim": "90", "bold": "1"}


def paint(text: str, style: str) -> str:
    if not _COLOR or style not in _CODES:
        return text
    return "\033[%sm%s\033[0m" % (_CODES[style], text)


def glyph(status: str) -> str:
    return {"ok": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "SKIP", "info": "----"}.get(status, "----")


def status_line(status: str, label: str, detail: str = "") -> str:
    style = {"ok": "ok", "warn": "warn", "fail": "fail"}.get(status, "dim")
    line = "  %s  %s" % (paint(glyph(status).ljust(4), style), label)
    if detail:
        line += paint("  " + detail, "dim")
    return line


def match_any(name: str, patterns: Iterable[str]) -> bool:
    import fnmatch

    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)
