"""The invariants BEARING states as Contracts, held as executable checks.

The framework's own argument is that a documented rule decays into an aspiration
unless something verifies it. These are the rules that would be most damaging to
lose quietly, so each one has a test that fails if it erodes.
"""

from __future__ import annotations

import json
import os
import unittest

from context import BearingTestCase, TempWorkspace, run_cli

# Several tests need fixture source files containing real anchor annotations. Written
# literally, BEARING's own scanner would read them as this repository's anchors and
# report them as broken -- which is the false-positive class `bearing:ignore-anchor`
# exists for. So each fixture line carries the marker in this file and has it removed
# on the way to disk, leaving the temp workspace with exactly what a real repository
# would contain.
_MARKER = "bearing:ignore-anchor"


def fixture(text):
    return "\n".join(line.replace(_MARKER, "").rstrip() for line in text.split("\n"))


def _record(number, title, status="Accepted", extra=""):
    return (
        "---\n"
        "id: ADR-%04d\n"
        "title: %s\n"
        "status: %s\n"
        "date: 2026-01-01\n"
        "triggers: [%s]\n"
        "%s"
        "---\n\n"
        "# ADR-%04d: %s\n\n"
        "## Context\n\nSomething needed deciding.\n\n"
        "## Decision\n\nWe decided.\n\n"
        "## Consequences\n\nThings follow.\n"
    ) % (number, title, status, title.lower(), extra, number, title)


