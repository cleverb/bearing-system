"""`bearing init`: bootstrap a workspace without guessing anything about it.

The one decision this command must not get wrong is where decision records live.
`decisions.path` is the key every other path derives from, and a wrong guess
produces a second, empty decision tree beside a repository's real one -- which is
worse than doing nothing, because now institutional memory is split in two.

So detection is presented, never applied silently, and BEARING does not migrate a
legacy directory. It offers to record the deviation as a decision record instead:
the deviation becomes discoverable to the next person who looks in the documented
default location, and BEARING demonstrates the thing it is asking the repository
to adopt.
"""

from __future__ import annotations

import datetime
import os
from typing import Dict, List, Optional, Tuple

from .config import ResolvedConfig, SCHEMA_URL, write_repo_config
from .decisions import build_index, load_records
from .paths import DISCOURAGED_DECISION_DIRS, detect_decision_dirs, template_path
from .util import ensure_dir, read_text, write_json, write_text

_GITIGNORE_MARK = "# --- BEARING run state: never committed ---"


def choose_decisions_path(
    workspace: str,
    explicit: Optional[str],
    assume_yes: bool,
    prompt=input,
) -> Tuple[str, List[str]]:
    """Resolve where decisions live. Returns (path, notes)."""
    notes: List[str] = []
    detected = detect_decision_dirs(workspace)

    if explicit:
        return explicit.strip("/"), notes

    if not detected:
        return "docs/decisions", ["no existing decision-record convention found"]

    if len(detected) == 1 and detected[0]["path"] == "docs/decisions":
        return "docs/decisions", ["found the recommended location already in place"]

    best = detected[0]
    for entry in detected:
        if int(entry["record_count"] or 0) > int(best["record_count"] or 0):
            best = entry

    if assume_yes:
        notes.append(
            "detected %s (%s) and adopted it non-interactively"
            % (best["path"], ", ".join(best["reasons"]))
        )
        return str(best["path"]), notes

    print()
    print("This repository already appears to keep decision records. Detected:")
    for index, entry in enumerate(detected, 1):
        flag = "  [discouraged naming]" if entry["discouraged"] else ""
        print(
            "  %d) %s — %s, %d numbered record(s)%s"
            % (index, entry["path"], ", ".join(entry["reasons"]), entry["record_count"], flag)
        )
    print("  %d) docs/decisions (BEARING default, create new)" % (len(detected) + 1))
    print()
    print("BEARING will not move or rename an existing directory. Whichever you choose")
    print("becomes decisions.path, and every command derives its paths from it.")
    raw = prompt("Which should BEARING use? [1] ").strip()
    choice = int(raw) if raw.isdigit() else 1
    if 1 <= choice <= len(detected):
        selected = str(detected[choice - 1]["path"])
    else:
        selected = "docs/decisions"
    notes.append("operator selected %s" % selected)
    return selected, notes


def scaffold(config: ResolvedConfig, decisions_rel: str) -> Dict[str, List[str]]:
    """Create the directories and seed files. Idempotent by construction."""
    created: List[str] = []
    existing: List[str] = []
    layout = config.layout

    def note(path: str, changed: bool) -> None:
        rel = os.path.relpath(path, config.workspace).replace(os.sep, "/")
        (created if changed else existing).append(rel)

    for directory in (
        layout.bearing,
        layout.ledger_dir,
        layout.runs,
        layout.cache,
        os.path.join(layout.eval_dir, "gold"),
        os.path.join(layout.eval_dir, "dark"),
        os.path.join(layout.eval_dir, "negative"),
        layout.decisions,
        layout.shadow,
        layout.transcripts,
    ):
        before = os.path.isdir(directory)
        ensure_dir(directory)
        note(directory, not before)

    substitutions = {
        "decisions_path": layout.decisions_rel,
        "index_file": layout.index_name,
        "shadow_dir": layout.shadow_name,
        "transcripts_dir": layout.transcripts_name,
        "date": datetime.date.today().isoformat(),
    }

    for template_name, destination in (
        ("decisions-readme.md", os.path.join(layout.decisions, "README.md")),
        ("shadow-readme.md", os.path.join(layout.shadow, "README.md")),
    ):
        if not os.path.isfile(destination):
            note(destination, write_text(destination, _fill(template_name, substitutions)))
        else:
            note(destination, False)

    for path in (layout.candidates, layout.rejected, layout.cost_ledger):
        if not os.path.isfile(path):
            ensure_dir(os.path.dirname(path))
            note(path, write_text(path, ""))
        else:
            note(path, False)

    for name in ("gold", "dark", "negative"):
        cases = os.path.join(layout.eval_dir, name, "cases.jsonl")
        if not os.path.isfile(cases):
            note(cases, write_text(cases, ""))

    if not os.path.isfile(layout.pass_fail):
        note(layout.pass_fail, write_text(layout.pass_fail, _fill("pass-fail-criteria.md", substitutions)))
    else:
        note(layout.pass_fail, False)

    if not os.path.isfile(layout.pricing):
        note(layout.pricing, write_json(layout.pricing, _pricing_stub()))
    else:
        note(layout.pricing, False)

    note(layout.config_file, write_repo_config(layout, dict(config.data, decisions={
        **(config.data.get("decisions") or {}),
        "path": decisions_rel,
    })))

    index_path = layout.index
    if not os.path.isfile(index_path):
        note(index_path, write_json(index_path, build_index(load_records(layout))))
    else:
        note(index_path, False)

    changed = update_gitignore(config)
    note(os.path.join(config.workspace, ".gitignore"), changed)

    return {"created": created, "existing": existing}


