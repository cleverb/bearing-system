"""`bearing report`: cost and outcome reporting, with two refusals built in.

@see ADR-0005 — reporting refusals are code, not a documentation plea.

**Refusal one: token counts are not printed alone.** The onboarding spec lists
this as a Success Criterion, and a criterion that depends on someone remembering
it will be violated the first time somebody just wants the token number. So the
command fails instead.

The reasoning is not pedantry. The BEARING run is *expected* to consume more
tokens than the baseline, because it now loads a constitution, a disclosure index,
and Contract summaries the baseline never had. Higher token use with lower rework
and fewer Contract violations is the framework working exactly as designed. A
token delta reported without those numbers beside it is not a weak signal, it is
an actively misleading one -- it looks like a cost regression and reads as
authoritative.

**Refusal two: engineer time is not silently priced.** Review minutes convert to
dollars only when someone supplies a rate. Everything else in a cost report is at
least traceable to a published price; a fabricated hourly figure for a senior
engineer's attention would put the least defensible number in the most prominent
position.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .config import ResolvedConfig
from .cost import (
    CAVEAT_BLOCK,
    acceptance_stats,
    cost_per_promoted,
    kill_switch_triggered,
    load_ledger,
    load_price_book,
    model_cost,
    price_book_warnings,
    require_paired_metrics,
    review_cost,
)
from .util import BearingError


def cost_report(config: ResolvedConfig, include_tokens: bool = True) -> str:
    book = load_price_book(config)
    rows = load_ledger(config)

    if not rows:
        return (
            "# BEARING cost report\n\n"
            "No rows in `%s`. Nothing has been measured yet, and this report deliberately does "
            "not estimate what a run *would* cost -- a projection with no measurement behind it "
            "is a guess wearing a report's formatting.\n"
            % os.path.relpath(config.layout.cost_ledger, config.workspace)
        )

    lines: List[str] = ["# BEARING cost report", ""]
    lines.append("Price book **%s**, sourced from %s." % (book.version, ", ".join(
        os.path.relpath(path, config.workspace) if path.startswith(config.workspace) else os.path.basename(path)
        for path in book.sources
    )))

    warnings = price_book_warnings(config, book)
    if warnings:
        lines.append("")
        lines.append("> **Price book warnings** — every figure below inherits these:")
        for warning in warnings:
            lines.append("> - %s" % warning)

    lines.append("")
    lines.append("## Model cost")
    lines.append("")
    model_range, notes = model_cost(config, book, rows)
    if model_range is None:
        lines.append("No priced model rows in the ledger.")
    else:
        lines.append("- **Total:** %s" % model_range.render())
        if model_range.estimated:
            lines.append(
                "- The range reflects token-count uncertainty on estimated rows, not price "
                "uncertainty. Price uncertainty is unbounded and not modelled — see the caveats."
            )
    for note in notes:
        lines.append("- %s" % note)

    lines.append("")
    lines.append("## Review cost")
    lines.append("")
    review = review_cost(config, rows)
    lines.append("- **Total:** %s" % review.render())
    lines.append(
        "- Review time, not tokens, is the dominant cost of this system. It is listed second "
        "because it is larger, not because it is secondary."
    )

    stats = acceptance_stats(rows)
    lines.append("")
    lines.append("## Throughput")
    lines.append("")
    lines.append("- Candidates reviewed: %d" % stats["candidates_reviewed"])
    lines.append("- Candidates promoted: %d" % stats["candidates_promoted"])
    if stats["acceptance_rate"] is not None:
        lines.append(
            "- Acceptance rate: %.0f%% — context only. A repository producing 100 trivial "
            "candidates at 30%% and one producing 5 candidates at 20%% where the single hit is "
            "an undocumented security constraint are not the same system, and a rate cannot "
            "tell them apart." % (stats["acceptance_rate"] * 100)
        )

    per_promoted = cost_per_promoted(config, book, rows)
    if per_promoted is None:
        lines.append(
            "- Cost per promoted candidate: **not computed.** This metric exists to put the "
            "dominant cost — review time — into the number that decides whether the Skill keeps "
            "running. Computing it from tokens alone would report the small half and call it the "
            "whole. Set `cost.reviewer_rate_usd_per_hour` to enable it."
        )
    else:
        lines.append("- Cost per promoted candidate: $%.2f" % per_promoted)

    triggered, reason = kill_switch_triggered(config, book, rows)
    lines.append("")
    lines.append("## Kill switch")
    lines.append("")
    lines.append("- **%s** — %s" % ("TRIGGERED" if triggered else "not triggered", reason))

    if include_tokens:
        gate = require_paired_metrics(rows)
        lines.append("")
        lines.append("## Token consumption")
        lines.append("")
        if gate:
            lines.append(
                "**Withheld.** Token figures are only reported alongside rework, "
                "Contract-violation, and escalation-correctness metrics. Missing:"
            )
            for message in gate:
                lines.append("- %s" % message)
            lines.append("")
            lines.append(
                "This is a refusal, not a formatting choice. See the reasoning in the caveats "
                "below: the BEARING run is expected to use more tokens, and that number without "
                "outcome metrics beside it reads as a cost regression when it may be the "
                "opposite."
            )
        else:
            lines.extend(_token_table(rows))

    lines.append("")
    lines.append(CAVEAT_BLOCK)
    lines.append("")
    lines.append("_Generated by bearing %s._" % __version__)
    return "\n".join(lines) + "\n"


def _token_table(rows: List[Dict[str, Any]]) -> List[str]:
    lines = [
        "| condition | input | output | source | rework | contract violations | escalation correct |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        if row.get("stage") != "pilot":
            continue
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s |"
            % (
                row.get("condition", "?"),
                row.get("input_tokens", "-"),
                row.get("output_tokens", "-"),
                row.get("token_source", "estimated"),
                row.get("rework_count", "-"),
                row.get("contract_violations", "-"),
                row.get("escalation_correct", "-"),
            )
        )
    lines.append("")
    lines.append(
        "The row that matters is the **paired delta** between the baseline and BEARING "
        "conditions on the same tickets. Pricing and estimation error is largely common-mode: "
        "it mostly cancels in a difference and does not cancel at all in a total."
    )
    return lines


def pilot_report(config: ResolvedConfig) -> Tuple[str, int]:
    """Pilot outcome against the pre-registered bar. Returns (text, exit code)."""
    from .profiles import pre_registration_errors

    errors = pre_registration_errors(config)
    lines: List[str] = ["# BEARING pilot report", ""]

    if errors:
        lines.append("## Pre-registration check: FAILED")
        lines.append("")
        for message in errors:
            lines.append("- %s" % message)
        lines.append("")
        lines.append(
            "The pass/fail bar is pre-registered before Step 5 runs, and this check is the only "
            "real defense against a threshold that moves to fit the results. It matters more "
            "after a large recovery investment, not less."
        )
        lines.append("")
        lines.append(cost_report(config, include_tokens=False))
        return "\n".join(lines) + "\n", 1

    lines.append("## Pre-registration check: passed")
    lines.append("")
    lines.append(
        "`%s` was in place before the first pilot run."
        % os.path.relpath(config.layout.pass_fail, config.workspace)
    )
    lines.append("")
    lines.append(cost_report(config, include_tokens=True))
    return "\n".join(lines) + "\n", 0
