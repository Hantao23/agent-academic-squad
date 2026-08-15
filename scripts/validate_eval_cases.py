#!/usr/bin/env python3
"""Validate the trigger and routing eval dataset without running a model."""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


DATASET = Path(__file__).resolve().parent.parent / "evals" / "trigger-routing.csv"
REQUIRED_COLUMNS = {
    "id",
    "category",
    "should_trigger",
    "expected_stage",
    "expected_domain",
    "expected_handling",
    "expected_external_skill",
    "constraints",
    "prompt",
}
ALLOWED_CATEGORIES = {"explicit", "implicit", "contextual", "negative", "boundary"}
ALLOWED_STAGES = {"none", "plan", "execute", "review"}
ALLOWED_DOMAINS = {"none", "code_experiment", "mathematics", "paper"}
ALLOWED_HANDLING = {"direct", "subagent", "plan_first"}
ALLOWED_CONSTRAINTS = {
    "none",
    "read_only",
    "plan_only",
    "respect_model_override",
    "no_file_write",
    "direct_execution",
    "temporary_plan",
    "durable_plan",
    "long_running",
    "temporary_artifacts",
    "workspace_read_only",
}


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> int:
    try:
        with DATASET.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            if set(reader.fieldnames or ()) != REQUIRED_COLUMNS:
                fail(f"unexpected columns: {reader.fieldnames}")
            rows = list(reader)

        if not 20 <= len(rows) <= 40:
            fail(f"expected 20-40 cases, found {len(rows)}")

        identifiers = [row["id"] for row in rows]
        if len(identifiers) != len(set(identifiers)):
            fail("case IDs must be unique")

        triggers = Counter()
        categories = Counter()
        for row_number, row in enumerate(rows, start=2):
            prefix = f"row {row_number} ({row['id']})"
            if not row["prompt"].strip():
                fail(f"{prefix}: prompt is empty")
            if row["category"] not in ALLOWED_CATEGORIES:
                fail(f"{prefix}: invalid category")
            if row["should_trigger"] not in {"true", "false"}:
                fail(f"{prefix}: should_trigger must be true or false")
            if row["expected_stage"] not in ALLOWED_STAGES:
                fail(f"{prefix}: invalid stage")
            if row["expected_domain"] not in ALLOWED_DOMAINS:
                fail(f"{prefix}: invalid domain")
            if row["expected_handling"] not in ALLOWED_HANDLING:
                fail(f"{prefix}: invalid handling")
            explicit_token = "$agent-academic-squad" in row["prompt"]
            if row["category"] == "explicit" and not explicit_token:
                fail(f"{prefix}: explicit case must invoke $agent-academic-squad")
            if row["category"] != "explicit" and explicit_token:
                fail(f"{prefix}: only explicit cases may invoke $agent-academic-squad")
            constraints = set(row["constraints"].split("|"))
            if not constraints <= ALLOWED_CONSTRAINTS:
                fail(f"{prefix}: invalid constraint")
            if row["should_trigger"] == "false":
                if row["expected_stage"] != "none" or row["expected_domain"] != "none":
                    fail(f"{prefix}: inactive cases must use stage/domain none")
                if row["expected_handling"] != "direct":
                    fail(f"{prefix}: inactive cases must be handled directly")
                if row["expected_external_skill"]:
                    fail(f"{prefix}: inactive squad cases cannot assign an external skill")
            triggers[row["should_trigger"]] += 1
            categories[row["category"]] += 1

        if triggers["true"] < 8 or triggers["false"] < 8:
            fail("dataset needs at least eight positive and eight negative cases")
        missing_categories = ALLOWED_CATEGORIES - set(categories)
        if missing_categories:
            fail(f"missing categories: {sorted(missing_categories)}")
        if not any("$agent-academic-squad" in row["prompt"] for row in rows):
            fail("dataset needs an explicit invocation case")

    except (OSError, ValueError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"validated {len(rows)} cases: "
        f"{triggers['true']} trigger, {triggers['false']} direct; "
        f"categories={dict(sorted(categories.items()))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
