#!/usr/bin/env python3
"""Claude Code adapter for ADR-0010 Discover injection.

The canonical operation is resolve-and-inject. Interrupt/retry is selected only
for a direct mutation whose tool input was created before PreToolUse context can
influence it; it is an adapter fallback, not part of the Decision System model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(PLUGIN_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from bearing.config import resolve  # noqa: E402
from bearing.decisions import accepted_contracts_for_path  # noqa: E402
from bearing.util import read_json, write_json  # noqa: E402
from bearing.workspace import effective_workspace_files  # noqa: E402


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (TypeError, ValueError):
        return _emit({})

    workspace = os.path.abspath(str(payload.get("cwd") or os.getcwd()))
    config = resolve(workspace=workspace)
    if not config.initialized:
        return _emit({})

    event = str(payload.get("hook_event_name") or "")
    if event == "UserPromptSubmit":
        return _prompt_injection(payload, config)

    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or tool_input.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return _emit({})
    absolute = raw_path if os.path.isabs(raw_path) else os.path.join(workspace, raw_path)
    absolute = os.path.abspath(absolute)
    try:
        if os.path.commonpath((absolute, workspace)) != workspace:
            return _emit({})
    except ValueError:
        return _emit({})
    rel = os.path.relpath(absolute, workspace).replace(os.sep, "/")

    try:
        contracts = accepted_contracts_for_path(config.layout, rel)
    except Exception as error:  # hook boundary: convert failures into a safe client response
        return _deny("BEARING could not resolve authoritative context for %s: %s" % (rel, error))
    if not contracts:
        return _emit({})

    context = _context_text(rel, contracts)
    digest = hashlib.sha256(context.encode("utf-8")).hexdigest()
    state_path = _state_path(config.workspace, str(payload.get("session_id") or "session"))
    state = read_json(state_path, {}) or {}
    if state.get(rel) == digest:
        return _emit({})

    try:
        state[rel] = digest
        write_json(state_path, state)
    except OSError as error:
        return _deny("BEARING could not record injected context for %s: %s" % (rel, error))

    if tool_name == "Read":
        return _emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": context,
                }
            }
        )
    if tool_name in ("Edit", "Write"):
        return _deny(context + "\nRe-evaluate and retry this mutation with these Contracts in context.")
    return _emit({})


def _context_text(path: str, contracts) -> str:
    lines = ["BEARING context for %s:" % path]
    for entry in contracts:
        lines.append(
            "- %s [%s]: %s (source: %s)"
            % (entry["id"], entry["lifecycle_state"], entry["trigger"], entry["source"])
        )
    return "\n".join(lines)


def _prompt_injection(payload, config) -> int:
    """Inject early when a prompt names an existing effective workspace file."""
    prompt = str(payload.get("prompt") or "")
    mentioned = set(
        match.rstrip(".,:;)]}")
        for match in re.findall(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+", prompt)
    )
    effective = set(effective_workspace_files(config))
    paths = sorted(path for path in mentioned if path in effective)
    if not paths:
        return _emit({})
    contexts = []
    state_path = _state_path(config.workspace, str(payload.get("session_id") or "session"))
    state = read_json(state_path, {}) or {}
    try:
        for path in paths:
            contracts = accepted_contracts_for_path(config.layout, path)
            if not contracts:
                continue
            context = _context_text(path, contracts)
            digest = hashlib.sha256(context.encode("utf-8")).hexdigest()
            if state.get(path) != digest:
                contexts.append(context)
                state[path] = digest
        if contexts:
            write_json(state_path, state)
    except Exception as error:
        return _emit({"systemMessage": "BEARING context resolution failed: %s" % error})
    if not contexts:
        return _emit({})
    return _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n\n".join(contexts),
            }
        }
    )


def _state_path(workspace: str, session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_id)[:80] or "session"
    return os.path.join(workspace, ".bearing", "runtime", "context", safe + ".json")


def _deny(reason: str) -> int:
    return _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def _emit(payload) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
