"""`bearing doctor` and the optional controlled-pilot preflight.

@see ADR-0002 — doctor flags runtime data that has drifted back into the plugin tree.

Install is not a pipeline step. It is a precondition owned by the distribution
layer, and the gap the original onboarding spec skipped over -- a repository with
no `.agents/` tree at all -- is closed by *verifying* that precondition rather
than by adding an install step to a procedure that has no business installing
anything.

So there are three layers, and preflight sits on the seam between the first two:

1. **Distribution** -- the plugin is installed once per user or organization.
2. **Bootstrap** -- `bearing init` writes config and scaffolds the corpus.
3. **Operation** -- normal BEARING use or an optional onboarding evaluation.

Every check reports a remedy, because a preflight failure that does not say what
to run is just a slower way of getting stuck.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .config import LAYER_LOCAL, LAYER_REPO, LAYER_USER, ResolvedConfig
from .cost import load_price_book, price_book_warnings, resolve_models, tiering_errors
from .paths import (
    PLUGIN_SKILL_NAMES,
    detect_decision_dirs,
    git_output,
    is_git_repo,
    plugin_root,
    resolve_skill_source,
)
from .render import projection_necessity_errors, skill_projection_errors
from .util import paint, read_text, status_line

OK = "ok"
WARN = "warn"
FAIL = "fail"


class Check:
    def __init__(
        self,
        status: str,
        label: str,
        detail: str = "",
        remedy: str = "",
        gating: bool = True,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.status = status
        self.label = label
        self.detail = detail
        self.remedy = remedy
        self.gating = gating
        self.data = data or {}


def _minimum_python() -> Check:
    version = "%d.%d.%d" % sys.version_info[:3]
    if sys.version_info < (3, 9):
        return Check(
            FAIL,
            "Python 3.9 or newer",
            "found %s" % version,
            "BEARING's scripts target 3.9 so they run in whatever environment a target "
            "repository already has. Upgrade Python or run the CLI from a newer interpreter.",
        )
    return Check(OK, "Python 3.9 or newer", "found %s" % version)


def _plugin_check() -> Check:
    root = plugin_root()
    if not os.path.isfile(os.path.join(root, "plugin.json")):
        return Check(
            FAIL,
            "plugin resolves",
            "no plugin.json found above %s" % root,
            "Reinstall the CLI from the plugin directory (`pipx install --force ./plugin` "
            "or `uv tool install --force ./plugin`) so plugin.json ships inside the wheel. "
            "A Cursor/Claude plugin install is a different tree and does not satisfy this check.",
        )
    missing = [
        name
        for name in PLUGIN_SKILL_NAMES
        if not os.path.isfile(os.path.join(root, "skills", name, "SKILL.md"))
    ]
    if missing:
        return Check(
            FAIL,
            "plugin resolves",
            "missing skill(s): %s" % ", ".join(missing),
            "The CLI wheel looks incomplete. Reinstall from ./plugin "
            "(`pipx install --force ./plugin` or `uv tool install --force ./plugin`).",
        )
    return Check(OK, "plugin resolves", root)


def _skill_source_check(config: ResolvedConfig) -> List[Check]:
    """Report which copy of the Skills a runtime would actually load.

    A repository's `.agents/skills/` wins over the installed plugin in both Cursor
    and Codex. That makes vendoring a silent shadowing hazard: an old vendored
    copy keeps being used long after the plugin is upgraded, and the symptom is a
    Skill behaving like a version nobody has installed. So it is stated outright
    every time doctor runs, not buried in documentation.
    """
    info = resolve_skill_source(config.workspace)
    declared = config.get("skills.source") or "plugin"
    checks: List[Check] = []

    if info["effective"] == "vendored":
        shadowed = info["shadowed"]
        detail = "%d vendored skill(s) in .agents/skills/ take discovery precedence" % len(
            info["vendored_skills"]
        )
        if declared != "vendored":
            checks.append(
                Check(
                    FAIL,
                    "skill source agrees with config",
                    detail + ", but skills.source is %r" % declared,
                    "Either set skills.source to 'vendored' and record the version with "
                    "`bearing vendor --pin`, or delete .agents/skills/ so the installed "
                    "plugin is used.",
                )
            )
        else:
            checks.append(
                Check(
                    OK,
                    "skill source agrees with config",
                    "vendored, version %s" % (config.get("skills.vendored_version") or "unpinned"),
                )
            )
        if shadowed:
            checks.append(
                Check(
                    WARN,
                    "vendored copies shadow the plugin",
                    ", ".join(shadowed),
                    "This is supported and sometimes correct (air-gapped installs, audit "
                    "reproducibility, CI isolation), but the vendored copy is what actually "
                    "runs. Re-run `bearing vendor` after upgrading the plugin.",
                    gating=False,
                )
            )
    else:
        checks.append(Check(OK, "skill source", "installed plugin (%d skills)" % len(info["plugin_skills"])))
        if declared == "vendored":
            checks.append(
                Check(
                    FAIL,
                    "skill source agrees with config",
                    "skills.source is 'vendored' but no vendored skills were found",
                    "Run `bearing vendor` to create the in-repo copy, or set "
                    "skills.source back to 'plugin'.",
                )
            )
    return checks


def _git_checks(config: ResolvedConfig, require_clean: bool) -> List[Check]:
    checks: List[Check] = []
    if not is_git_repo(config.workspace):
        checks.append(
            Check(
                FAIL,
                "git repository",
                "%s is not a git repository" % config.workspace,
                "Onboarding freezes a baseline tag and works on a branch, both of which need "
                "git. Run `git init` first, or point BEARING at the right directory.",
            )
        )
        return checks

    checks.append(Check(OK, "git repository", config.workspace))

    status = git_output(config.workspace, ["status", "--porcelain"])
    if status is None:
        checks.append(Check(WARN, "working tree state", "could not read git status", gating=False))
    elif status.strip():
        count = len([line for line in status.splitlines() if line.strip()])
        checks.append(
            Check(
                FAIL if require_clean else WARN,
                "working tree is clean",
                "%d uncommitted change(s)" % count,
                "A controlled baseline comparison needs a clean tree. Ordinary onboarding "
                "does not; commit or stash only if you selected that evaluation method.",
                gating=require_clean,
            )
        )
    else:
        checks.append(Check(OK, "working tree is clean"))

    return checks


def _config_checks(config: ResolvedConfig) -> List[Check]:
    checks: List[Check] = []

    if not config.initialized:
        checks.append(
            Check(
                FAIL,
                "workspace is initialized",
                "no .bearing/config.json",
                "Run `bearing init`. It detects the decision-record convention this "
                "repository already uses instead of assuming one.",
            )
        )
    else:
        checks.append(Check(OK, "workspace is initialized", config.sources[LAYER_REPO] or ""))

    for message in config.errors:
        checks.append(Check(FAIL, "config is valid", message, "Fix .bearing/config.json."))
    if not config.errors:
        checks.append(Check(OK, "config is valid"))

    for message in config.warnings:
        checks.append(Check(WARN, "config advisory", message, gating=False))

    layers = []
    for layer in (LAYER_USER, LAYER_REPO, LAYER_LOCAL):
        source = config.sources.get(layer)
        if source:
            layers.append("%s=%s" % (layer, source))
    checks.append(
        Check(
            OK,
            "config layers in effect",
            "; ".join(layers) or "packaged defaults only",
            gating=False,
        )
    )

    return checks


def _decisions_checks(config: ResolvedConfig) -> List[Check]:
    layout = config.layout
    checks: List[Check] = []

    if os.path.isdir(layout.decisions):
        checks.append(Check(OK, "decisions directory", layout.decisions_rel))
    else:
        detected = detect_decision_dirs(config.workspace)
        others = [entry["path"] for entry in detected if entry["path"] != layout.decisions_rel]
        detail = "%s does not exist" % layout.decisions_rel
        remedy = "Run `bearing init` to scaffold it."
        if others:
            detail += "; found %s instead" % ", ".join(others)
            remedy = (
                "This repository appears to keep decisions in %s. Set decisions.path to match "
                "rather than creating a second tree -- institutional memory split across two "
                "directories is worse than either one." % others[0]
            )
        checks.append(Check(FAIL, "decisions directory", detail, remedy))
        return checks

    if os.path.isdir(layout.shadow):
        checks.append(Check(OK, "shadow graph", "%s/%s" % (layout.decisions_rel, layout.shadow_name)))
    else:
        checks.append(
            Check(
                FAIL,
                "shadow graph",
                "missing %s/" % layout.shadow_name,
                "Run `bearing init`. Recovery has nowhere to write candidates without it, and "
                "writing them next to authored records is exactly what the folder boundary "
                "prevents.",
            )
        )

    if os.path.isfile(layout.index):
        checks.append(Check(OK, "disclosure index", layout.index_name))
    else:
        checks.append(
            Check(
                WARN,
                "disclosure index",
                "missing %s" % layout.index_name,
                "Run `bearing index`.",
                gating=False,
            )
        )

    discouraged = layout.decisions_rel.rstrip("/")
    if discouraged in ("docs/adrs", "docs/ADRs", "adrs"):
        checks.append(
            Check(
                WARN,
                "decisions directory naming",
                "%r is the acronym-plural pattern the architecture advises against" % discouraged,
                "This is a warning, never an error. Renaming a legacy decision tree is the "
                "repository owners' call, and forcing it is the adoption friction the "
                "retrospective path exists to avoid. Consider recording the deviation as a "
                "decision record instead.",
                gating=False,
            )
        )

    return checks


def _constitution_check(config: ResolvedConfig) -> Check:
    root_agents = os.path.join(config.workspace, "AGENTS.md")
    nested = os.path.join(config.workspace, ".agents", "AGENTS.md")

    if os.path.isfile(nested) and not os.path.isfile(root_agents):
        return Check(
            FAIL,
            "AGENTS.md is at the repository root",
            "found .agents/AGENTS.md instead",
            "Codex walks from the project root down to the working directory checking "
            "AGENTS.md per directory, so a constitution inside .agents/ is never loaded by "
            "Codex at all. Cursor happens to read it, which is what makes this easy to miss. "
            "Move it to the repository root.",
        )
    if not os.path.isfile(root_agents):
        return Check(
            FAIL,
            "AGENTS.md is at the repository root",
            "missing",
            "Run `bearing render` to create it with the managed BEARING block.",
        )
    text = read_text(root_agents) or ""
    if "BEARING:START" not in text:
        return Check(
            WARN,
            "AGENTS.md carries the BEARING block",
            "present but unmanaged",
            "Run `bearing render`. It inserts a delimited block and never touches anything "
            "outside it.",
            gating=False,
        )
    return Check(OK, "AGENTS.md is at the repository root", "with managed block")


def _writability_checks(config: ResolvedConfig) -> List[Check]:
    """Can each configured projection scope actually be written to?

    Worth checking up front because the failure mode otherwise appears halfway
    through a render, with some adapters written and others not.
    """
    checks: List[Check] = []
    scopes = set()
    for kind in ("subagents", "rules", "contracts"):
        scope = (config.get("projections.%s" % kind) or {}).get("scope") or "repo"
        scopes.add(scope)

    for scope in sorted(scopes):
        if scope == "repo":
            target, label = config.workspace, "workspace"
        elif scope == "user":
            target, label = os.path.expanduser("~"), "home directory"
        else:
            checks.append(
                Check(
                    OK,
                    "projection scope %r writable" % scope,
                    "rendered to a session temp directory; nothing is committed",
                    gating=False,
                )
            )
            continue

        if os.access(target, os.W_OK):
            checks.append(Check(OK, "projection scope %r writable" % scope, "%s: %s" % (label, target)))
        else:
            checks.append(
                Check(
                    FAIL,
                    "projection scope %r writable" % scope,
                    "%s is not writable" % target,
                    "Change the scope for that projection, or fix permissions.",
                )
            )

    return checks


def _plugin_readonly_check() -> Check:
    """Verify the plugin tree is not being written to.

    The purity rule is enforced by test, but a quick runtime signal helps: if the
    plugin directory is writable *and* contains files BEARING is known to write
    elsewhere, something has drifted back to the old layout.
    """
    root = plugin_root()
    strays = []
    for relative in (
        "skills/decision-recovery/references/cost-ledger.jsonl",
        "skills/decision-interview/references/interview-transcripts",
        "skills/decision-recovery/references/gold-set",
        "skills/decision-onboarding/references/pass-fail-criteria.md",
    ):
        if os.path.exists(os.path.join(root, relative)):
            strays.append(relative)
    if strays:
        return Check(
            FAIL,
            "plugin tree holds no runtime data",
            ", ".join(strays),
            "These are written at runtime and plugin directories are replaced wholesale on "
            "update, so anything here is destroyed on the next upgrade. Move them to "
            ".bearing/ or the decisions directory.",
        )
    return Check(OK, "plugin tree holds no runtime data")


def _cost_checks(config: ResolvedConfig) -> List[Check]:
    checks: List[Check] = []
    book = load_price_book(config)
    checks.append(
        Check(
            OK,
            "price book",
            "version %s, %d model(s), age %s day(s)"
            % (book.version, len(book.models), book.age_days() if book.age_days() is not None else "?"),
            gating=False,
        )
    )

    errors = tiering_errors(config, book)
    if errors:
        for message in errors:
            checks.append(
                Check(
                    WARN,
                    "model tier advisory",
                    message,
                    "Model choice and recovery execution are operator-controlled. Confirm the "
                    "assignment or update the price book if cost reporting matters.",
                    gating=False,
                )
            )
    else:
        assignments = ", ".join(
            "%s=%s" % (role, settings["model"]) for role, settings in sorted(resolve_models(config).items())
        )
        checks.append(Check(OK, "model tier advisory", assignments, gating=False))

    for message in price_book_warnings(config, book):
        checks.append(Check(WARN, "price book advisory", message, gating=False))

    if config.get("cost.reviewer_rate_usd_per_hour") is None:
        checks.append(
            Check(
                OK,
                "reviewer rate",
                "unset, so review cost is reported in minutes and never converted to dollars",
                gating=False,
            )
        )

    return checks


def _projection_design_checks(config: ResolvedConfig) -> List[Check]:
    checks: List[Check] = []
    problems = projection_necessity_errors(config) + skill_projection_errors()
    if problems:
        for message in problems:
            checks.append(Check(FAIL, "projection is necessary", message))
    else:
        checks.append(
            Check(OK, "projection is necessary", "every projection bridges a real format gap")
        )
    return checks


def _runtime_compatibility_checks(config: ResolvedConfig) -> List[Check]:
    """Report evidence-backed compatibility without assuming a client accepts us.

    @see ADR-0011
    """
    from .compatibility import COMPATIBILITY_API, runtime_statuses
    from .util import read_json

    checks: List[Check] = []
    root = plugin_root()
    manifest = read_json(os.path.join(root, "plugin.json"), {}) or {}
    summary = read_json(os.path.join(root, "runtime-compatibility.json"), {}) or {}
    plugin_version = manifest.get("version")
    plugin_api = summary.get("bearing_compatibility_api")
    if plugin_api is not None and plugin_api != COMPATIBILITY_API:
        checks.append(
            Check(
                FAIL,
                "CLI/plugin compatibility API",
                "CLI=%s plugin=%s" % (COMPATIBILITY_API, plugin_api),
                "Install CLI and plugin builds with the same compatibility API.",
                data={"cli_api": COMPATIBILITY_API, "plugin_api": plugin_api},
            )
        )
    else:
        status = WARN if plugin_version and plugin_version != __version__ else OK
        checks.append(
            Check(
                status,
                "CLI/plugin compatibility",
                "CLI=%s plugin=%s API=%s" % (__version__, plugin_version or "unknown", COMPATIBILITY_API),
                "Upgrade the older artifact; compatible version skew is advisory."
                if status == WARN else "",
                gating=False if status == WARN else True,
                data={
                    "cli_version": __version__,
                    "plugin_version": plugin_version,
                    "compatibility_api": COMPATIBILITY_API,
                },
            )
        )

    for entry in runtime_statuses(config):
        state = entry["status"]
        checks.append(
            Check(
                OK if state == "verified" else WARN,
                "runtime compatibility: %s" % entry["runtime"],
                "%s; installed=%s; verified=%s; discovery=%s"
                % (
                    state,
                    entry.get("installed_version") or "not detected",
                    entry.get("verified_range") or "none",
                    entry.get("discovery_mode"),
                ),
                "Run Tier 4 conformance for this client version before claiming release support."
                if state != "verified" else "",
                gating=False,
                data=entry,
            )
        )
    return checks


def run_checks(config: ResolvedConfig, require_clean_tree: bool = False) -> List[Check]:
    checks: List[Check] = [_minimum_python(), _plugin_check(), _plugin_readonly_check()]
    checks.extend(_config_checks(config))
    checks.extend(_skill_source_check(config))
    checks.extend(_git_checks(config, require_clean_tree))
    checks.extend(_decisions_checks(config))
    checks.append(_constitution_check(config))
    checks.extend(_writability_checks(config))
    checks.extend(_projection_design_checks(config))
    checks.extend(_runtime_compatibility_checks(config))
    checks.extend(_cost_checks(config))
    return checks


def report(checks: List[Check], title: str) -> int:
    """Print results. Returns a process exit code."""
    print()
    print(paint("%s  (bearing %s)" % (title, __version__), "bold"))
    print()
    for check in checks:
        print(status_line(check.status, check.label, check.detail))
        if check.remedy and check.status in (FAIL, WARN):
            for line in _wrap(check.remedy, 74):
                print("        " + paint(line, "dim"))

    failures = [check for check in checks if check.status == FAIL and check.gating]
    soft = [check for check in checks if check.status == FAIL and not check.gating]
    warnings = [check for check in checks if check.status == WARN]

    print()
    summary = "%d passed, %d warning(s), %d failure(s)" % (
        len([check for check in checks if check.status == OK]),
        len(warnings),
        len(failures) + len(soft),
    )
    if failures:
        print(paint("BLOCKED: " + summary, "fail"))
        print()
        return 1
    print(paint("OK: " + summary, "ok"))
    print()
    return 0


def _wrap(text: str, width: int) -> List[str]:
    import textwrap

    return textwrap.wrap(text, width=width) or [text]


def preflight(config: ResolvedConfig) -> Tuple[bool, List[Check]]:
    """Stricter readiness check for an operator-selected controlled pilot.

    Stricter than `doctor` in one respect -- it requires a clean working tree --
    A clean tree matters when comparing a frozen baseline against a branch. The
    ordinary onboarding guide does not require this check.
    """
    checks = run_checks(config, require_clean_tree=True)
    blocked = any(check.status == FAIL and check.gating for check in checks)
    return (not blocked), checks
