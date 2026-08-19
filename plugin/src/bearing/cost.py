"""Cost: the price book, the tiering Contract, and what BEARING refuses to claim.

Three positions this module exists to hold.

**A price is a dated fact, not a constant.** Every price book entry carries
`as_of` and a source, every figure BEARING reports names the price book version
it used, and a stale book produces a warning stamped into the report rather than
a silent number that looks as authoritative as a fresh one.

**Configuration must not be able to void a Contract.** Model choice per pipeline
role is an operator decision, but the Model Tiering Contract says extraction MUST
use the cheap tier. So the choice is free and the Contract is enforced: a config
that puts a frontier model on extraction fails `bearing doctor`. This is the
documented-to-machine-verifiable ladder applied to BEARING's own configuration.

**Review time is the dominant cost and the least knowable.** So it is reported in
minutes, and converted to dollars only when someone supplies a rate. Inventing an
hourly figure for a senior engineer's attention would make the total look precise
in exactly the place it is least defensible.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Tuple

from .config import ResolvedConfig
from .paths import data_dir
from .util import BearingError, read_json, read_jsonl

PIPELINE_ROLES = ("extract", "resolve", "score", "interview")

# The Model Tiering Contract, as a machine-checkable rule rather than prose.
# Extraction is the only stage that runs over the *whole* corpus, so it is the
# only one where model choice changes cost by orders of magnitude.
TIER_CONTRACT = {
    "extract": ("cheap",),
    "resolve": ("cheap", "mid", "frontier"),
    "score": ("cheap", "mid", "frontier"),
    "interview": ("cheap", "mid", "frontier"),
}

TIER_ORDER = {"cheap": 0, "mid": 1, "frontier": 2}

CAVEAT_BLOCK = """\
## How to read these numbers

- **Token counts** are measured where the host agent reports them and estimated
  from content length otherwise. Every figure is marked `measured` or
  `estimated`; an estimated figure carries a range, not a point value.
- **Dollar figures** come from a dated price book of published list prices. They
  ignore prompt caching, batch discounts, committed-use pricing, and any
  negotiated rate, all of which move real spend materially.
- **The number that carries signal is the paired delta** between the baseline run
  and the BEARING run on the same ticket under the same price book. Pricing error
  is largely common-mode: it mostly cancels in a difference and does not cancel
  at all in an absolute total.
- **Therefore:** absolute totals are order-of-magnitude budgeting only and should
  not be quoted as forecasts. Relative deltas are the deliverable.
- **Review time is reported in minutes** unless a reviewer rate is configured.
  Review time, not tokens, is the dominant cost of this system.
- **A token delta on its own is not interpretable in either direction.** The
  BEARING run is expected to use more tokens, because it loads a constitution, a
  disclosure index, and Contract summaries the baseline never had. More tokens
  with less rework is the framework working. That is why token figures are
  reported only alongside rework, Contract-violation, and escalation metrics.
