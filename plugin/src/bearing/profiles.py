"""Optional onboarding planning presets.

@see ADR-0008 — profiles do not select or run recovery infrastructure.

"Should I run full recovery before evaluating?" is a real question with no single
right answer, so it becomes a named profile rather than a flag buried in prose.

- **pilot** -- suggests one scope and a small number of anchors.
- **thorough** -- offers multi-scope recovery and review-wave planning.
- **audit** -- suggests recovery without promotion.

What `thorough` relaxes: the anchor cap, and the single-scope restriction.

The helpers below can warn about review load, scope, and measurement quality.
They support an operator-selected formal evaluation; they are not universal
adoption gates. The human authority boundary remains non-negotiable.

- **The human authority boundary.** Unchanged and not negotiable. More candidates
  is not an argument for reviewing them less carefully.
- **Evaluation quality.** Pre-registration, review waves, matched scope, and a
  frozen baseline are available when a team selects a controlled pilot. The
  helpers report problems with those controls without defining ordinary
  onboarding success.
"""

from __future__ import annotations

import datetime
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from .config import ResolvedConfig
from .decisions import load_candidates, surfaced_candidates
from .util import BearingError, read_json, read_jsonl, read_text, write_json

PILOT = "pilot"
THOROUGH = "thorough"
AUDIT = "audit"
PROFILES = (PILOT, THOROUGH, AUDIT)

_SPEC: Dict[str, Dict[str, Any]] = {
    PILOT: {
        "max_scopes": 1,
        "max_promotions": 5,
        "creates_branch": True,
        "runs_pilot": True,
        "allows_promotion": True,
        "requires_review_budget": False,
        "summary": "Suggested small trial: one scope and a few anchors.",
    },
    THOROUGH: {
        "max_scopes": None,
        "max_promotions": None,
        "creates_branch": True,
        "runs_pilot": True,
        "allows_promotion": True,
        "requires_review_budget": True,
        "summary": "Optional multi-scope planning with review-capacity estimates.",
    },
    AUDIT: {
        "max_scopes": None,
        "max_promotions": 0,
        "creates_branch": False,
        "runs_pilot": False,
        "allows_promotion": False,
        "requires_review_budget": False,
        "summary": "Recovery-only evaluation with no promotion implied.",
    },
}


