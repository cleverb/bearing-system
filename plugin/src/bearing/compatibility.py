"""Distribution evidence for runtime support.

@see ADR-0011 — support is qualified by real-client evidence bound only to
behaviorally relevant compatibility inputs.
@see ADR-0005 — fingerprints and version checks use the standard library.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from . import CONFIG_VERSION, RENDERER_VERSION
from .jsonschema import validate
from .paths import data_dir, plugin_root
from .util import dump_json, read_json, sha256_text

COMPATIBILITY_API = 1
EVIDENCE_SCHEMA_VERSION = 1

_TEXT_ARTIFACT_SUFFIXES = (
    ".py",
    ".json",
    ".md",
    ".mdc",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".sh",
    ".cfg",
)


def _artifact_digest_bytes(path: str, raw: bytes) -> str:
    """Hash artifact bytes with CRLF normalized so fingerprints match across OSes."""
    suffix = os.path.splitext(path)[1].lower()
    if suffix in _TEXT_ARTIFACT_SUFFIXES:
        try:
            raw = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass
    return hashlib.sha256(raw).hexdigest()


def _artifact_digest_text(content: str) -> str:
    return _artifact_digest_bytes("<override>", content.encode("utf-8"))


def load_support() -> Dict[str, Any]:
    return read_json(os.path.join(data_dir(), "runtime-support.json"), {}) or {}


def runtime_fingerprint(
    runtime: str,
    workspace: str,
    root: Optional[str] = None,
    overrides: Optional[Dict[str, str]] = None,
) -> str:
    return sha256_text(dump_json(runtime_inputs(runtime, workspace, root, overrides)))


def runtime_inputs(
    runtime: str,
    workspace: str,
    root: Optional[str] = None,
    overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Return the explicit, runtime-local inputs bound into Tier 4 evidence."""
    support = load_support()
    settings = (support.get("runtimes") or {}).get(runtime) or {}
    root = root or plugin_root()
    payload: Dict[str, Any] = {
        "bearing_compatibility_api": COMPATIBILITY_API,
        "renderer_version": int(settings.get("renderer_version") or RENDERER_VERSION),
        "config_schema_version": CONFIG_VERSION,
        "runtime": runtime,
        "artifacts": [],
    }
    overrides = {
        os.path.abspath(key).replace("\\", "/"): value
        for key, value in (overrides or {}).items()
    }
    for relative in sorted(settings.get("artifacts") or []):
        path = os.path.join(workspace, relative.replace("/", os.sep))
        absolute = os.path.abspath(path).replace("\\", "/")
        if absolute in overrides:
            digest = _artifact_digest_text(overrides[absolute])
        else:
            try:
                with open(path, "rb") as handle:
                    digest = _artifact_digest_bytes(path, handle.read())
            except OSError:
                digest = "missing"
        payload["artifacts"].append({"path": relative, "sha256": digest})
    return payload


def evidence_dir(workspace: str) -> str:
    return os.path.join(workspace, "conformance", "evidence")


def load_evidence(workspace: str) -> List[Dict[str, Any]]:
    directory = evidence_dir(workspace)
    if not os.path.isdir(directory):
        return []
    found: List[Dict[str, Any]] = []
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".json"):
            row = read_json(os.path.join(directory, filename))
            if isinstance(row, dict):
                found.append(row)
    return found


def evidence_errors(row: Dict[str, Any]) -> List[str]:
    schema = read_json(os.path.join(data_dir(), "conformance-evidence.schema.json"), {}) or {}
    return validate(row, schema)


def valid_evidence(runtime: str, workspace: str) -> List[Dict[str, Any]]:
    inputs = runtime_inputs(runtime, workspace)
    fingerprint = sha256_text(dump_json(inputs))
    return [
        row
        for row in load_evidence(workspace)
        if not evidence_errors(row)
        and row.get("runtime") == runtime
        and row.get("result") == "pass"
        and row.get("bearing_compatibility_api") == COMPATIBILITY_API
        and row.get("renderer_version") == inputs["renderer_version"]
        and row.get("config_schema_version") == CONFIG_VERSION
        and row.get("fingerprint") == fingerprint
        and row.get("artifacts") == inputs["artifacts"]
        and all(item.get("sha256") != "missing" for item in inputs["artifacts"])
        and all(bool(value) for value in (row.get("checks") or {}).values())
    ]


