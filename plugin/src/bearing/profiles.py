"""Onboarding profiles.

"Should I run full recovery before evaluating?" is a real question with no single
right answer, so it becomes a named profile rather than a flag buried in prose.

- **pilot** -- one scope, three to five anchors. Proves the loop closes fast.
- **thorough** -- multi-scope recovery in reviewed waves. Coverage bounded by
  declared review capacity rather than a fixed anchor count.
- **audit** -- recovery only. No promotion, no branch, no pilot. Produces a
  coverage and cost report so the decision to invest in `thorough` is made on
  measurement instead of optimism. This is the honest answer to "do I have time
  for this": measure first.

What `thorough` relaxes: the anchor cap, and the single-scope restriction.

What it does not relax, and why each one matters *more* rather than less at
larger scale:

- **The human authority boundary.** Unchanged and not negotiable. More candidates
  is not an argument for reviewing them less carefully.
- **Pre-registration of the pass/fail bar.** After two weeks of recovery
  investment, whoever ran it is strongly motivated to find a threshold the
  results happen to clear. Pre-registration is the only real defense, and it is
  enforced here by comparing file mtimes rather than trusted.
- **Wave-bounded review.** Recovery generates in waves, each fully reviewed
  before the next is produced. This is what preserves "a human can review
  everything the pass produces" without capping total coverage -- which is what
  the scoped-recovery discipline was actually protecting. The original spec
  conflated the two, and separating them is what makes `thorough` safe.
- **Scope and test-ticket coordination.** Still required. Broad recovery makes it
  easier, and that is the real evaluation benefit of `thorough`: it addresses the
  null-result risk that pilot mode explicitly worries about, where the tickets
  chosen for evaluation turn out not to touch the recovered area at all.
- **The frozen baseline.** Same tag. The report notes elapsed wall-clock time, so
  drift between the baseline and a weeks-later comparison is visible instead of
  invisible.
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
        "summary": "One scope, 3-5 anchors, fastest path to a closed loop.",
    },
    THOROUGH: {
        "max_scopes": None,
        "max_promotions": None,
        "creates_branch": True,
        "runs_pilot": True,
        "allows_promotion": True,
        "requires_review_budget": True,
        "summary": "Multi-scope recovery in reviewed waves, bounded by declared review capacity.",
    },
    AUDIT: {
        "max_scopes": None,
        "max_promotions": 0,
        "creates_branch": False,
        "runs_pilot": False,
        "allows_promotion": False,
        "requires_review_budget": False,
        "summary": "Recovery only. Measures coverage and cost so the decision to invest is informed.",
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
                    "profile 'thorough' requires review.budget_minutes_per_session to be set. "
                    "Coverage in this profile is bounded by review capacity rather than a fixed "
                    "anchor count, so an undeclared budget means an unbounded review queue."
                )
        return errors

    def promotion_errors(self, promoted_count: int) -> List[str]:
        limit = self.spec["max_promotions"]
        if limit is None:
            return []
        if promoted_count > limit:
            if limit == 0:
                return [
                    "profile 'audit' promotes nothing by design -- it exists to measure whether "
                    "a larger investment is worth making. %d promotion(s) attempted."
                    % promoted_count
                ]
            return [
                "profile %r caps promotions at %d without explicit human sign-off that a larger "
                "scope is intentional (%d attempted). The cap is not about capacity; it is about "
                "keeping the first pass small enough that a wrong promotion is cheap to undo."
                % (self.name, limit, promoted_count)
            ]
        return []

    def scope_errors(self, scopes: List[str]) -> List[str]:
        limit = self.spec["max_scopes"]
        if limit is not None and len(scopes) > limit:
            return [
                "profile %r permits %d recovery scope(s), %d given. Unscoped recovery on a "
                "zero-anchor repository produces a first batch no one can review, which is the "
                "fastest way to lose trust in the whole pipeline."
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
    """Was the pass/fail bar written before the results were seen?

    Checked by comparing the criteria file's modification time against the first
    pilot row in the ledger. Not a perfect proof -- a determined person can touch
    a file -- but it catches the realistic case, which is not fraud. It is someone
    who genuinely believes the threshold was wrong now that they have seen the
    data, which is exactly the belief pre-registration exists to overrule.
    """
    layout = config.layout
    errors: List[str] = []

    if not os.path.isfile(layout.pass_fail):
        return [
            "no %s. The pass/fail bar must be written and committed before any pilot ticket "
            "runs." % os.path.relpath(layout.pass_fail, config.workspace)
        ]

    text = read_text(layout.pass_fail) or ""
    if "<measure on baseline first>" in text or "<fill in" in text:
        errors.append(
            "%s still contains template placeholders, so no bar has actually been set."
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
            "%s was modified at %s, after the first pilot run at %s. Thresholds are not "
            "adjusted once results are visible -- after real investment in a recovery pass, "
            "whoever ran it is strongly motivated to find a bar the results clear."
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
        "or widen the scope before running Step 5." % (len(ticket_paths), ", ".join(scopes))
    )
