from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import radar_snapshot  # noqa: E402


class RadarSnapshotTests(unittest.TestCase):
    def test_fast_feed_uses_explicit_timestamp(self) -> None:
        payload = {
            "updated_at": "2026-08-15T00:00:00Z",
            "runs": [
                {"run_id": "new", "measured_at": "2026-08-15T02:00:00Z"},
                {"run_id": "old", "measured_at": "2026-08-14T02:00:00Z"},
            ],
        }
        compacted = radar_snapshot.compact_fast(payload)
        self.assertEqual(compacted["latest"]["run_id"], "new")

    def test_freshness_marks_old_and_unknown_sources(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        self.assertTrue(radar_snapshot.freshness(old, 72)["stale"])
        self.assertIsNone(radar_snapshot.freshness(None, 72)["stale"])

    def test_required_container_shape_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            radar_snapshot.compact_community({"models": {}})

    def test_recommendations_accept_current_alert_container(self) -> None:
        payload = {
            "schema": 1,
            "recommendations": [],
            "degradation_alerts": {"rule": "threshold", "items": []},
        }
        compacted = radar_snapshot.compact_recommendations(payload)
        self.assertEqual(compacted["source_schema_version"], 1)
        self.assertEqual(compacted["degradation_alert_rule"], "threshold")
        self.assertEqual(compacted["degradation_alerts"], [])

    def test_recommendations_reject_invalid_alert_items(self) -> None:
        payload = {
            "recommendations": [],
            "degradation_alerts": {"items": {}},
        }
        with self.assertRaises(ValueError):
            radar_snapshot.compact_recommendations(payload)

    def test_non_numeric_iq_does_not_break_sorting(self) -> None:
        payload = {
            "points": [
                {"model": "unknown", "iq": "n/a"},
                {"model": "known", "iq": 12.5},
            ]
        }
        compacted = radar_snapshot.compact_deep_swe(payload)
        self.assertEqual(compacted["points"][0]["model"], "known")


if __name__ == "__main__":
    unittest.main()
