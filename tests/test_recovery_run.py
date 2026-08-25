"""Recovery run-state: durable telemetry, not a model heartbeat (ADR-0014)."""

from __future__ import annotations

import json
import os
import unittest

from context import BearingTestCase, TempWorkspace, run_cli
from bearing.recovery_run import compute_eta, patch_run, snapshot, start_run


class RecoveryRunTest(BearingTestCase):
    def test_start_writes_status_and_events(self):
        with TempWorkspace() as ws:
            ws.init()
            config = ws.config()
            data = start_run(config, {"stage": "discover"})
            self.assertTrue(data["run_id"].startswith("recovery-"))
            self.assertEqual(data["status"], "running")
            self.assertEqual(data["stage"], "discover")
            self.assertEqual(data["stage_index"], 2)
            status_file = os.path.join(
                ws.path, ".bearing", "runs", "recovery", data["run_id"], "status.json"
            )
            self.assertTrue(os.path.isfile(status_file))
            current = ws.read(".bearing/runs/recovery/current").strip()
            self.assertEqual(current, data["run_id"])
            events = data["recent_activity"]
            self.assertEqual(events[0]["type"], "start")

    def test_patch_merges_and_caps_event_feed(self):
        with TempWorkspace() as ws:
            ws.init()
            config = ws.config()
            start_run(config)
            for i in range(12):
                patch_run(
                    config,
                    {"findings": {"candidate_decisions": i + 1}},
                    {"type": "found", "label": "n=%d" % i},
                )
            data = snapshot(config)
            self.assertEqual(len(data["recent_activity"]), 8)
            self.assertEqual(data["findings"]["candidate_decisions"], 12)

    def test_eta_is_not_locations_over_total_times_stages(self):
        status = {
            "stage": "discover",
            "scope": {"locations_total": 100, "locations_scanned": 10},
            "rates": {"discover": {"per_minute": 20, "samples": 9}},
            "findings": {},
            "status": "running",
        }
        eta = compute_eta(status)
        self.assertEqual(eta["confidence"], "high")
        naive = int((90 / 100.0) * 6 * 3600)
        self.assertLess(eta["remaining_seconds_high"], naive)

    def test_cli_start_and_complete(self):
        with TempWorkspace() as ws:
            ws.init()
            started = run_cli(["recovery-status", "start"], workspace=ws.path)
            self.assertEqual(started.returncode, 0, started.stderr)
            payload = json.loads(started.stdout)
            self.assertEqual(payload["status"], "running")
            done = run_cli(
                ["recovery-status", "complete", "--reason", "pass complete"],
                workspace=ws.path,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            finished = json.loads(done.stdout)
            self.assertEqual(finished["status"], "completed")
            self.assertEqual(finished["stage"], "write_persist")


if __name__ == "__main__":
    unittest.main()