"""


class PriceBook:
    def __init__(self, data: Dict[str, Any], sources: List[str]) -> None:
        self.data = data
        self.sources = sources
        self.version = str(data.get("version", "unknown"))
        self.models: Dict[str, Dict[str, Any]] = data.get("models") or {}

    def entry(self, model: str) -> Optional[Dict[str, Any]]:
        return self.models.get(model)

    def tier(self, model: str) -> Optional[str]:
        entry = self.entry(model)
        return entry.get("tier") if entry else None

    def is_priced(self, model: str) -> bool:
        entry = self.entry(model)
        return bool(entry and entry.get("input") is not None and entry.get("output") is not None)

    def oldest_as_of(self) -> Optional[datetime.date]:
        dates = []
        for entry in self.models.values():
            parsed = _parse_date(entry.get("as_of"))
            if parsed:
                dates.append(parsed)
        return min(dates) if dates else None

    def age_days(self, today: Optional[datetime.date] = None) -> Optional[int]:
        oldest = self.oldest_as_of()
        if oldest is None:
            return None
        today = today or datetime.date.today()
        return (today - oldest).days

    def cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
        entry = self.entry(model)
        if not entry or entry.get("input") is None or entry.get("output") is None:
            return None
        million = 1_000_000.0
        return (input_tokens / million) * float(entry["input"]) + (
            output_tokens / million
        ) * float(entry["output"])


def _parse_date(value: Any) -> Optional[datetime.date]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def load_price_book(config: ResolvedConfig) -> PriceBook:
    """Packaged defaults, overlaid by the repository's own book.

    Merged per model rather than wholesale, so a repository can correct one
    price without restating the entire book and silently losing the rest.
    """
    packaged_path = os.path.join(data_dir(), "pricing.default.json")
    packaged = read_json(packaged_path) or {}
    sources = [packaged_path]

    merged: Dict[str, Any] = {
        "version": packaged.get("version", "unknown"),
        "currency": packaged.get("currency", "USD"),
        "unit": packaged.get("unit", "per_million_tokens"),
        "models": dict(packaged.get("models") or {}),
    }

    repo_path = config.layout.pricing
    repo_book = read_json(repo_path)
    if repo_book:
        sources.append(repo_path)
        if repo_book.get("version"):
            merged["version"] = repo_book["version"]
        for model, entry in (repo_book.get("models") or {}).items():
            base = dict(merged["models"].get(model) or {})
            base.update(entry)
            merged["models"][model] = base

    return PriceBook(merged, sources)


def resolve_models(config: ResolvedConfig) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for role in PIPELINE_ROLES:
        settings = config.get("models.%s" % role) or {}
        out[role] = {
            "model": settings.get("model") or "inherit",
            "declared_tier": settings.get("tier"),
        }
    return out


def tiering_errors(config: ResolvedConfig, book: PriceBook) -> List[str]:
    """Enforce the Model Tiering Contract against the resolved config.

    Two distinct failures are reported, because they have different causes:
    a model the price book has never heard of (so its tier is unknowable), and a
    model whose tier is known and disallowed for that role.
    """
    errors: List[str] = []
    for role, settings in resolve_models(config).items():
        model = settings["model"]
        declared = settings["declared_tier"]
        actual = book.tier(model)
        allowed = TIER_CONTRACT.get(role, ("cheap", "mid", "frontier"))

        if actual is None:
            errors.append(
                "models.%s.model is %r, which the price book does not list. Its tier cannot be "
                "verified against the Model Tiering Contract, and its cost cannot be estimated. "
                "Add it to .bearing/pricing.json with a tier, as_of date, and source."
                % (role, model)
            )
            continue

        if declared and declared != actual:
            errors.append(
                "models.%s declares tier %r but the price book lists %r as %r. The price book "
                "is authoritative for tier; fix the config rather than the book."
                % (role, declared, model, actual)
            )

        if actual not in allowed:
            errors.append(
                "models.%s.model is %r (tier %r), but the Model Tiering Contract permits only "
                "%s for this role. Extraction runs over the entire scoped corpus, so this is "
                "the one place model choice changes cost by orders of magnitude -- which is why "
                "configuration is not permitted to override it."
                % (role, model, actual, " or ".join(repr(t) for t in allowed))
            )

    return errors


def price_book_warnings(config: ResolvedConfig, book: PriceBook) -> List[str]:
    warnings: List[str] = []
    max_age = config.get("cost.price_book_max_age_days") or 90
    age = book.age_days()
    if age is None:
        warnings.append(
            "price book has no usable `as_of` dates, so its staleness cannot be assessed"
        )
    elif age > max_age:
        warnings.append(
            "price book is %d days old (limit %d). Cost figures derived from it are reported "
            "as stale; refresh .bearing/pricing.json." % (age, max_age)
        )
    for model, entry in sorted(book.models.items()):
        if entry.get("input") is None and not entry.get("unpriced_reason"):
            warnings.append(
                "price book entry %r has no price and no `unpriced_reason`" % model
            )
    return warnings


class CostRange:
    """A cost with explicit uncertainty, and an explicit provenance."""

    def __init__(self, low: float, expected: float, high: float, estimated: bool) -> None:
        self.low = low
        self.expected = expected
        self.high = high
        self.estimated = estimated

    def as_dict(self) -> Dict[str, Any]:
        return {
            "low_usd": round(self.low, 4),
            "expected_usd": round(self.expected, 4),
            "high_usd": round(self.high, 4),
            "token_source": "estimated" if self.estimated else "measured",
        }

    def render(self) -> str:
        if self.estimated:
            return "$%.2f (est. $%.2f-$%.2f)" % (self.expected, self.low, self.high)
        return "$%.2f (measured)" % self.expected


def model_cost(
    config: ResolvedConfig, book: PriceBook, rows: List[Dict[str, Any]]
) -> Tuple[Optional[CostRange], List[str]]:
    """Total model cost across ledger rows, with a range when any row is estimated.

    A measured row contributes no uncertainty. An estimated row widens the band by
    the configured fraction. Mixing the two is normal -- the host reports tokens
    for some calls and not others -- and the result is marked estimated if any
    contributing row was, because a total is only as measured as its weakest term.
    """
    uncertainty = float(config.get("cost.token_estimate_uncertainty") or 0.25)
    notes: List[str] = []
    expected = 0.0
    low = 0.0
    high = 0.0
    any_estimated = False
    priced_rows = 0

    for row in rows:
        model = row.get("model")
        if not model or row.get("stage") == "review":
            continue
        input_tokens = int(row.get("input_tokens") or 0)
        output_tokens = int(row.get("output_tokens") or 0)
        cost = book.cost_usd(str(model), input_tokens, output_tokens)
        if cost is None:
            entry = book.entry(str(model))
            reason = (entry or {}).get("unpriced_reason") or "not in the price book"
            notes.append(
                "run %s stage %s used %r, which is unpriced (%s); its cost is excluded from the "
                "total rather than guessed at"
                % (row.get("run_id", "?"), row.get("stage", "?"), model, reason)
            )
            continue
        priced_rows += 1
        estimated = str(row.get("token_source", "estimated")).lower() != "measured"
        any_estimated = any_estimated or estimated
        expected += cost
        if estimated:
            low += cost * (1.0 - uncertainty)
            high += cost * (1.0 + uncertainty)
        else:
            low += cost
            high += cost

    if priced_rows == 0:
        return None, notes
    return CostRange(low, expected, high, any_estimated), notes


class ReviewCost:
    """Review effort. Minutes always; dollars only when a rate exists."""

    def __init__(self, minutes: float, rate_usd_per_hour: Optional[float]) -> None:
        self.minutes = minutes
        self.rate = rate_usd_per_hour

    @property
    def usd(self) -> Optional[float]:
        if self.rate is None:
            return None
        return (self.minutes / 60.0) * self.rate

    def render(self) -> str:
        if self.rate is None:
            return (
                "%.0f min (no reviewer rate configured, so this is deliberately not "
                "converted to dollars)" % self.minutes
            )
        return "%.0f min = $%.2f at $%.2f/hr" % (self.minutes, self.usd or 0.0, self.rate)


def review_cost(config: ResolvedConfig, rows: List[Dict[str, Any]]) -> ReviewCost:
    minutes = 0.0
    for row in rows:
        if row.get("stage") == "review":
            minutes += float(row.get("estimated_review_minutes") or 0)
        elif row.get("interview_duration_minutes"):
            minutes += float(row["interview_duration_minutes"])
    rate = config.get("cost.reviewer_rate_usd_per_hour")
    return ReviewCost(minutes, float(rate) if rate is not None else None)


def load_ledger(config: ResolvedConfig) -> List[Dict[str, Any]]:
    return [row for row in read_jsonl(config.layout.cost_ledger) if isinstance(row, dict)]


def acceptance_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    reviewed = sum(int(row.get("candidates_reviewed") or 0) for row in rows)
    promoted = sum(int(row.get("candidates_promoted") or 0) for row in rows)
    return {
        "candidates_reviewed": reviewed,
        "candidates_promoted": promoted,
        "acceptance_rate": (promoted / reviewed) if reviewed else None,
    }


def cost_per_promoted(
    config: ResolvedConfig, book: PriceBook, rows: List[Dict[str, Any]]
) -> Optional[float]:
    """Model cost plus valued review time, per promoted candidate.

    Returns None when no reviewer rate is configured. That is intentional: this
    metric's entire purpose is to make the dominant cost -- review time, not
    tokens -- visible in the number that decides whether the Skill keeps running.
    Computing it from tokens alone would report the small half and call it the
    whole, which is more misleading than reporting nothing.
    """
    stats = acceptance_stats(rows)
    promoted = stats["candidates_promoted"]
    if not promoted:
        return None
    review = review_cost(config, rows)
    if review.usd is None:
        return None
    model_range, _ = model_cost(config, book, rows)
    model_total = model_range.expected if model_range else 0.0
    return (model_total + review.usd) / promoted


def kill_switch_triggered(
    config: ResolvedConfig, book: PriceBook, rows: List[Dict[str, Any]]
) -> Tuple[bool, str]:
    """Fires on a sustained rise in cost per promoted candidate.

    Not on acceptance rate. A repository producing 100 trivial candidates at 30%
    acceptance and one producing 5 candidates at 20% acceptance where the single
    hit is an undocumented security constraint are not the same kind of system,
    and a rate alone cannot tell them apart.
    """
    window = int(config.get("verify.cost_per_promoted_trailing_window") or 4)
    by_run: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        run_id = str(row.get("run_id") or "")
        if run_id:
            by_run.setdefault(run_id, []).append(row)

    series: List[Tuple[str, float]] = []
    for run_id in sorted(by_run):
        value = cost_per_promoted(config, book, by_run[run_id])
        if value is not None:
            series.append((run_id, value))

    if len(series) < window:
        return False, (
            "not enough history: %d run(s) with a computable cost per promoted candidate, "
            "need %d" % (len(series), window)
        )

    recent = series[-window:]
    rising = all(recent[i][1] < recent[i + 1][1] for i in range(len(recent) - 1))
    if rising:
        return True, "cost per promoted candidate rose in each of the last %d runs (%s)" % (
            window,
            " -> ".join("$%.2f" % value for _, value in recent),
        )
    return False, "cost per promoted candidate is not monotonically rising over the last %d runs" % window


def require_paired_metrics(rows: List[Dict[str, Any]]) -> List[str]:
    """The token-reporting gate.

    `bearing report` will not print token figures without rework,
    Contract-violation, and escalation-correctness metrics beside them. The
    onboarding spec already lists this as a Success Criterion; making it a
    refusal rather than a guideline is what stops it eroding the first time
    somebody is in a hurry and just wants the token number.
    """
    required = ("rework_count", "contract_violations", "escalation_correct")
    pilot_rows = [row for row in rows if row.get("stage") == "pilot"]
    if not pilot_rows:
        return ["no pilot rows in the ledger, so there is nothing to pair token counts with"]

    missing: List[str] = []
    for row in pilot_rows:
        absent = [field for field in required if row.get(field) is None]
        if absent:
            missing.append(
                "pilot row %s/%s is missing %s"
                % (row.get("run_id", "?"), row.get("condition", "?"), ", ".join(absent))
            )
    return missing