def release_errors(workspace: str) -> List[str]:
    support = load_support()
    errors: List[str] = []
    for runtime, settings in sorted((support.get("runtimes") or {}).items()):
        if settings.get("supported") and not valid_evidence(runtime, workspace):
            errors.append(
                "%s has no passing Tier 4 evidence for compatibility fingerprint %s"
                % (runtime, runtime_fingerprint(runtime, workspace)[:12])
            )
    return errors


def build_summary(workspace: str, overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    support = load_support()
    runtimes: List[Dict[str, Any]] = []
    for runtime, settings in sorted((support.get("runtimes") or {}).items()):
        evidence = valid_evidence(runtime, workspace)
        latest = sorted(evidence, key=lambda row: str(row.get("tested_at") or ""))[-1] if evidence else None
        runtimes.append(
            {
                "runtime": runtime,
                "supported": bool(settings.get("supported")),
                "discovery_mode": (
                    settings.get("qualified_discovery_mode")
                    if latest
                    else settings.get("discovery_mode")
                ) or "unsupported",
                "fingerprint": runtime_fingerprint(runtime, workspace, overrides=overrides),
                "renderer_version": int(settings.get("renderer_version") or RENDERER_VERSION),
                "config_schema_version": CONFIG_VERSION,
                "evidence": latest,
            }
        )
    return {
        "schema_version": 1,
        "bearing_compatibility_api": COMPATIBILITY_API,
        "renderer_version": RENDERER_VERSION,
        "config_schema_version": CONFIG_VERSION,
        "runtimes": runtimes,
    }


def runtime_statuses(config) -> List[Dict[str, Any]]:
    support = load_support()
    packaged = read_json(os.path.join(plugin_root(), "runtime-compatibility.json"), {}) or {}
    packaged_by_runtime = {
        entry.get("runtime"): entry
        for entry in (packaged.get("runtimes") or [])
        if isinstance(entry, dict) and entry.get("runtime")
    }
    statuses: List[Dict[str, Any]] = []
    api_incompatible = (
        packaged.get("bearing_compatibility_api") is not None
        and packaged.get("bearing_compatibility_api") != COMPATIBILITY_API
    )
    for runtime, settings in sorted((support.get("runtimes") or {}).items()):
        installed = detect_runtime_version(str(settings.get("executable") or runtime))
        packaged_entry = packaged_by_runtime.get(runtime) or {}
        selected = packaged_entry.get("evidence")
        if api_incompatible:
            status = "incompatible"
        elif selected and installed and version_in_range(installed, selected):
            status = "verified"
        elif installed and selected:
            status = "unverified-version"
        elif installed:
            status = "unknown"
        else:
            status = "unknown"
        statuses.append(
            {
                "runtime": runtime,
                "installed_version": installed,
                "discovery_mode": packaged_entry.get("discovery_mode") or settings.get("discovery_mode") or "unsupported",
                "status": status,
                "verified_range": (
                    "%s..%s" % (selected["runtime_version_min"], selected["runtime_version_max"])
                    if selected else None
                ),
                "fingerprint": packaged_entry.get("fingerprint"),
                "renderer_version": packaged_entry.get("renderer_version"),
                "config_schema_version": packaged_entry.get("config_schema_version"),
            }
        )
    return statuses


def detect_runtime_version(executable: str) -> Optional[str]:
    path = shutil.which(executable)
    if not path:
        return None
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (result.stdout or result.stderr or "").strip().split("\n")[0]
    return text or None


def version_in_range(version: str, evidence: Dict[str, Any]) -> bool:
    value = _version_tuple(version)
    low = _version_tuple(str(evidence.get("runtime_version_min") or ""))
    high = _version_tuple(str(evidence.get("runtime_version_max") or ""))
    return bool(value and low and high and low <= value <= high)


def _version_tuple(value: str) -> Tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", value)
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()