def _fill(template_name: str, substitutions: Dict[str, str]) -> str:
    text = read_text(template_path(template_name)) or ""
    for key, value in substitutions.items():
        text = text.replace("{{%s}}" % key, str(value))
    return text


def _pricing_stub() -> Dict[str, object]:
    """An empty overlay, deliberately without a `version`.

    Stamping today's date on a book that contains no prices would claim a
    freshness the underlying figures do not have -- the packaged version is the
    honest answer until this file actually carries an entry. Set `version` when
    you add one.
    """
    return {
        "$comment": (
            "This repository's price book. Merged OVER the packaged defaults per model, so "
            "correcting one price does not require restating the whole book. Every entry "
            "must carry as_of and source: a price with no date is a number nobody can audit, "
            "and BEARING stamps the book version into every cost figure it reports. Add a "
            "`version` here once this file has entries of its own."
        ),
        "models": {},
    }


def update_gitignore(config: ResolvedConfig) -> bool:
    """Add BEARING's ignore entries, appending rather than replacing.

    Deliberately not managed as a rewritable delimited block. A `.gitignore` is
    edited constantly by everyone on a team, and a tool that rewrites a region of
    it will eventually eat somebody's entry.
    """
    path = os.path.join(config.workspace, ".gitignore")
    existing = read_text(path) or ""
    if _GITIGNORE_MARK in existing:
        return False

    layout = config.layout
    transcripts_local = ""
    if layout.transcript_retention == "local":
        transcripts_local = "%s/%s/%s/local/" % (
            layout.decisions_rel,
            layout.shadow_name,
            layout.transcripts_name,
        )
    block = _fill("gitignore-block.txt", {"transcripts_local": transcripts_local})
    block = "\n".join(line for line in block.split("\n") if line.strip() or line == "")
    separator = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return write_text(path, "%s%s%s" % (existing, separator, block))


def deviation_record(config: ResolvedConfig) -> Optional[str]:
    """Draft a decision record explaining a non-default decisions location.

    Offered, never written automatically -- a repository's decision corpus is not
    somewhere a tool gets to add records on its own initiative.
    """
    layout = config.layout
    if layout.decisions_rel.rstrip("/") == "docs/decisions":
        return None
    records = load_records(layout)
    next_number = max([record.number or 0 for record in records] + [0]) + 1
    return _fill(
        "deviation-adr.md",
        {
            "number": "%04d" % next_number,
            "decisions_path": layout.decisions_rel,
            "date": datetime.date.today().isoformat(),
        },
    )


def deviation_warning(decisions_rel: str) -> Optional[str]:
    if decisions_rel.rstrip("/") in DISCOURAGED_DECISION_DIRS:
        return (
            "%r uses the acronym-plural pattern the architecture advises against. This is a "
            "warning, not an error: renaming a legacy decision tree is the repository owners' "
            "call, and forcing it is exactly the adoption friction the retrospective path "
            "exists to avoid." % decisions_rel
        )
    return None
