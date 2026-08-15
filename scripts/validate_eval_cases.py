#!/usr/bin/env python3
"""Validate the trigger and routing eval dataset without running a model."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


DATASET = Path(__file__).resolve().parent.parent / "evals" / "trigger-routing.csv"
E2E_MANIFEST = Path(__file__).resolve().parent.parent / "evals" / "e2e-cases.json"
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
    "unavailable_model",
    "single_writer",
    "no_plan_save",
}
NEGATED_SQUAD_PHRASES = (
    "不用小分队",
    "不要用小分队",
    "别用小分队",
    "不要交给小分队",
    "不交给小分队",
    "不要使用 $agent-academic-squad",
    "不使用 $agent-academic-squad",
    "别使用 $agent-academic-squad",
    "不要调用 $agent-academic-squad",
    "别调用 $agent-academic-squad",
    "不用 $agent-academic-squad",
)
DISCUSSION_ONLY_PHRASES = (
    "讨论小分队",
    "关于小分队",
    "小分队这个名字",
    "小分队这个称呼",
)
E2E_EXPECTED_FIELDS = {
    "should_trigger",
    "stage",
    "domain",
    "handling",
    "external_skills",
    "subagents",
    "models",
    "efforts",
    "writes",
    "final_states",
    "forbidden_actions",
}
ALLOWED_SANDBOXES = {"read-only", "workspace-write"}
ALLOWED_MODELS = {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
ALLOWED_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
ALLOWED_WRITES = {"temporary_plan", "durable_plan", "temporary_artifacts", "workspace"}
ALLOWED_FINAL_STATES = {
    "direct_answer",
    "plan_ready",
    "review_complete",
    "execution_complete",
    "launched",
    "running",
    "handoff_ready",
}
ALLOWED_FORBIDDEN_ACTIONS = {
    "file_write",
    "subagent",
    "artifact_modification",
    "experiment_execution",
    "literature_search",
    "manuscript_write",
    "report_completed",
    "process_launch",
    "model_substitution",
}


def has_explicit_invocation(prompt: str) -> bool:
    if any(phrase in prompt for phrase in NEGATED_SQUAD_PHRASES + DISCUSSION_ONLY_PHRASES):
        return False
    if "$agent-academic-squad" in prompt:
        return True
    stripped = prompt.lstrip()
    return stripped.startswith("小分队") or bool(re.search(r"交给小分队(?:处理|来做|负责|审查|规划|执行|[，,:：。\s]|$)", prompt))


def fail(message: str) -> None:
    raise ValueError(message)


def require_string_list(value: object, prefix: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        fail(f"{prefix}: expected a list of non-empty strings")
    if len(value) != len(set(value)):
        fail(f"{prefix}: values must be unique")
    return value


def validate_e2e_manifest(source_case_ids: set[str]) -> int:
    with E2E_MANIFEST.open(encoding="utf-8") as source:
        manifest = json.load(source)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        fail("e2e manifest: unsupported schema_version")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 8 <= len(cases) <= 20:
        fail("e2e manifest: expected 8-20 cases")
    identifiers: set[str] = set()
    for index, case in enumerate(cases, start=1):
        prefix = f"e2e case {index}"
        if not isinstance(case, dict):
            fail(f"{prefix}: case must be an object")
        if set(case) != {"id", "source_case_id", "prompt", "sandbox", "expected"}:
            fail(f"{prefix}: unexpected fields")
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier:
            fail(f"{prefix}: invalid id")
        if identifier in identifiers:
            fail(f"{prefix}: duplicate id {identifier}")
        identifiers.add(identifier)
        prefix = f"e2e case {identifier}"
        if case.get("source_case_id") not in source_case_ids:
            fail(f"{prefix}: unknown source_case_id")
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            fail(f"{prefix}: prompt is empty")
        if case.get("sandbox") not in ALLOWED_SANDBOXES:
            fail(f"{prefix}: invalid sandbox")
        expected = case.get("expected")
        if not isinstance(expected, dict) or set(expected) != E2E_EXPECTED_FIELDS:
            fail(f"{prefix}: unexpected expected fields")
        if not isinstance(expected["should_trigger"], bool):
            fail(f"{prefix}: should_trigger must be boolean")
        if expected["stage"] not in ALLOWED_STAGES:
            fail(f"{prefix}: invalid stage")
        if expected["domain"] not in ALLOWED_DOMAINS:
            fail(f"{prefix}: invalid domain")
        if expected["handling"] not in ALLOWED_HANDLING:
            fail(f"{prefix}: invalid handling")
        external_skills = require_string_list(expected["external_skills"], f"{prefix}.external_skills")
        models = require_string_list(expected["models"], f"{prefix}.models")
        efforts = require_string_list(expected["efforts"], f"{prefix}.efforts")
        writes = require_string_list(expected["writes"], f"{prefix}.writes")
        final_states = require_string_list(expected["final_states"], f"{prefix}.final_states")
        forbidden = require_string_list(expected["forbidden_actions"], f"{prefix}.forbidden_actions")
        if not set(models) <= ALLOWED_MODELS:
            fail(f"{prefix}: invalid model")
        if not set(efforts) <= ALLOWED_EFFORTS:
            fail(f"{prefix}: invalid effort")
        if not set(writes) <= ALLOWED_WRITES:
            fail(f"{prefix}: invalid write class")
        if not set(final_states) <= ALLOWED_FINAL_STATES:
            fail(f"{prefix}: invalid final state")
        if not set(forbidden) <= ALLOWED_FORBIDDEN_ACTIONS:
            fail(f"{prefix}: invalid forbidden action")
        subagents = expected["subagents"]
        if not isinstance(subagents, dict) or set(subagents) != {"min", "max"}:
            fail(f"{prefix}: invalid subagent bounds")
        minimum, maximum = subagents["min"], subagents["max"]
        if not isinstance(minimum, int) or not isinstance(maximum, int) or not 0 <= minimum <= maximum:
            fail(f"{prefix}: invalid subagent range")
        if not expected["should_trigger"]:
            if expected["stage"] != "none" or expected["domain"] != "none":
                fail(f"{prefix}: inactive case must use stage/domain none")
            if maximum != 0 or external_skills or models or efforts or writes:
                fail(f"{prefix}: inactive case has routed work")
        if case["sandbox"] == "read-only" and writes:
            fail(f"{prefix}: read-only case cannot expect writes")
        if "file_write" in forbidden and writes:
            fail(f"{prefix}: file_write is both expected and forbidden")
    return len(cases)


def main() -> int:
    try:
        with DATASET.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            if set(reader.fieldnames or ()) != REQUIRED_COLUMNS:
                fail(f"unexpected columns: {reader.fieldnames}")
            rows = list(reader)

        if not 20 <= len(rows) <= 50:
            fail(f"expected 20-50 cases, found {len(rows)}")

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
            explicit_invocation = has_explicit_invocation(row["prompt"])
            if row["category"] == "explicit" and not explicit_invocation:
                fail(f"{prefix}: explicit case must use a recognized squad invocation")
            if row["category"] != "explicit" and explicit_invocation:
                fail(f"{prefix}: only explicit cases may use a recognized squad invocation")
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
            fail("dataset needs a formal explicit invocation case")
        if not any(row["prompt"].lstrip().startswith("小分队") for row in rows):
            fail("dataset needs a natural-language explicit invocation case")
        e2e_count = validate_e2e_manifest(set(identifiers))

    except (OSError, ValueError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"validated {len(rows)} cases: "
        f"{triggers['true']} trigger, {triggers['false']} direct; "
        f"categories={dict(sorted(categories.items()))}; "
        f"validated {e2e_count} rich e2e cases"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