class Profile:
    def __init__(self, name: str, config: ResolvedConfig) -> None:
        if name not in PROFILES:
            raise BearingError(
                "unknown profile %r; choose one of %s" % (name, ", ".join(PROFILES))
            )
        self.name = name
        self.config = config
        self.spec = _SPEC[name]

    def __getattr__(self, item: str) -> Any:
        spec = self.__dict__.get("spec") or {}
        if item in spec:
            return spec[item]
        raise AttributeError(item)

    @property
    def review_budget_minutes(self) -> int:
        return int(self.config.get("review.budget_minutes_per_session") or 90)

    @property
    def wave_size(self) -> int:
        """Candidates per wave, capped by what the declared budget can absorb.

        Two independent limits, and the tighter one wins: an explicit wave size,
        and the number a reviewer can actually get through in the declared time.
        Configuring a wave of 200 with a 90-minute budget is a contradiction, and
        resolving it silently in favour of the larger number is how review
        becomes rubber-stamping.
        """
        configured = int(self.config.get("review.wave_size") or 25)
        seconds = int(self.config.get("review.seconds_per_candidate_estimate") or 85)
        affordable = max(1, int((self.review_budget_minutes * 60) // max(seconds, 1)))
        return min(configured, affordable)

    def readiness_errors(self) -> List[str]:
        errors: List[str] = []
        if self.spec["requires_review_budget"]:
            budget = self.config.get("review.budget_minutes_per_session")
            if not budget:
                errors.append(
                    "profile 'thorough' works best with review.budget_minutes_per_session set. "
                    "Without it, wave estimates use the default review budget."
                )
        return errors

    def promotion_errors(self, promoted_count: int) -> List[str]:
        limit = self.spec["max_promotions"]
        if limit is None:
            return []
        if promoted_count > limit:
            if limit == 0:
                return [
                    "profile 'audit' promotes nothing by design; %d promotion(s) fall outside "
                    "that preset. The operator may choose another profile or workflow."
                    % promoted_count
                ]
            return [
                "profile %r suggests at most %d promotions (%d attempted). Confirm a larger "
                "scope or choose another workflow if it is intentional."
                % (self.name, limit, promoted_count)
            ]
        return []

    def scope_errors(self, scopes: List[str]) -> List[str]:
        limit = self.spec["max_scopes"]
        if limit is not None and len(scopes) > limit:
            return [
                "profile %r suggests %d recovery scope(s), %d given. Confirm the broader scope "
                "or choose another workflow if it is intentional."
                % (self.name, limit, len(scopes))
            ]
        return []


def plan_waves(profile: Profile, candidate_count: int) -> List[Dict[str, int]]:
    """Split a candidate count into reviewable waves."""
    size = profile.wave_size
    if candidate_count <= 0:
        return []
    total = int(math.ceil(candidate_count / float(size)))
    waves = []
    remaining = candidate_count
    for index in range(total):
        this_wave = min(size, remaining)
        waves.append(
            {
                "wave": index + 1,
                "candidates": this_wave,
                "estimated_review_minutes": int(
                    this_wave
                    * int(profile.config.get("review.seconds_per_candidate_estimate") or 85)
                    / 60
                ),
            }
        )
        remaining -= this_wave
    return waves


def wave_gate(profile: Profile, config: ResolvedConfig) -> Tuple[bool, str]:
    """May the next wave be generated?

    Only when the current one is fully cleared. Generating wave two while wave one
    is half-reviewed is how a review queue becomes a backlog nobody re-enters.
    """
    candidates = load_candidates(config.layout)
    outstanding = [
        candidate
        for candidate in surfaced_candidates(candidates)
        if candidate.get("lifecycle_state") == "Reviewable"
    ]
    if not outstanding:
        return True, "no outstanding Reviewable candidates; the next wave may be generated"
    return False, (
        "%d Reviewable candidate(s) still outstanding. Each wave is fully reviewed before the "
        "next is generated -- that is what preserves reviewability without capping total "
        "coverage." % len(outstanding)
    )


def pre_registration_errors(config: ResolvedConfig) -> List[str]:
    """Advisories for teams that selected a pre-registered comparison.

    Checked by comparing the criteria file's modification time against the first
    pilot row in the ledger. Not a perfect proof -- a determined person can touch
    a file -- but it catches the realistic case, which is not fraud. It is someone
    who genuinely believes the threshold was wrong now that they have seen the
    data. The caller decides whether this matters for the selected evaluation.
    """
    layout = config.layout
    errors: List[str] = []

    if not os.path.isfile(layout.pass_fail):
        return [
            "no %s. A controlled, pre-registered comparison should define its bar before "
            "collecting results." % os.path.relpath(layout.pass_fail, config.workspace)
        ]

    text = read_text(layout.pass_fail) or ""
    if "<measure on baseline first>" in text or "<fill in" in text:
        errors.append(
            "%s still contains template placeholders, so no comparison bar has been set."
            % os.path.relpath(layout.pass_fail, config.workspace)
        )

    rows = [row for row in read_jsonl(layout.cost_ledger) if isinstance(row, dict)]
    pilot_rows = [row for row in rows if row.get("stage") == "pilot" and row.get("recorded_at")]
    if not pilot_rows:
        return errors

    first = min(str(row["recorded_at"]) for row in pilot_rows)
    first_date = _parse_iso(first)
    if first_date is None:
        return errors

    criteria_mtime = datetime.datetime.utcfromtimestamp(os.path.getmtime(layout.pass_fail))
    if criteria_mtime > first_date + datetime.timedelta(minutes=5):
        errors.append(
            "%s was modified at %s, after the first pilot run at %s. This weakens a "
            "pre-registered comparison; label the result accordingly."
            % (
                os.path.relpath(layout.pass_fail, config.workspace),
                criteria_mtime.isoformat(timespec="seconds"),
                first_date.isoformat(timespec="seconds"),
            )
        )

    return errors


def _parse_iso(value: str) -> Optional[datetime.datetime]:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def state_path(config: ResolvedConfig) -> str:
    return os.path.join(config.layout.runs, "onboarding.json")


def load_state(config: ResolvedConfig) -> Dict[str, Any]:
    return read_json(state_path(config), {}) or {}


def save_state(config: ResolvedConfig, state: Dict[str, Any]) -> None:
    write_json(state_path(config), state)


def describe(profile_name: str) -> str:
    return _SPEC[profile_name]["summary"]


def scope_ticket_overlap_warning(scopes: List[str], ticket_paths: List[str]) -> Optional[str]:
    """The most common way onboarding produces a misleading null result.

    If the recovery scope and the files the evaluation tickets touch do not
    intersect, the pilot measures a BEARING run that had no recovered knowledge
    available to it, and reports "no improvement" for a reason that has nothing to
    do with the framework.
    """
    from .util import match_any

    if not scopes or not ticket_paths:
        return None
    overlapping = [path for path in ticket_paths if match_any(path, scopes)]
    if overlapping:
        return None
    return (
        "none of the %d selected test-ticket path(s) fall inside the recovery scope %s. The "
        "pilot would measure a BEARING run with no recovered knowledge bearing on the work, "
        "and report a null result for a reason unrelated to the framework. Re-select tickets "
        "or widen the scope before interpreting the comparison." % (len(ticket_paths), ", ".join(scopes))
    )
