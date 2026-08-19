"""The `bearing` command line.

@see ADR-0008 — judgment belongs to Skills; this file is mechanical. Recovery
has no extractor binary.
@see ADR-0005 — standard library argparse, no third-party CLI framework.
@see ADR-0009 — assessment is informational; this file must not fail the process.

Everything here is deterministic and side-effect-explicit. That is a deliberate
division of labour: the *judgment* in this system belongs to Skills and to humans,
and the CLI's job is the mechanical part -- resolving config, generating adapters,
computing metrics, checking invariants. A command that needed a model to decide
what to do would not be verifiable, and the conformance suite depends on every
command in this file producing the same output from the same inputs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .config import ResolvedConfig, resolve
from .util import BearingError, dump_json, paint, status_line

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(args: argparse.Namespace, require_init: bool = True) -> ResolvedConfig:
    flags: Dict[str, Any] = {}
    if getattr(args, "decisions_path", None):
        flags["decisions.path"] = args.decisions_path
    if getattr(args, "profile", None):
        flags["profile"] = args.profile
    config = resolve(workspace=getattr(args, "workspace", None), flags=flags)
    if config.errors and require_init:
        raise BearingError(
            "configuration is not usable:\n  - %s" % "\n  - ".join(config.errors)
        )
    if require_init:
        config.require_initialized()
    return config


def _heading(text: str) -> None:
    print()
    print(paint(text, "bold"))
    print()


def _emit(data: Any, as_json: bool) -> None:
    if as_json:
        print(dump_json(data), end="")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    from .scaffold import choose_decisions_path, deviation_record, deviation_warning, scaffold

    config = resolve(workspace=getattr(args, "workspace", None))
    workspace = config.workspace

    decisions_rel, notes = choose_decisions_path(
        workspace, args.decisions_path, args.yes
    )

    # Re-resolve so the chosen path drives Layout for the whole scaffold.
    config = resolve(workspace=workspace, flags={"decisions.path": decisions_rel})

    _heading("bearing init  (%s)" % workspace)
    for note in notes:
        print(status_line("ok", "detection", note))

    warning = deviation_warning(decisions_rel)
    if warning:
        print(status_line("warn", "decisions directory naming", warning))

    outcome = scaffold(config, decisions_rel)
    for path in outcome["created"]:
        print(status_line("ok", "created", path))
    if outcome["existing"]:
        print(status_line("ok", "already present", "%d path(s) left untouched" % len(outcome["existing"])))

    draft = deviation_record(config)
    if draft:
        target = os.path.join(config.layout.decisions, "0001-decision-record-location.md")
        if args.record_deviation:
            from .util import write_text

            write_text(target, draft)
            print(status_line("ok", "recorded deviation", os.path.relpath(target, workspace)))
        else:
            print()
            print(
                paint(
                    "This repository keeps decisions in %r rather than the documented default."
                    % decisions_rel,
                    "warn",
                )
            )
            print(
                "BEARING will not rename it. Re-run with --record-deviation to add a decision\n"
                "record explaining the location, so the next person who looks in the default\n"
                "place finds an explanation instead of an empty directory."
            )

    if not args.no_render:
        print()
        args.check = False
        args.ephemeral = False
        args.emit_plugin_paths = False
        cmd_render(args)

    print()
    print(paint("Next: `bearing doctor` to verify everything resolves.", "dim"))
    return EXIT_OK


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import report, run_checks

    config = resolve(workspace=getattr(args, "workspace", None))
    checks = run_checks(config, require_clean_tree=args.strict)
    if args.json:
        payload = [
            {
                "status": check.status,
                "label": check.label,
                "detail": check.detail,
                "remedy": check.remedy,
                "gating": check.gating,
            }
            for check in checks
        ]
        _emit(payload, True)
        return EXIT_FAIL if any(c.status == "fail" and c.gating for c in checks) else EXIT_OK
    return report(checks, "bearing doctor")


def cmd_preflight(args: argparse.Namespace) -> int:
    from .doctor import preflight, report

    config = resolve(workspace=getattr(args, "workspace", None))
    passed, checks = preflight(config)
    code = report(checks, "bearing preflight  (onboarding Step 0a)")
    if not passed:
        print(
            paint(
                "Onboarding stops here. Preflight verifies preconditions rather than installing\n"
                "them: install belongs to the distribution layer, and bootstrap to `bearing init`.\n",
                "dim",
            )
        )
    return code


def cmd_assessment(args: argparse.Namespace) -> int:
    """Scorecard. Always exits 0 — unreadiness is not a merge gate.

    @see ADR-0009
    """
    from .assessment import assess, render_text

    config = resolve(workspace=getattr(args, "workspace", None))
    result = assess(config)
    if args.json:
        print(dump_json(result), end="")
    else:
        print(render_text(result), end="")
    return EXIT_OK


# ---------------------------------------------------------------------------
# render / package
# ---------------------------------------------------------------------------

def cmd_render(args: argparse.Namespace) -> int:
    from .agentsmd import apply_block, check_block, rule_body, targets as agents_targets
    from .artifacts import apply as apply_artifacts, build_lock, read_lock, write_lock
    from .render import load_subagents, render_contracts, render_rules, render_subagents

    config = _load(args)
    ephemeral_dir = None
    if getattr(args, "ephemeral", False):
        ephemeral_dir = tempfile.mkdtemp(prefix="bearing-projection-")

    subagents = load_subagents()
    body = rule_body(config)
    artifacts, skips = render_subagents(config, subagents, ephemeral_dir)
    rule_artifacts, rule_skips = render_rules(config, body, ephemeral_dir)
    artifacts += rule_artifacts
    skips += rule_skips
    contract_artifacts, contract_skips = render_contracts(config, ephemeral_dir)
    artifacts += contract_artifacts
    skips += contract_skips

    if getattr(args, "emit_plugin_paths", False):
        # Cursor's workspaceOpen hook consumes this to load ephemeral adapters
        # for the session, so nothing is written into the working tree at all.
        apply_artifacts(artifacts, config.workspace)
        print(json.dumps({"pluginPaths": [ephemeral_dir] if ephemeral_dir else []}))
        return EXIT_OK

    previous = read_lock(config.layout.lock)
    check = getattr(args, "check", False)
    outcome = apply_artifacts(artifacts, config.workspace, check=check, previous_lock=previous)

    _heading("bearing render%s" % ("  --check" % () if check else ""))

    block_problems: List[str] = []
    for path, block_body, header in agents_targets(config):
        rel = os.path.relpath(path, config.workspace)
        if check:
            drift = check_block(path, block_body)
            if drift:
                block_problems.append(drift)
                print(status_line("fail", "block %s" % rel, drift))
            else:
                print(status_line("ok", "block %s" % rel, "in sync"))
        else:
            changed, action = apply_block(path, block_body, header)
            print(
                status_line(
                    "ok",
                    "block %s" % rel,
                    "%s (content outside the markers untouched)" % action if changed else "unchanged",
                )
            )

    for path in outcome.written:
        print(status_line("ok", "wrote", path))
    for path, why in outcome.drifted:
        print(status_line("fail", "drifted", "%s — %s" % (path, why)))
    for path in outcome.missing:
        print(status_line("fail", "missing", path))
    for path in outcome.orphaned:
        print(
            status_line(
                "warn" if check else "ok",
                "orphaned" if check else "removed orphan",
                "%s — no longer produced by the current config" % path,
            )
        )
    if outcome.unchanged:
        print(status_line("ok", "unchanged", "%d artifact(s)" % len(outcome.unchanged)))

    for skip in skips:
        print(status_line("skip", "%s -> %s" % (skip.kind, skip.target), skip.reason))

    lock = build_lock(artifacts, skips, config.workspace)
    if check:
        current = read_lock(config.layout.lock)
        lock_stale = current != lock
        if lock_stale:
            print(status_line("fail", "projections.lock.json", "out of date"))
        else:
            print(status_line("ok", "projections.lock.json", "current"))
        failed = bool(block_problems) or not outcome.clean or lock_stale
        print()
        if failed:
            print(paint("DRIFT: generated adapters do not match their canonical sources.", "fail"))
            print(
                paint(
                    "Run `bearing render`. A generated file is never a second source of truth;\n"
                    "edit the canonical source instead.",
                    "dim",
                )
            )
            print()
            return EXIT_FAIL
        print(paint("OK: no drift.", "ok"))
        print()
        return EXIT_OK

    write_lock(config.layout.lock, lock)
    print(
        status_line(
            "ok",
            "projections.lock.json",
            "%d artifact(s), %d recorded skip(s)" % (len(artifacts), len(skips)),
        )
    )
    print()
    return EXIT_OK


def cmd_package(args: argparse.Namespace) -> int:
    """Maintainer command: regenerate every client manifest from `plugin.json`."""
    from .artifacts import apply as apply_artifacts
    from .manifests import all_package_artifacts, version_consistency_errors
    from .paths import find_workspace_root, plugin_root

    workspace = find_workspace_root(getattr(args, "workspace", None))
    root = plugin_root()

    problems = version_consistency_errors(root, __version__)
    if problems:
        raise BearingError("\n  ".join(problems))

    artifacts, skips = all_package_artifacts(workspace, root)
    outcome = apply_artifacts(artifacts, workspace, check=args.check)

    _heading("bearing package%s" % ("  --check" if args.check else ""))
    for path in outcome.written:
        print(status_line("ok", "wrote", path))
    for path, why in outcome.drifted:
        print(status_line("fail", "drifted", "%s — %s" % (path, why)))
    for path in outcome.missing:
        print(status_line("fail", "missing", path))
    if outcome.unchanged:
        print(status_line("ok", "unchanged", "%d artifact(s)" % len(outcome.unchanged)))
    for skip in skips:
        print(status_line("skip", "%s -> %s" % (skip.kind, skip.target), skip.reason))

    print()
    if args.check and not outcome.clean:
        print(paint("DRIFT: client manifests do not match plugin/plugin.json.", "fail"))
        print()
        return EXIT_FAIL
    print(paint("OK: %d manifest artifact(s) current." % len(artifacts), "ok"))
    print()
    return EXIT_OK


# ---------------------------------------------------------------------------
# index / lint
# ---------------------------------------------------------------------------

def cmd_index(args: argparse.Namespace) -> int:
    from .decisions import build_index, estimate_index_tokens, load_records
    from .util import write_json

    config = _load(args)
    records = load_records(config.layout)
    index = build_index(records)
    tokens = estimate_index_tokens(index)
    budget = int(config.get("verify.index_token_budget") or 4000)

    if args.json:
        _emit(index, True)
        return EXIT_OK

    changed = write_json(config.layout.index, index)
    _heading("bearing index")
    print(
        status_line(
            "ok",
            "wrote" if changed else "unchanged",
            "%s — %d entr(ies)" % (config.layout.index_name, len(records)),
        )
    )
    status = "ok" if tokens <= budget else "fail"
    print(
        status_line(
            status,
            "disclosure budget",
            "roughly %d tokens against a ceiling of %d" % (tokens, budget),
        )
    )
    if tokens > budget:
        print(
            paint(
                "        This file is loaded on every task. An index that grows without bound\n"
                "        silently reverses the framework's value.",
                "dim",
            )
        )
    print()
    return EXIT_OK if tokens <= budget else EXIT_FAIL


def cmd_lint(args: argparse.Namespace) -> int:
    from .lint import run, summarize

    config = _load(args)
    findings = run(config)
    errors, warnings = summarize(findings)

    if args.json:
        _emit(
            [
                {
                    "severity": finding.severity,
                    "code": finding.code,
                    "location": finding.location,
                    "message": finding.message,
                }
                for finding in findings
            ],
            True,
        )
        return EXIT_FAIL if errors else EXIT_OK

    _heading("bearing lint")
    if not findings:
        print(status_line("ok", "decision graph", "no findings"))
    for finding in findings:
        print(
            status_line(
                "fail" if finding.severity == "error" else "warn",
                "%s %s" % (finding.code, finding.location),
                finding.message,
            )
        )
    print()
    summary = "%d error(s), %d warning(s)" % (errors, warnings)
    if errors:
        print(paint("FAIL: " + summary, "fail"))
        print(
            paint(
                "These are structural failures — broken links and dead ends — which is the only\n"
                "class of finding permitted to block a merge alongside an accepted Contract.",
                "dim",
            )
        )
        print()
        return EXIT_FAIL
    print(paint("OK: " + summary, "ok"))
    print()
    return EXIT_OK


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

_PILLAR_LABEL = {
    "escalate": "ESCALATE — if intent is missing, stop",
    "anchor": "ANCHOR — wire implementation to intent",
    "project": "PROJECT — standardize the source, generate the adapters",
    "evolve": "EVOLVE — a stateful graph, not a static library",
    "usability": "USABILITY — fit and finish",
}


def cmd_verify(args: argparse.Namespace) -> int:
    from .verify import PILLARS, pillar_verdicts, run

    config = _load(args)
    selected = [pillar for pillar in PILLARS if getattr(args, pillar, False)] or None
    results = run(config, selected)

    if args.json:
        _emit(
            [
                {
                    "pillar": result.pillar,
                    "name": result.name,
                    "status": result.status,
                    "detail": result.detail,
                    "hard": result.hard,
                }
                for result in results
            ],
            True,
        )
        verdicts = pillar_verdicts(results)
        return EXIT_FAIL if "fail" in verdicts.values() else EXIT_OK

    _heading("bearing verify  —  mandate conformance")
    current = None
    for result in results:
        if result.pillar != current:
            current = result.pillar
            print(paint("  " + _PILLAR_LABEL.get(current, current.upper()), "bold"))
        print(status_line(result.status, result.name, result.detail))

    verdicts = pillar_verdicts(results)
    print()
    print(paint("  Verdict by pillar", "bold"))
    for pillar, verdict in verdicts.items():
        print(status_line(verdict, _PILLAR_LABEL.get(pillar, pillar), ""))

    failed = [pillar for pillar, verdict in verdicts.items() if verdict == "fail"]
    warned = [pillar for pillar, verdict in verdicts.items() if verdict == "warn"]
    print()
    if failed:
        print(paint("FAIL: %s" % ", ".join(failed), "fail"))
        print()
        return EXIT_FAIL
    if warned:
        print(paint("PASS with warnings: %s" % ", ".join(warned), "warn"))
        print(
            paint(
                "Warnings mean a mandate metric was unmeasured or soft-failed, not that it passed.",
                "dim",
            )
        )
        print()
        return EXIT_OK
    print(paint("PASS: every pillar conforms.", "ok"))
    print()
    return EXIT_OK


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> int:
    from .report import cost_report, pilot_report

    config = _load(args)
    if args.pilot:
        text, code = pilot_report(config)
        print(text, end="")
        return code
    print(cost_report(config, include_tokens=not args.no_tokens), end="")
    return EXIT_OK


# ---------------------------------------------------------------------------
# vendor / uninstall
# ---------------------------------------------------------------------------

def cmd_vendor(args: argparse.Namespace) -> int:
    from .vendor import pin, unvendor, vendor

    config = _load(args)
    _heading("bearing vendor")
    if args.remove:
        removed = unvendor(config)
        for path in removed:
            print(status_line("ok", "removed", path))
        print(status_line("ok", "skills.source", "reset to 'plugin'"))
        print()
        return EXIT_OK

    if args.pin:
        outcome = pin(config)
        print(status_line("ok", "pinned version", str(outcome["pinned_version"])))
        print(status_line("ok", "skills.source", "vendored"))
        print()
        return EXIT_OK

    outcome = vendor(config, force=args.force)
    for path in outcome["copied"]:
        print(status_line("ok", "vendored", path))
    print(status_line("ok", "pinned version", str(outcome["pinned_version"])))
    print(status_line("warn", "discovery precedence", str(outcome["note"])))
    print()
    return EXIT_OK


def cmd_uninstall(args: argparse.Namespace) -> int:
    from .uninstall import preserved_paths, removable_paths, uninstall

    config = _load(args)
    _heading("bearing uninstall%s" % ("  --dry-run" if args.dry_run else ""))

    if args.dry_run:
        for path in removable_paths(config):
            print(status_line("ok", "would remove", os.path.relpath(path, config.workspace)))
        for path in preserved_paths(config):
            print(status_line("ok", "would keep", os.path.relpath(path, config.workspace)))
        print()
        print(
            paint(
                "Decision content is never removed. Every record, the index, the shadow graph,\n"
                "the rejection ledger, and the transcripts survive uninstall — they are the\n"
                "repository's knowledge, not BEARING's.",
                "dim",
            )
        )
        print()
        return EXIT_OK

    outcome = uninstall(config, keep_config=not args.purge_config)
    for path in outcome["removed"]:
        print(status_line("ok", "removed", path))
    for name in outcome["blocks_stripped"]:
        print(status_line("ok", "stripped block", "%s (rest of the file untouched)" % name))
    for path in outcome["preserved"]:
        print(status_line("ok", "kept", path))
    print()
    print(paint("Decision content left intact.", "ok"))
    print()
    return EXIT_OK


# ---------------------------------------------------------------------------
# onboard
# ---------------------------------------------------------------------------

def cmd_onboard(args: argparse.Namespace) -> int:
    from .doctor import preflight, report
    from .profiles import Profile, describe, load_state, plan_waves, save_state, wave_gate

    config = _load(args)
    profile = Profile(args.profile or config.get("profile") or "pilot", config)

    _heading("bearing onboard  —  profile %r" % profile.name)
    print("  " + describe(profile.name))
    print()

    for message in profile.readiness_errors():
        print(status_line("fail", "profile readiness", message))
    if profile.readiness_errors():
        print()
        return EXIT_FAIL

    passed, checks = preflight(config)
    if not passed:
        report(checks, "Step 0a — Preflight")
        return EXIT_FAIL
    print(status_line("ok", "Step 0a preflight", "%d check(s) passed" % len(checks)))

    ready, reason = wave_gate(profile, config)
    print(status_line("ok" if ready else "warn", "wave gate", reason))

    waves = plan_waves(profile, args.candidates or 0)
    if waves:
        print()
        print(paint("  Review plan", "bold"))
        for wave in waves:
            print(
                status_line(
                    "ok",
                    "wave %d" % wave["wave"],
                    "%d candidate(s), roughly %d min of review"
                    % (wave["candidates"], wave["estimated_review_minutes"]),
                )
            )

    state = load_state(config)
    state.update(
        {
            "profile": profile.name,
            "wave_size": profile.wave_size,
            "max_promotions": profile.spec["max_promotions"],
            "creates_branch": profile.spec["creates_branch"],
            "runs_pilot": profile.spec["runs_pilot"],
            "preflight": "passed",
        }
    )
    save_state(config, state)

    print()
    print(paint("  Guardrails that do not relax in any profile", "bold"))
    for line in (
        "the human authority boundary on promotion",
        "wave-bounded review — each wave fully reviewed before the next is generated",
        "pre-registration of the pass/fail bar before Step 5",
        "coordination between recovery scope and test-ticket selection",
        "the same frozen baseline tag, with elapsed time noted in the report",
    ):
        print(status_line("ok", line, ""))

    print()
    print(paint("State written to .bearing/runs/onboarding.json.", "dim"))
    print(
        paint(
            "Steps 0 through 6 are carried out by the decision-onboarding Skill; this command\n"
            "gates and records them. Load the Skill to proceed.",
            "dim",
        )
    )
    print()
    return EXIT_OK


# ---------------------------------------------------------------------------
# path resolution helpers used by the Skills
# ---------------------------------------------------------------------------

def cmd_context(args: argparse.Namespace) -> int:
    """Print index entries whose scope matches a file — generation-time discovery."""
    from .decisions import context_entries

    config = _load(args)
    raw = args.path
    if os.path.isabs(raw):
        rel = os.path.relpath(raw, config.workspace)
    else:
        rel = raw
    rel = rel.replace(os.sep, "/").lstrip("./")
    entries = context_entries(config.layout, rel)
    if args.json:
        print(dump_json({"path": rel, "entries": entries}), end="")
        return EXIT_OK
    if not entries:
        print("No decision records in scope for %s." % rel)
        print(
            "Load %s first; escalate rather than guessing."
            % os.path.join(config.layout.decisions_rel, config.layout.index_name)
        )
        return EXIT_OK
    _heading("bearing context  %s" % rel)
    for entry in entries:
        print(
            "  %s  [%s / %s]  %s"
            % (
                entry.get("id"),
                entry.get("eocr_function"),
                entry.get("lifecycle_state"),
                entry.get("trigger"),
            )
        )
        print(paint("    scope: %s" % entry.get("scope"), "dim"))
        print(paint("    source: %s" % entry.get("source"), "dim"))
    print()
    return EXIT_OK


def cmd_schema(args: argparse.Namespace) -> int:
    """Resolve a schema path from the plugin root.

    This is how `decision-interview` uses `decision-recovery`'s candidate schema.
    A literal `../decision-recovery/schemas/candidate.schema.json` breaks the
    moment the plugin is installed: clients copy the plugin directory, and Agent
    Plugins v1.0.0 section 4.1.3 requires them to reject package paths that
    resolve outside the plugin root. Resolving from the root works whether BEARING
    is installed, vendored, or run from a checkout.
    """
    from .paths import data_dir, plugin_root

    if args.name == "config":
        # Config's schema lives with the CLI's packaged data rather than with a
        # skill, and its `$schema` URL is not resolvable offline, so an editor or
        # a CI step needs a real path.
        path = os.path.join(data_dir(), "config.schema.json")
    else:
        path = os.path.join(
            plugin_root(),
            "skills",
            "decision-recovery",
            "schemas",
            "%s.schema.json" % args.name,
        )
    if not os.path.isfile(path):
        raise BearingError("no schema named %r (looked in %s)" % (args.name, os.path.dirname(path)))
    print(path)
    return EXIT_OK


def cmd_ledger(args: argparse.Namespace) -> int:
    config = _load(args)
    print(config.layout.cost_ledger)
    return EXIT_OK


def cmd_eval(args: argparse.Namespace) -> int:
    config = _load(args)
    print(os.path.join(config.layout.eval_dir, args.set))
    return EXIT_OK


def cmd_transcripts(args: argparse.Namespace) -> int:
    config = _load(args)
    if config.layout.transcript_retention == "none":
        raise BearingError(
            "interview.transcripts.retention is 'none', so transcripts are not written. The "
            "candidate's evidence excerpt is the only surviving record, and a promoted "
            "Contract's full provenance is not reconstructible from this repository."
        )
    print(config.layout.transcripts)
    return EXIT_OK


def cmd_config(args: argparse.Namespace) -> int:
    from .config import classify

    config = _load(args, require_init=False)
    if args.key:
        value = config.get(args.key)
        if args.origin:
            print(
                "%s = %s  [%s fact, from %s]"
                % (args.key, json.dumps(value), classify(args.key) or "unclassified", config.origin(args.key))
            )
        else:
            print(json.dumps(value))
        return EXIT_OK

    if args.origin:
        _heading("bearing config  —  resolved values and where each came from")
        from .util import flatten

        for key in sorted(flatten(config.data)):
            print(
                "  %-52s %-10s %s"
                % (key, classify(key) or "?", paint(config.origin(key), "dim"))
            )
        print()
        print(paint("  Precedence", "bold"))
        print("  repo facts:     defaults < user < repo < local < env < flags")
        print("  operator facts: defaults < repo < user < local < env < flags")
        print()
        print(
            paint(
                "  Split by whose fact it is, not by which file is nearer. A repository owns\n"
                "  where its decisions live; an operator owns which model they pay for.",
                "dim",
            )
        )
        print()
        return EXIT_OK

    _emit(config.data, True)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bearing",
        description="BEARING: an EOCR-based decision system for human-agent engineering.",
    )
    parser.add_argument("--version", action="version", version="bearing %s" % __version__)
    parser.add_argument(
        "-C",
        "--workspace",
        default=None,
        help="operate on this workspace instead of the current directory",
    )
    subparsers = parser.add_subparsers(dest="command")

    def add(name: str, help_text: str, handler) -> argparse.ArgumentParser:
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        sub.add_argument("-C", "--workspace", default=None, help=argparse.SUPPRESS)
        sub.set_defaults(handler=handler)
        return sub

    init = add("init", "Bootstrap this workspace, detecting existing conventions.", cmd_init)
    init.add_argument("--decisions-path", default=None, help="skip detection and use this path")
    init.add_argument("--yes", action="store_true", help="accept detected defaults without prompting")
    init.add_argument(
        "--record-deviation",
        action="store_true",
        help="write a decision record explaining a non-default decisions location",
    )
    init.add_argument("--no-render", action="store_true", help="skip the initial projection render")

    doctor = add("doctor", "Report what resolves, from where, and what is broken.", cmd_doctor)
    doctor.add_argument("--strict", action="store_true", help="also require a clean working tree")
    doctor.add_argument("--json", action="store_true")

    assessment = add(
        "assessment",
        "Score agentic decision readiness (informational; always exits 0).",
        cmd_assessment,
    )
    assessment.add_argument("--json", action="store_true")

    add("preflight", "Onboarding Step 0a: verify preconditions before any pipeline step.", cmd_preflight)

    render = add("render", "Generate runtime adapters from canonical sources.", cmd_render)
    render.add_argument("--check", action="store_true", help="fail on drift instead of writing")
    render.add_argument(
        "--ephemeral",
        action="store_true",
        help="render to a session temp directory; commit nothing",
    )
    render.add_argument(
        "--emit-plugin-paths",
        action="store_true",
        help="print {\"pluginPaths\": [...]} for Cursor's workspaceOpen hook",
    )

    package = add("package", "Maintainer: regenerate client manifests from plugin.json.", cmd_package)
    package.add_argument("--check", action="store_true", help="fail on drift instead of writing")

    index = add("index", "Regenerate the progressive-disclosure index.", cmd_index)
    index.add_argument("--json", action="store_true", help="print the index instead of writing it")

    lint = add("lint", "Check decision-graph structural integrity.", cmd_lint)
    lint.add_argument("--json", action="store_true")

    verify = add("verify", "Run the mandate conformance suite.", cmd_verify)
    for pillar in ("escalate", "anchor", "project", "evolve", "usability"):
        verify.add_argument("--%s" % pillar, action="store_true", help="run only this pillar")
    verify.add_argument("--json", action="store_true")

    report_cmd = add("report", "Cost and outcome reporting.", cmd_report)
    report_cmd.add_argument("--pilot", action="store_true", help="pilot report with pre-registration check")
    report_cmd.add_argument("--no-tokens", action="store_true", help="omit the token section")

    vendor_cmd = add("vendor", "Copy the Skills into this repository and pin the version.", cmd_vendor)
    vendor_cmd.add_argument("--force", action="store_true", help="replace an existing vendored copy")
    vendor_cmd.add_argument("--remove", action="store_true", help="remove vendored copies")
    vendor_cmd.add_argument(
        "--pin",
        action="store_true",
        help="record skills.source=vendored and the current version without copying",
    )

    uninstall_cmd = add("uninstall", "Remove generated adapters and run state; keep decisions.", cmd_uninstall)
    uninstall_cmd.add_argument("--dry-run", action="store_true", help="list what would change")
    uninstall_cmd.add_argument("--purge-config", action="store_true", help="also remove .bearing/config.json")

    onboard = add("onboard", "Gate and record the onboarding pipeline.", cmd_onboard)
    onboard.add_argument("--profile", choices=("pilot", "thorough", "audit"), default=None)
    onboard.add_argument("--candidates", type=int, default=0, help="candidate count to plan waves for")

    schema = add("schema", "Print the resolved path to a shared schema.", cmd_schema)
    schema.add_argument("name", choices=("candidate", "evidence", "config"))

    context = add(
        "context",
        "Print decision-index entries whose scope matches a file.",
        cmd_context,
    )
    context.add_argument("path", help="workspace-relative file path")
    context.add_argument("--json", action="store_true")

    add("ledger", "Print the resolved cost-ledger path.", cmd_ledger)

    eval_cmd = add("eval", "Print the resolved path to an evaluation set.", cmd_eval)
    eval_cmd.add_argument("set", choices=("gold", "dark", "negative", "escalation"))

    add("transcripts", "Print the resolved interview-transcript path.", cmd_transcripts)

    config_cmd = add("config", "Print resolved configuration.", cmd_config)
    config_cmd.add_argument("key", nargs="?", default=None, help="a dotted key, e.g. decisions.path")
    config_cmd.add_argument(
        "--origin", action="store_true", help="show which layer each value came from"
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.handler(args)
    except BearingError as error:
        print()
        print(paint("bearing: %s" % error, "fail"), file=sys.stderr)
        print()
        return EXIT_FAIL
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
