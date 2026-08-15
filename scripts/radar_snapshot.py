#!/usr/bin/env python3
"""Fetch a compact, read-only snapshot of the public Codex Radar feeds."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def required_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"expected {key!r} to be a list")
    return value


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def freshness(value: Any, max_age_hours: float) -> dict[str, Any]:
    parsed = parse_timestamp(value)
    if parsed is None:
        return {"timestamp": value, "age_hours": None, "stale": None}
    age_hours = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 3600)
    return {
        "timestamp": parsed.isoformat(),
        "age_hours": round(age_hours, 2),
        "stale": age_hours > max_age_hours,
    }


def numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def fetch_json(url: str, timeout: float) -> Any:
    request = Request(url, headers={"User-Agent": "agent-academic-squad"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def compact_recommendations(payload: dict[str, Any]) -> dict[str, Any]:
    groups = []
    for group in required_list(payload, "recommendations"):
        if not isinstance(group, dict):
            continue
        items = []
        raw_items = group.get("items", [])
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
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
    raw_alert_container = payload.get("degradation_alerts", [])
    alert_rule = None
    if isinstance(raw_alert_container, dict):
        alert_rule = raw_alert_container.get("rule")
        raw_alerts = raw_alert_container.get("items")
        if not isinstance(raw_alerts, list):
            raise ValueError("expected 'degradation_alerts.items' to be a list")
    elif isinstance(raw_alert_container, list):
        raw_alerts = raw_alert_container
    else:
        raise ValueError("expected 'degradation_alerts' to be a list or object")
    for alert in raw_alerts:
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
        "degradation_alert_rule": alert_rule,
        "degradation_alerts": alerts,
    }


def compact_deep_swe(payload: dict[str, Any]) -> dict[str, Any]:
    points = []
    for point in required_list(payload, "points"):
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
    points.sort(
        key=lambda item: (
            numeric(item.get("iq")) is None,
            -(numeric(item.get("iq")) or 0),
        )
    )
    return {
        "benchmark_id": payload.get("benchmark_id"),
        "source_updated_at": payload.get("source_updated_at"),
        "runs_24h_total": payload.get("runs_24h_total"),
        "points": points,
    }


def compact_community(payload: dict[str, Any]) -> dict[str, Any]:
    models = []
    for model in required_list(payload, "models"):
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
    runs = required_list(payload, "runs")
    dated_runs = [
        (timestamp, run)
        for run in runs
        if isinstance(run, dict)
        if (timestamp := parse_timestamp(run.get("measured_at"))) is not None
    ]
    latest = max(dated_runs, key=lambda item: item[0])[1] if dated_runs else {}
    return {
        "updated_at": payload.get("updated_at"),
        "latest": {
            key: latest.get(key) for key in ("run_id", "measured_at", "models")
        },
    }


COMPACTORS = {
    "recommendations": compact_recommendations,
    "deep_swe": compact_deep_swe,
    "community": compact_community,
    "fast": compact_fast,
}


def feed_timestamp(name: str, feed: dict[str, Any]) -> Any:
    if name in {"recommendations", "deep_swe"}:
        return feed.get("source_updated_at")
    if name == "community":
        return feed.get("updated_at") or feed.get("day")
    if name == "fast":
        latest = feed.get("latest")
        if isinstance(latest, dict):
            return latest.get("measured_at") or feed.get("updated_at")
    return None


def fetch_and_compact(name: str, url: str, timeout: float, max_age_hours: float) -> dict[str, Any]:
    payload = fetch_json(url, timeout)
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value is not an object")
    feed = COMPACTORS[name](payload)
    feed["freshness"] = freshness(feed_timestamp(name, feed), max_age_hours)
    return feed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-feed timeout in seconds")
    parser.add_argument("--indent", type=int, default=2, help="JSON indentation")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=72.0,
        help="Mark a feed stale when its source timestamp is older than this",
    )
    args = parser.parse_args()
    if args.timeout <= 0 or args.max_age_hours <= 0:
        parser.error("timeout and max-age-hours must be positive")

    snapshot: dict[str, Any] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "feeds": {},
        "errors": {},
        "warnings": {},
    }

    completed: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(ENDPOINTS)) as executor:
        futures = {
            executor.submit(fetch_and_compact, name, url, args.timeout, args.max_age_hours): name
            for name, url in ENDPOINTS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                completed[name] = future.result()
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                snapshot["errors"][name] = f"{type(exc).__name__}: {exc}"

    for name in ENDPOINTS:
        feed = completed.get(name)
        if feed is None:
            continue
        snapshot["feeds"][name] = feed
        state = feed["freshness"].get("stale")
        if state is True:
            snapshot["warnings"][name] = "source timestamp is stale"
        elif state is None:
            snapshot["warnings"][name] = "source freshness could not be established"

    print(json.dumps(snapshot, ensure_ascii=False, indent=args.indent, sort_keys=True))
    return 0 if snapshot["feeds"] else 1


if __name__ == "__main__":
    sys.exit(main())
