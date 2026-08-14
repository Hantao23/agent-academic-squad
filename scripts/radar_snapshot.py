#!/usr/bin/env python3
"""Fetch a compact, read-only snapshot of the public Codex Radar feeds."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINTS = {
    "recommendations": "https://codex-reset-radar.pages.dev/api/radar-insights",
    "deep_swe": "https://codex-reset-radar.pages.dev/api/intelligence-efficiency-metrics",
    "community": "https://codex-reset-radar.pages.dev/api/model-ratings?view=public",
    "fast": "https://codex-reset-radar.pages.dev/data/fast-radar-history.json",
}


def fetch_json(url: str, timeout: float) -> Any:
    request = Request(url, headers={"User-Agent": "agent-academic-squad/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def compact_recommendations(payload: dict[str, Any]) -> dict[str, Any]:
    groups = []
    for group in payload.get("recommendations", []):
        items = []
        for item in group.get("items", []):
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    key: item.get(key)
                    for key in (
                        "model",
                        "effort",
                        "iq",
                        "samples",
                        "average_cost_usd",
                        "average_duration_minutes",
                    )
                }
            )
        groups.append({"key": group.get("key"), "title": group.get("title"), "items": items})
    alerts = []
    for alert in payload.get("degradation_alerts", []):
        if not isinstance(alert, dict):
            continue
        alerts.append(
            {
                key: alert.get(key)
                for key in (
                    "model",
                    "effort",
                    "current_iq",
                    "severity",
                    "from_24h_average_iq",
                    "from_48h_average_iq",
                )
            }
        )
    return {
        "source_updated_at": payload.get("source_updated_at"),
        "groups": groups,
        "degradation_alerts": alerts,
    }


def compact_deep_swe(payload: dict[str, Any]) -> dict[str, Any]:
    points = []
    for point in payload.get("points", []):
        if not isinstance(point, dict):
            continue
        points.append(
            {
                key: point.get(key)
                for key in (
                    "model",
                    "effort",
                    "iq",
                    "weighted_passed",
                    "weighted_total",
                    "average_price_usd",
                    "average_minutes",
                    "runs_24h",
                )
            }
        )
    points.sort(key=lambda item: (item.get("iq") is None, -(item.get("iq") or 0)))
    return {
        "benchmark_id": payload.get("benchmark_id"),
        "source_updated_at": payload.get("source_updated_at"),
        "runs_24h_total": payload.get("runs_24h_total"),
        "points": points,
    }


def compact_community(payload: dict[str, Any]) -> dict[str, Any]:
    models = []
    for model in payload.get("models", []):
        if not isinstance(model, dict):
            continue
        models.append(
            {key: model.get(key) for key in ("id", "label", "average", "count")}
        )
    return {
        "day": payload.get("day"),
        "updated_at": payload.get("updated_at"),
        "models": models,
    }


def compact_fast(payload: dict[str, Any]) -> dict[str, Any]:
    runs = payload.get("runs", [])
    latest = runs[-1] if isinstance(runs, list) and runs else {}
    return {
        "updated_at": payload.get("updated_at"),
        "latest": {
            key: latest.get(key) for key in ("run_id", "measured_at", "cli_version", "models")
        },
    }


COMPACTORS = {
    "recommendations": compact_recommendations,
    "deep_swe": compact_deep_swe,
    "community": compact_community,
    "fast": compact_fast,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-feed timeout in seconds")
    parser.add_argument("--indent", type=int, default=2, help="JSON indentation")
    args = parser.parse_args()

    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "feeds": {},
        "errors": {},
    }

    for name, url in ENDPOINTS.items():
        try:
            payload = fetch_json(url, args.timeout)
            if not isinstance(payload, dict):
                raise ValueError("top-level JSON value is not an object")
            snapshot["feeds"][name] = COMPACTORS[name](payload)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            snapshot["errors"][name] = f"{type(exc).__name__}: {exc}"

    print(json.dumps(snapshot, ensure_ascii=False, indent=args.indent, sort_keys=True))
    return 0 if snapshot["feeds"] else 1


if __name__ == "__main__":
    sys.exit(main())
