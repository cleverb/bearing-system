#!/usr/bin/env python3
"""Record one real-client Tier 4 conformance run.

This recorder deliberately does not infer success from a manifest parser. The
operator or client-specific automation supplies the six observed checks after
installing the release candidate; this script binds them to the exact relevant
artifact fingerprint and validates the resulting evidence.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "plugin", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from bearing import CONFIG_VERSION  # noqa: E402
from bearing.compatibility import (  # noqa: E402
    COMPATIBILITY_API,
    evidence_errors,
    runtime_fingerprint,
    runtime_inputs,
)
from bearing.util import write_json  # noqa: E402

CHECKS = (
    "install",
    "skill_discovery",
    "agent_acceptance",
    "hook_execution",
    "readonly_boundary",
    "uninstall_preservation",
)
EXECUTABLES = {"cursor": "cursor-agent", "claude": "claude", "codex": "codex"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Tier 4 real-client conformance evidence.")
    parser.add_argument("--runtime", required=True, choices=sorted(EXECUTABLES))
    parser.add_argument("--runtime-version", default=None)
    parser.add_argument("--version-min", default=None)
    parser.add_argument("--version-max", default=None)
    parser.add_argument("--pass-check", action="append", default=[], choices=CHECKS)
    parser.add_argument("--fail-check", action="append", default=[], choices=CHECKS)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    version = args.runtime_version or _version(EXECUTABLES[args.runtime])
    if not version:
        parser.error("runtime version could not be detected; pass --runtime-version")
    observed = {name: name in args.pass_check and name not in args.fail_check for name in CHECKS}
    missing = [name for name in CHECKS if name not in args.pass_check and name not in args.fail_check]
    if missing:
        parser.error("record every check with --pass-check or --fail-check: %s" % ", ".join(missing))

    inputs = runtime_inputs(args.runtime, REPO)
    missing_artifacts = [
        item["path"] for item in inputs["artifacts"] if item["sha256"] == "missing"
    ]
    if missing_artifacts:
        parser.error("runtime compatibility artifact(s) missing: %s" % ", ".join(missing_artifacts))
    row = {
        "schema_version": 1,
        "runtime": args.runtime,
        "runtime_version_min": args.version_min or version,
        "runtime_version_max": args.version_max or version,
        "platform": platform.platform(),
        "tested_at": datetime.date.today().isoformat(),
        "bearing_compatibility_api": COMPATIBILITY_API,
        "renderer_version": inputs["renderer_version"],
        "config_schema_version": CONFIG_VERSION,
        "fingerprint": runtime_fingerprint(args.runtime, REPO),
        "artifacts": inputs["artifacts"],
        "checks": observed,
        "result": "pass" if all(observed.values()) else "fail",
        "notes": args.notes,
    }
    errors = evidence_errors(row)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    destination = os.path.join(REPO, "conformance", "evidence", "%s-%s.json" % (args.runtime, _slug(version)))
    write_json(destination, row)
    print(destination)
    return 0


def _version(executable: str):
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout or result.stderr or "").strip().split("\n")[0] or None


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() or character in ".-" else "-" for character in value)[:80]


if __name__ == "__main__":
    raise SystemExit(main())