class NoInferenceBlocksAMergeTest(BearingTestCase):
    """The single most load-bearing rule in the framework."""

    def test_config_cannot_grant_a_recovery_signal_blocking_authority(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/config.json",
                json.dumps(
                    {
                        "version": 1,
                        "decisions": {"path": "docs/decisions"},
                        "enforcement": {"block_on": ["structural", "recovery_signal"]},
                    }
                ),
            )
            result = run_cli(["lint"], workspace=workspace.path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("recovery_signal", result.stdout + result.stderr)

    def test_a_high_confidence_candidate_produces_no_lint_error(self):
        """Confidence is a claim about evidence, never about authority."""
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "docs/decisions/shadow/candidates.jsonl",
                "\n".join(
                    json.dumps(
                        {
                            "candidate_id": "CAND-%03d" % index,
                            "lifecycle_state": "Reviewable",
                            "confidence": "HIGH",
                            "subject": "src/billing/invoice.py",
                        }
                    )
                    for index in range(3)
                )
                + "\n",
            )
            run_cli(["index"], workspace=workspace.path)
            result = run_cli(["lint"], workspace=workspace.path)
            self.assertEqual(
                result.returncode,
                0,
                "a confident candidate must not fail lint:\n%s" % result.stdout,
            )

    def test_an_anchor_into_the_shadow_graph_is_an_error(self):
        """The inverse: code may not borrow authority from a candidate."""
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "src/thing.py",
                fixture(
                    "# @see docs/decisions/shadow/candidates.jsonl#CAND-001  bearing:ignore-anchor\n"
                    "def thing():\n    return 1\n"
                ),
            )
            workspace.write(
                ".bearing/config.json",
                json.dumps(
                    {
                        "version": 1,
                        "decisions": {"path": "docs/decisions"},
                        "scope": {"include": ["src/**"]},
                    }
                ),
            )
            run_cli(["index"], workspace=workspace.path)
            result = run_cli(["lint"], workspace=workspace.path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("anchor-into-shadow", result.stdout)


class ShadowGraphTest(BearingTestCase):
    def test_lint_and_the_schema_agree_on_the_lifecycle_states(self):
        """A schema-valid candidate that lint rejects discredits both."""
        import os

        from context import PLUGIN_ROOT
        from bearing.decisions import CANDIDATE_STATES

        schema_path = os.path.join(
            PLUGIN_ROOT, "skills", "decision-recovery", "schemas", "candidate.schema.json"
        )
        with open(schema_path, "r", encoding="utf-8") as handle:
            schema = json.load(handle)
        self.assertEqual(
            sorted(schema["properties"]["lifecycle_state"]["enum"]),
            sorted(CANDIDATE_STATES),
        )

    def test_an_assessed_dead_end_does_not_re_enter_the_review_queue(self):
        from bearing.decisions import surfaced_candidates

        candidates = [
            {"candidate_id": "a", "lifecycle_state": "Reviewable", "confidence": "HIGH"},
            {"candidate_id": "b", "lifecycle_state": "Insufficient Evidence", "confidence": "HIGH"},
            {"candidate_id": "c", "lifecycle_state": "Rejected", "confidence": "HIGH"},
            {"candidate_id": "d", "lifecycle_state": "Promoted", "confidence": "HIGH"},
        ]
        surfaced = {candidate["candidate_id"] for candidate in surfaced_candidates(candidates)}
        self.assertEqual(surfaced, {"a"})

    def test_a_low_confidence_candidate_surfaces_only_when_it_contradicts_or_is_load_bearing(self):
        from bearing.decisions import surfaced_candidates

        candidates = [
            {"candidate_id": "quiet", "lifecycle_state": "Detected", "confidence": "LOW"},
            {
                "candidate_id": "contradicts",
                "lifecycle_state": "Detected",
                "confidence": "LOW",
                "conflicts_with_accepted": "ADR-0001",
            },
            {
                "candidate_id": "load-bearing",
                "lifecycle_state": "Detected",
                "confidence": "LOW",
                "load_bearing": True,
            },
        ]
        surfaced = {candidate["candidate_id"] for candidate in surfaced_candidates(candidates)}
        self.assertEqual(surfaced, {"contradicts", "load-bearing"})

    def test_an_unknown_lifecycle_state_is_a_lint_error(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(
                    {
                        "candidate_id": "CAND-001",
                        "lifecycle_state": "Vibes",
                        "confidence": "HIGH",
                    }
                )
                + "\n",
            )
            run_cli(["index"], workspace=workspace.path)
            result = run_cli(["lint"], workspace=workspace.path)
            self.assertIn("candidate-bad-state", result.stdout)


class StructuralEnforcementTest(BearingTestCase):
    def test_an_unresolved_anchor_is_an_error(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "src/thing.py",
                fixture(
                    "# @see ADR-0042  bearing:ignore-anchor\ndef thing():\n    return 1\n"
                ),
            )
            workspace.write(
                ".bearing/config.json",
                json.dumps(
                    {
                        "version": 1,
                        "decisions": {"path": "docs/decisions"},
                        "scope": {"include": ["src/**"]},
                    }
                ),
            )
            run_cli(["index"], workspace=workspace.path)
            result = run_cli(["lint"], workspace=workspace.path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("anchor-unresolved", result.stdout)

    def test_a_superseded_record_without_a_successor_is_an_error(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "docs/decisions/0002-old.md", _record(2, "Old approach", status="Superseded")
            )
            run_cli(["index"], workspace=workspace.path)
            result = run_cli(["lint"], workspace=workspace.path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("superseded-without-successor", result.stdout)

    def test_a_resolved_successor_chain_is_clean(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "docs/decisions/0002-old.md",
                _record(2, "Old approach", status="Superseded", extra="superseded_by: ADR-0003\n"),
            )
            workspace.write("docs/decisions/0003-new.md", _record(3, "New approach"))
            workspace.write(
                "src/a.py",
                fixture(
                    "# @see ADR-0002  bearing:ignore-anchor\n"
                    "# @see ADR-0003  bearing:ignore-anchor\n"
                ),
            )
            run_cli(["index"], workspace=workspace.path)
            result = run_cli(["lint"], workspace=workspace.path)
            self.assertNotIn("superseded-without-successor", result.stdout)
            self.assertNotIn("successor-unresolved", result.stdout)

    def test_a_deprecation_marker_with_no_record_to_consult_is_reported(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "src/legacy.py",
                fixture(
                    "# @deprecated do not use  bearing:ignore-anchor\n"
                    "def legacy():\n    pass\n"
                ),
            )
            workspace.write(
                ".bearing/config.json",
                json.dumps(
                    {
                        "version": 1,
                        "decisions": {"path": "docs/decisions"},
                        "scope": {"include": ["src/**"]},
                    }
                ),
            )
            run_cli(["index"], workspace=workspace.path)
            result = run_cli(["lint"], workspace=workspace.path)
            self.assertIn("deprecated-without-anchor", result.stdout)


class DisclosureBudgetTest(BearingTestCase):
    def test_an_index_over_budget_fails(self):
        """An always-loaded file that grows without bound reverses the value."""
        with TempWorkspace() as workspace:
            workspace.init()
            for number in range(2, 60):
                workspace.write(
                    "docs/decisions/%04d-record.md" % number,
                    _record(number, "Decision number %d with a deliberately long title" % number),
                )
            workspace.write(
                ".bearing/config.json",
                json.dumps(
                    {
                        "version": 1,
                        "decisions": {"path": "docs/decisions"},
                        "verify": {"index_token_budget": 200},
                    }
                ),
            )
            result = run_cli(["index"], workspace=workspace.path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("disclosure budget", result.stdout)


class ModelTieringContractTest(BearingTestCase):
    def test_a_frontier_model_on_extraction_is_rejected(self):
        from bearing.cost import load_price_book, tiering_errors

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config({"models.extract.model": "claude-opus-4.1",
                                       "models.extract.tier": "cheap"})
            errors = tiering_errors(config, load_price_book(config))
            self.assertTrue(errors, "the tiering Contract must refuse this config")
            self.assertTrue(any("Tiering Contract" in error for error in errors))

    def test_doctor_fails_on_a_contract_violating_model_choice(self):
        with TempWorkspace() as workspace:
            workspace.init()
            result = run_cli(
                ["doctor"],
                workspace=workspace.path,
                env={"BEARING_MODELS_EXTRACT_MODEL": '"claude-opus-4.1"'},
            )
            self.assertNotEqual(
                result.returncode,
                0,
                "configuration must not be able to silently void a Contract:\n%s" % result.stdout,
            )

    def test_an_unknown_model_is_rejected_rather_than_assumed_cheap(self):
        from bearing.cost import load_price_book, tiering_errors

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config({"models.extract.model": "some-new-model"})
            errors = tiering_errors(config, load_price_book(config))
            self.assertTrue(any("price book does not list" in error for error in errors))

    def test_the_default_config_satisfies_its_own_contract(self):
        from bearing.cost import load_price_book, tiering_errors

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config()
            self.assertEqual(tiering_errors(config, load_price_book(config)), [])


class HonestCostTest(BearingTestCase):
    def test_review_time_is_minutes_until_a_rate_is_supplied(self):
        from bearing.cost import review_cost

        with TempWorkspace() as workspace:
            workspace.init()
            rows = [{"stage": "review", "estimated_review_minutes": 90}]

            without = review_cost(workspace.config(), rows)
            self.assertEqual(without.minutes, 90)
            self.assertIsNone(
                without.usd,
                "BEARING must not invent a dollar value for an engineer's attention",
            )
            self.assertIn("min", without.render())
            self.assertNotIn("$", without.render())

            with_rate = review_cost(
                workspace.config({"cost.reviewer_rate_usd_per_hour": 150}), rows
            )
            self.assertAlmostEqual(with_rate.usd or 0.0, 225.0)

    def test_an_estimated_token_count_produces_a_range_not_a_point(self):
        from bearing.cost import load_price_book, model_cost

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config()
            book = load_price_book(config)

            estimated, _ = model_cost(
                config,
                book,
                [
                    {
                        "run_id": "r1",
                        "stage": "extract",
                        "model": "claude-haiku-4.5",
                        "input_tokens": 1_000_000,
                        "output_tokens": 100_000,
                        "token_source": "estimated",
                    }
                ],
            )
            self.assertIsNotNone(estimated)
            self.assertTrue(estimated.estimated)
            self.assertLess(estimated.low, estimated.expected)
            self.assertGreater(estimated.high, estimated.expected)
            self.assertIn("est.", estimated.render())

            measured, _ = model_cost(
                config,
                book,
                [
                    {
                        "run_id": "r1",
                        "stage": "extract",
                        "model": "claude-haiku-4.5",
                        "input_tokens": 1_000_000,
                        "output_tokens": 100_000,
                        "token_source": "measured",
                    }
                ],
            )
            self.assertFalse(measured.estimated)
            self.assertEqual(measured.low, measured.high)
            self.assertIn("measured", measured.render())

    def test_an_unpriced_model_is_excluded_rather_than_guessed_at(self):
        from bearing.cost import load_price_book, model_cost

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config()
            total, notes = model_cost(
                config,
                load_price_book(config),
                [
                    {
                        "run_id": "r1",
                        "stage": "extract",
                        "model": "totally-unknown",
                        "input_tokens": 500,
                        "output_tokens": 500,
                    }
                ],
            )
            self.assertIsNone(total)
            self.assertTrue(any("unpriced" in note for note in notes))

    def test_cost_per_promoted_is_withheld_without_a_reviewer_rate(self):
        """Reporting the small half of the cost as the whole is worse than silence."""
        from bearing.cost import cost_per_promoted, load_price_book

        with TempWorkspace() as workspace:
            workspace.init()
            rows = [
                {
                    "run_id": "r1",
                    "stage": "extract",
                    "model": "claude-haiku-4.5",
                    "input_tokens": 100_000,
                    "output_tokens": 10_000,
                },
                {
                    "run_id": "r1",
                    "stage": "review",
                    "estimated_review_minutes": 60,
                    "candidates_reviewed": 20,
                    "candidates_promoted": 4,
                },
            ]
            config = workspace.config()
            self.assertIsNone(cost_per_promoted(config, load_price_book(config), rows))

            priced = workspace.config({"cost.reviewer_rate_usd_per_hour": 120})
            value = cost_per_promoted(priced, load_price_book(priced), rows)
            self.assertIsNotNone(value)
            self.assertGreater(value, 0)

    def test_the_report_refuses_token_figures_without_paired_outcome_metrics(self):
        from bearing.cost import require_paired_metrics

        complete = [
            {
                "run_id": "r1",
                "stage": "pilot",
                "condition": "bearing",
                "rework_count": 1,
                "contract_violations": 0,
                "escalation_correct": 3,
            }
        ]
        self.assertEqual(require_paired_metrics(complete), [])

        partial = [{"run_id": "r1", "stage": "pilot", "condition": "bearing", "rework_count": 1}]
        missing = require_paired_metrics(partial)
        self.assertTrue(missing)
        self.assertIn("contract_violations", missing[0])

    def test_every_cost_report_carries_the_caveat_block(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/ledger/cost.jsonl",
                json.dumps(
                    {
                        "run_id": "r1",
                        "stage": "extract",
                        "model": "claude-haiku-4.5",
                        "input_tokens": 1000,
                        "output_tokens": 100,
                        "token_source": "measured",
                    }
                )
                + "\n",
            )
            result = run_cli(["report"], workspace=workspace.path)
            self.assertIn("How to read these numbers", result.stdout)
            self.assertIn("price book", result.stdout.lower())

    def test_a_stale_price_book_stamps_a_warning_into_the_report(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/pricing.json",
                json.dumps(
                    {
                        "version": "2019-01-01",
                        "models": {
                            "claude-haiku-4.5": {
                                "tier": "cheap",
                                "input": 1.0,
                                "output": 5.0,
                                "as_of": "2019-01-01",
                                "source": "https://example.invalid/prices",
                            }
                        },
                    }
                ),
            )
            workspace.write(
                ".bearing/ledger/cost.jsonl",
                json.dumps(
                    {
                        "run_id": "r1",
                        "stage": "extract",
                        "model": "claude-haiku-4.5",
                        "input_tokens": 1000,
                        "output_tokens": 100,
                        "token_source": "measured",
                    }
                )
                + "\n",
            )
            result = run_cli(["report"], workspace=workspace.path)
            self.assertIn(
                "days old",
                result.stdout,
                "a figure derived from a stale book must say so where the figure is:\n%s"
                % result.stdout,
            )

    def test_every_figure_names_the_price_book_that_produced_it(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/ledger/cost.jsonl",
                json.dumps(
                    {
                        "run_id": "r1",
                        "stage": "extract",
                        "model": "claude-haiku-4.5",
                        "input_tokens": 1000,
                        "output_tokens": 100,
                        "token_source": "measured",
                    }
                )
                + "\n",
            )
            result = run_cli(["report"], workspace=workspace.path)
            self.assertIn("price book", result.stdout.lower())


class ProfileTest(BearingTestCase):
    def test_pilot_caps_promotions_to_keep_the_first_batch_reviewable(self):
        from bearing.profiles import Profile

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config()
            self.assertTrue(Profile("pilot", config).promotion_errors(20))
            self.assertEqual(Profile("pilot", config).promotion_errors(3), [])
            self.assertEqual(
                Profile("thorough", config).promotion_errors(200),
                [],
                "thorough relaxes the anchor cap; what it does not relax is review capacity",
            )

    def test_audit_promotes_nothing(self):
        from bearing.profiles import Profile

        with TempWorkspace() as workspace:
            workspace.init()
            errors = Profile("audit", workspace.config()).promotion_errors(1)
            self.assertTrue(errors)
            self.assertIn("promotes nothing by design", errors[0])

    def test_pilot_permits_only_one_recovery_scope(self):
        from bearing.profiles import Profile

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config()
            self.assertEqual(Profile("pilot", config).scope_errors(["src/billing/**"]), [])
            self.assertTrue(
                Profile("pilot", config).scope_errors(["src/billing/**", "src/auth/**"])
            )
            self.assertEqual(
                Profile("thorough", config).scope_errors(["a/**", "b/**", "c/**"]), []
            )

    def test_thorough_requires_a_declared_review_budget(self):
        from bearing.profiles import Profile

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config({"review.budget_minutes_per_session": 0})
            errors = Profile("thorough", config).readiness_errors()
            self.assertTrue(
                errors,
                "coverage in thorough mode is bounded by review capacity, so an undeclared "
                "budget means an unbounded queue",
            )
            self.assertEqual(Profile("thorough", workspace.config()).readiness_errors(), [])

    def test_waves_never_exceed_what_the_declared_budget_can_absorb(self):
        from bearing.profiles import Profile, plan_waves

        with TempWorkspace() as workspace:
            workspace.init()
            profile = Profile("thorough", workspace.config({"review.wave_size": 10}))
            waves = plan_waves(profile, 47)
            self.assertEqual(sum(wave["candidates"] for wave in waves), 47)
            self.assertTrue(all(wave["candidates"] <= 10 for wave in waves))
            self.assertEqual([wave["wave"] for wave in waves], [1, 2, 3, 4, 5])

    def test_a_wave_size_larger_than_the_budget_resolves_to_the_budget(self):
        """Resolving the contradiction toward the larger number is how review
        becomes rubber-stamping."""
        from bearing.profiles import Profile

        with TempWorkspace() as workspace:
            workspace.init()
            profile = Profile(
                "thorough",
                workspace.config(
                    {
                        "review.wave_size": 500,
                        "review.budget_minutes_per_session": 60,
                        "review.seconds_per_candidate_estimate": 120,
                    }
                ),
            )
            self.assertEqual(profile.wave_size, 30)

    def test_the_next_wave_waits_for_the_current_one_to_clear(self):
        from bearing.profiles import Profile, wave_gate

        with TempWorkspace() as workspace:
            workspace.init()
            config = workspace.config()
            profile = Profile("thorough", config)

            allowed, _ = wave_gate(profile, config)
            self.assertTrue(allowed)

            workspace.write(
                "docs/decisions/shadow/candidates.jsonl",
                json.dumps(
                    {
                        "candidate_id": "CAND-001",
                        "lifecycle_state": "Reviewable",
                        "confidence": "HIGH",
                    }
                )
                + "\n",
            )
            allowed, reason = wave_gate(profile, workspace.config())
            self.assertFalse(allowed)
            self.assertIn("outstanding", reason)

    def test_pre_registration_catches_a_threshold_moved_after_the_results(self):
        from bearing.profiles import pre_registration_errors

        with TempWorkspace() as workspace:
            workspace.init()
            self.assertTrue(
                pre_registration_errors(workspace.config()),
                "with no criteria file at all, thorough mode must not start",
            )

            workspace.write(
                ".bearing/ledger/pass-fail-criteria.md",
                "# Criteria\n\nRework must drop by at least 20%.\n",
            )
            workspace.write(
                ".bearing/ledger/cost.jsonl",
                json.dumps(
                    {
                        "run_id": "r1",
                        "stage": "pilot",
                        "condition": "bearing",
                        "recorded_at": "2020-01-01T00:00:00",
                    }
                )
                + "\n",
            )
            errors = pre_registration_errors(workspace.config())
            self.assertTrue(
                any("after the first pilot run" in error for error in errors),
                "a criteria file touched after the first pilot row must be reported: %s" % errors,
            )

    def test_a_template_placeholder_means_no_bar_was_actually_set(self):
        from bearing.profiles import pre_registration_errors

        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/ledger/pass-fail-criteria.md",
                "# Criteria\n\nRework must drop by <measure on baseline first>.\n",
            )
            errors = pre_registration_errors(workspace.config())
            self.assertTrue(any("placeholder" in error for error in errors))


class VerifyTest(BearingTestCase):
    def test_a_missing_evaluation_set_is_skipped_with_a_reason_not_scored_as_a_pass(self):
        """Recall cannot be asserted without cases whose answer is known."""
        with TempWorkspace() as workspace:
            workspace.init()
            result = run_cli(["verify", "--escalate", "--json"], workspace=workspace.path)
            checks = json.loads(result.stdout)
            recall = [
                check for check in checks if "escalation recall" in check["name"]
            ]
            self.assertEqual(len(recall), 1)
            self.assertEqual(
                recall[0]["status"],
                "skip",
                "an absent eval set must be a skip carrying its reason, never a pass",
            )
            self.assertIn("cases.jsonl", recall[0]["detail"])
            self.assertFalse(recall[0]["hard"])

    def test_a_failing_eval_set_is_scored_and_fails(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/eval/escalation/cases.jsonl",
                "\n".join(
                    [
                        json.dumps({"id": "e1", "expects": "escalate", "observed": "proceed"}),
                        json.dumps({"id": "e2", "expects": "escalate", "observed": "proceed"}),
                        json.dumps({"id": "e3", "expects": "escalate", "observed": "escalate"}),
                        json.dumps({"id": "p1", "expects": "proceed", "observed": "proceed"}),
                    ]
                )
                + "\n",
            )
            result = run_cli(["verify", "--escalate", "--json"], workspace=workspace.path)
            checks = json.loads(result.stdout)
            recall = [c for c in checks if "escalation recall on must-escalate" in c["name"]][0]
            self.assertEqual(recall["status"], "fail")
            self.assertNotEqual(result.returncode, 0)

    def test_over_escalation_is_also_a_failure(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                ".bearing/eval/escalation/cases.jsonl",
                "\n".join(
                    [
                        json.dumps({"id": "e1", "expects": "escalate", "observed": "escalate"}),
                        json.dumps({"id": "p1", "expects": "proceed", "observed": "escalate"}),
                        json.dumps({"id": "p2", "expects": "proceed", "observed": "escalate"}),
                        json.dumps({"id": "p3", "expects": "proceed", "observed": "proceed"}),
                    ]
                )
                + "\n",
            )
            result = run_cli(["verify", "--escalate", "--json"], workspace=workspace.path)
            checks = json.loads(result.stdout)
            false_rate = [c for c in checks if "false-escalation" in c["name"]][0]
            self.assertEqual(
                false_rate["status"],
                "fail",
                "an agent that stops on everything is not cautious, it is unusable",
            )

    def test_verify_reports_every_pillar_of_the_mandate(self):
        with TempWorkspace() as workspace:
            workspace.init()
            result = run_cli(["verify", "--json"], workspace=workspace.path)
            checks = json.loads(result.stdout)
            self.assertEqual(
                {check["pillar"] for check in checks},
                {"escalate", "anchor", "project", "evolve", "usability"},
            )

    def test_repository_wide_anchor_coverage_is_not_reported_without_a_scope(self):
        """On a legacy codebase it measures the backlog, not the framework."""
        with TempWorkspace() as workspace:
            workspace.init()
            result = run_cli(["verify", "--anchor", "--json"], workspace=workspace.path)
            checks = json.loads(result.stdout)
            coverage = [c for c in checks if "coverage" in c["name"]][0]
            self.assertEqual(coverage["status"], "skip")
            self.assertIn("backlog", coverage["detail"])

    def test_project_conformance_catches_adapter_drift(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(
                ["render"],
                workspace=workspace.path,
                env={"BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"repo"'},
            )
            path = ".cursor/agents/decision-archaeologist.md"
            workspace.write(path, workspace.read(path) + "\nedited by hand\n")
            result = run_cli(
                ["verify", "--project"],
                workspace=workspace.path,
                env={"BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"repo"'},
            )
            self.assertNotEqual(result.returncode, 0)

    def test_uninstall_never_removes_decision_content(self):
        """The answer to the lock-in objection, as a test rather than a promise."""
        with TempWorkspace() as workspace:
            workspace.init()
            result = run_cli(["verify", "--usability", "--json"], workspace=workspace.path)
            checks = json.loads(result.stdout)
            check = [c for c in checks if "uninstall" in c["name"]][0]
            self.assertEqual(check["status"], "ok", check["detail"])

    def test_uninstall_preserves_records_in_practice(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write("docs/decisions/0002-keep-me.md", _record(2, "Keep me"))
            run_cli(["index"], workspace=workspace.path)
            run_cli(
                ["render"],
                workspace=workspace.path,
                env={"BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"repo"'},
            )
            result = run_cli(["uninstall"], workspace=workspace.path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(workspace.exists("docs/decisions/0002-keep-me.md"))
            self.assertTrue(workspace.exists("docs/decisions/index.json"))
            self.assertFalse(workspace.exists(".cursor/agents/decision-archaeologist.md"))

    def test_project_conformance_catches_adapter_drift(self):
        with TempWorkspace() as workspace:
            workspace.init()
            run_cli(
                ["render"],
                workspace=workspace.path,
                env={"BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"repo"'},
            )
            path = ".cursor/agents/decision-archaeologist.md"
            workspace.write(path, workspace.read(path) + "\nedited by hand\n")
            result = run_cli(
                ["verify", "--project"],
                workspace=workspace.path,
                env={"BEARING_PROJECTIONS_SUBAGENTS_SCOPE": '"repo"'},
            )
            self.assertNotEqual(result.returncode, 0)


class DocsConformanceTest(BearingTestCase):
    """A document that names a path it does not ship teaches readers to distrust it.

    This is the check with the widest blast radius in the suite, because the
    framework's whole argument is that written intent should be verifiable. It has
    to catch a moved directory, and it has to not cry wolf -- a check with false
    positives gets switched off, and then the real breakage stops being reported.
    """

    def _run(self, workspace):
        result = run_cli(["verify", "--usability", "--json"], workspace=workspace.path)
        checks = json.loads(result.stdout)
        return [c for c in checks if c["name"] == "documented paths exist"][0]

    def test_a_reference_to_a_moved_directory_is_reported(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write("README.md", "Skills live in `plugin/skills/nope/`.\n")
            check = self._run(workspace)
            self.assertEqual(check["status"], "fail")
            self.assertIn("plugin/skills/nope/", check["detail"])

    def test_a_line_may_opt_out_when_it_describes_another_repository(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "README.md",
                "Most repos have `.github/copilot-instructions.md`. "
                "<!-- bearing:ignore-paths: describes other repositories -->\n",
            )
            self.assertEqual(self._run(workspace)["status"], "ok")

    def test_a_relative_path_quoted_as_an_anti_pattern_is_not_treated_as_a_repo_path(self):
        """`../x` is relative to whatever the prose describes, not to the root.

        The specs have to name this reference class in order to forbid it, and
        `os.path.isdir("..")` is always true, so without this the documents could
        not discuss the rule they are enforcing.
        """
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "README.md",
                "A skill may not reach `../decision-recovery/schemas/candidate.schema.json`.\n",
            )
            self.assertEqual(self._run(workspace)["status"], "ok")

    def test_a_placeholder_or_glob_is_not_asserted_to_exist(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write(
                "README.md",
                "Records live in `<decisions.path>/shadow/` and scope takes `src/**`.\n",
            )
            self.assertEqual(self._run(workspace)["status"], "ok")

    def test_an_alternative_decision_convention_may_be_named_without_being_adopted(self):
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write("README.md", "Some repositories use `docs/adr/` instead.\n")
            self.assertEqual(self._run(workspace)["status"], "ok")

    def test_the_convention_exemption_does_not_extend_beneath_the_directory(self):
        """Naming an alternative convention is fair; naming a file in it is not.

        `docs/adr/` may appear in prose describing other repositories, but
        `docs/adr/0007-caching.md` is a claim about a specific artifact, and a
        blanket exemption on the directory would let every such claim through.
        """
        with TempWorkspace() as workspace:
            workspace.init()
            workspace.write("README.md", "See `docs/adr/0007-caching.md` for the reasoning.\n")
            self.assertEqual(self._run(workspace)["status"], "fail")

    def test_the_configured_decisions_path_is_never_exempt(self):
        with TempWorkspace(decisions_path="docs/adr") as workspace:
            workspace.init()
            workspace.write("README.md", "Records live in `docs/adr/` and there is `docs/adr/gone.md`.\n")
            check = self._run(workspace)
            self.assertEqual(check["status"], "fail")
            self.assertIn("docs/adr/gone.md", check["detail"])


if __name__ == "__main__":
    unittest.main()
