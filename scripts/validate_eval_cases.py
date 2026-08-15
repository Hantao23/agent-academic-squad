#!/usr/bin/env python3
"""Validate static routing cases and E2E manifests without running a model."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "evals" / "trigger-routing.csv"
E2E_MANIFESTS = (
    ROOT / "evals" / "e2e-cases.json",
    ROOT / "evals" / "nature-integration-cases.json",
)
RECEIPT_SCHEMA = ROOT / "evals" / "receipt-schema.json"
REQUIRED_COLUMNS = {
    "id", "category", "expected_host_loaded", "expected_routing_used", "expected_stage", "expected_domain",
    "expected_handling", "expected_external_skill", "constraints", "prompt",
}
ALLOWED_CATEGORIES = {"formal", "shortcut", "implicit", "contextual", "negative", "boundary"}
ALLOWED_STAGES = {"none", "plan", "execute", "review"}
ALLOWED_ROUTE_STAGES = ALLOWED_STAGES | {"search", "read", "write"}
ALLOWED_DOMAINS = {"none", "code_experiment", "mathematics", "paper"}
ALLOWED_HANDLING = {"direct", "subagent", "plan_first"}
ALLOWED_CONSTRAINTS = {
    "none", "read_only", "plan_only", "respect_model_override", "no_file_write",
    "direct_execution", "temporary_plan", "durable_plan", "long_running",
    "temporary_artifacts", "workspace_read_only", "unavailable_model",
    "single_writer", "no_plan_save", "academic_gate", "formal_literal_context",
    "formal_opt_out", "sensitive_no_store",
}
NEGATED_SHORTCUT_PHRASES = (
    "不用小分队", "不要用小分队", "别用小分队", "不要使用小分队",
    "不要交给小分队", "不交给小分队", "别交给小分队",
)
DISCUSSION_ONLY_PHRASES = ("讨论小分队", "关于小分队", "小分队这个名字", "小分队这个称呼")
E2E_EXPECTED_FIELDS = {
    "host_loaded", "routing_used", "stage", "domain", "handling", "subagents",
    "allowed_models", "required_models", "allowed_efforts", "required_efforts",
    "runtime_role_counts", "planned_routes", "invoked_external_skills", "writes", "final_states",
    "forbidden_actions", "required_evidence",
}
E2E_CASE_FIELDS = {
    "id", "source_case_id", "prompt", "sandbox", "expected", "fixture",
    "required_external_skills",
}
ALLOWED_SANDBOXES = {"read-only", "workspace-write"}
ALLOWED_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
ALLOWED_WRITES = {"temporary_plan", "durable_plan", "temporary_artifacts", "workspace"}
ALLOWED_FINAL_STATES = {
    "direct_answer", "plan_ready", "review_complete", "execution_complete",
    "launched", "running", "handoff_ready", "blocked",
}
ALLOWED_FORBIDDEN_ACTIONS = {
    "file_write", "subagent", "artifact_modification", "experiment_execution",
    "literature_search", "manuscript_write", "report_completed", "process_launch",
    "model_substitution",
}
ALLOWED_EVIDENCE = {
    "receipt", "workspace", "trace_turn", "trace_skill", "trace_subagents",
    "trace_routes", "trace_external_skills", "trace_commands",
}
ROUTE_FIELDS = {"stage", "role", "role_kind", "model", "effort", "external_skill"}
ALLOWED_ROLE_KINDS = {"planner", "executor", "reviewer", "searcher", "reader", "writer", "analyst"}


def classify_invocation(prompt: str) -> str:
    """Classify host-formal syntax before interpreting natural-language negation."""
    if "$agent-academic-squad" in prompt:
        return "formal"
    if any(phrase in prompt for phrase in DISCUSSION_ONLY_PHRASES):
        return "discussion"
    if any(phrase in prompt for phrase in NEGATED_SHORTCUT_PHRASES):
        return "negated"
    stripped = prompt.lstrip()
    if stripped.startswith("小分队") or re.search(
        r"交给小分队(?:处理|来做|负责|审查|规划|执行|[，,:：。\s]|$)", prompt
    ):
        return "shortcut"
    return "none"


def has_explicit_invocation(prompt: str) -> bool:
    """Compatibility helper: formal syntax or a positive natural shortcut."""
    return classify_invocation(prompt) in {"formal", "shortcut"}


def fail(message: str) -> None:
    raise ValueError(message)


def require_string_list(value: object, prefix: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        fail(f"{prefix}: expected a list of non-empty strings")
    if len(value) != len(set(value)):
        fail(f"{prefix}: values must be unique")
    return value


def validate_route(route: object, prefix: str) -> None:
    if not isinstance(route, dict) or set(route) != ROUTE_FIELDS:
        fail(f"{prefix}: invalid route fields")
    if route["stage"] not in ALLOWED_ROUTE_STAGES:
        fail(f"{prefix}: invalid route stage")
    if not isinstance(route["role"], str) or not route["role"]:
        fail(f"{prefix}: invalid route role")
    if route["role_kind"] not in ALLOWED_ROLE_KINDS:
        fail(f"{prefix}: invalid route role_kind")
    if not isinstance(route["model"], str) or not route["model"]:
        fail(f"{prefix}: invalid route model")
    if route["effort"] not in ALLOWED_EFFORTS:
        fail(f"{prefix}: invalid route effort")
    if route["external_skill"] is not None and not isinstance(route["external_skill"], str):
        fail(f"{prefix}: invalid route external_skill")


def validate_e2e_manifest(path: Path, source_case_ids: set[str]) -> int:
    with path.open(encoding="utf-8") as source:
        manifest = json.load(source)
    if not isinstance(manifest, dict):
        fail(f"{path.name}: manifest must be an object")
    if set(manifest) != {"suite", "cases"}:
        fail(f"{path.name}: unexpected top-level fields")
    if not isinstance(manifest.get("suite"), str) or not manifest["suite"]:
        fail(f"{path.name}: invalid suite")
    cases = manifest.get("cases")
    minimum = 8 if manifest["suite"] == "core" else 1
    if not isinstance(cases, list) or not minimum <= len(cases) <= 24:
        fail(f"{path.name}: expected {minimum}-24 cases")
    identifiers: set[str] = set()
    for index, case in enumerate(cases, start=1):
        prefix = f"{path.name} case {index}"
        if not isinstance(case, dict) or not set(case) <= E2E_CASE_FIELDS:
            fail(f"{prefix}: unexpected fields")
        required_case_fields = {"id", "source_case_id", "prompt", "sandbox", "expected"}
        if not required_case_fields <= set(case):
            fail(f"{prefix}: missing required fields")
        identifier = case["id"]
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            fail(f"{prefix}: invalid or duplicate id")
        identifiers.add(identifier)
        prefix = f"{path.name} case {identifier}"
        if case["source_case_id"] not in source_case_ids:
            fail(f"{prefix}: unknown source_case_id")
        if not isinstance(case["prompt"], str) or not case["prompt"].strip():
            fail(f"{prefix}: prompt is empty")
        if case["sandbox"] not in ALLOWED_SANDBOXES:
            fail(f"{prefix}: invalid sandbox")
        fixture = case.get("fixture")
        if fixture is not None and (not isinstance(fixture, str) or not (ROOT / "evals" / "fixtures" / fixture).is_dir()):
            fail(f"{prefix}: missing fixture")
        require_string_list(case.get("required_external_skills", []), f"{prefix}.required_external_skills")

        expected = case["expected"]
        if not isinstance(expected, dict) or set(expected) != E2E_EXPECTED_FIELDS:
            fail(f"{prefix}: unexpected expected fields")
        if not isinstance(expected["host_loaded"], bool) or not isinstance(expected["routing_used"], bool):
            fail(f"{prefix}: host_loaded and routing_used must be boolean")
        if expected["routing_used"] and not expected["host_loaded"]:
            fail(f"{prefix}: routing_used requires host_loaded")
        if expected["stage"] not in ALLOWED_STAGES or expected["domain"] not in ALLOWED_DOMAINS:
            fail(f"{prefix}: invalid stage or domain")
        if expected["handling"] not in ALLOWED_HANDLING:
            fail(f"{prefix}: invalid handling")
        allowed_models = require_string_list(expected["allowed_models"], f"{prefix}.allowed_models")
        required_models = require_string_list(expected["required_models"], f"{prefix}.required_models")
        allowed_efforts = require_string_list(expected["allowed_efforts"], f"{prefix}.allowed_efforts")
        required_efforts = require_string_list(expected["required_efforts"], f"{prefix}.required_efforts")
        invoked = require_string_list(expected["invoked_external_skills"], f"{prefix}.invoked_external_skills")
        writes = require_string_list(expected["writes"], f"{prefix}.writes")
        final_states = require_string_list(expected["final_states"], f"{prefix}.final_states")
        forbidden = require_string_list(expected["forbidden_actions"], f"{prefix}.forbidden_actions")
        required_evidence = require_string_list(expected["required_evidence"], f"{prefix}.required_evidence")
        if not set(required_models) <= set(allowed_models):
            fail(f"{prefix}: required_models must be a subset of allowed_models")
        if not set(allowed_efforts) <= ALLOWED_EFFORTS or not set(required_efforts) <= set(allowed_efforts):
            fail(f"{prefix}: invalid effort relationship")
        if not set(writes) <= ALLOWED_WRITES or not set(final_states) <= ALLOWED_FINAL_STATES:
            fail(f"{prefix}: invalid writes or final state")
        if not set(forbidden) <= ALLOWED_FORBIDDEN_ACTIONS:
            fail(f"{prefix}: invalid forbidden action")
        if not set(required_evidence) <= ALLOWED_EVIDENCE:
            fail(f"{prefix}: invalid required evidence")
        if not {"receipt", "workspace", "trace_turn"} <= set(required_evidence):
            fail(f"{prefix}: receipt, workspace, and trace_turn evidence are required")
        routes = expected["planned_routes"]
        if not isinstance(routes, list):
            fail(f"{prefix}: planned_routes must be a list")
        for route_index, route in enumerate(routes, start=1):
            validate_route(route, f"{prefix}.planned_routes[{route_index}]")
        role_counts = expected["runtime_role_counts"]
        if (
            not isinstance(role_counts, dict)
            or not set(role_counts) <= ALLOWED_ROLE_KINDS
            or not all(isinstance(count, int) and count >= 0 for count in role_counts.values())
        ):
            fail(f"{prefix}: invalid runtime_role_counts")
        subagents = expected["subagents"]
        if not isinstance(subagents, dict) or set(subagents) != {"min", "max"}:
            fail(f"{prefix}: invalid subagent bounds")
        minimum_agents, maximum_agents = subagents["min"], subagents["max"]
        if not isinstance(minimum_agents, int) or not isinstance(maximum_agents, int) or not 0 <= minimum_agents <= maximum_agents:
            fail(f"{prefix}: invalid subagent range")
        if not expected["routing_used"]:
            if expected["stage"] != "none" or expected["domain"] != "none" or expected["handling"] != "direct":
                fail(f"{prefix}: inactive case must be none/none/direct")
            if maximum_agents or allowed_models or allowed_efforts or routes or invoked or writes:
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
        if not 20 <= len(rows) <= 60:
            fail(f"expected 20-60 cases, found {len(rows)}")
        identifiers = [row["id"] for row in rows]
        if len(identifiers) != len(set(identifiers)):
            fail("case IDs must be unique")

        triggers: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        for row_number, row in enumerate(rows, start=2):
            prefix = f"row {row_number} ({row['id']})"
            if not row["prompt"].strip() or row["category"] not in ALLOWED_CATEGORIES:
                fail(f"{prefix}: empty prompt or invalid category")
            if row["expected_host_loaded"] not in {"true", "false"} or row["expected_routing_used"] not in {"true", "false"}:
                fail(f"{prefix}: host/routing expectations must be true or false")
            if row["expected_routing_used"] == "true" and row["expected_host_loaded"] != "true":
                fail(f"{prefix}: routing requires host load")
            if row["expected_stage"] not in ALLOWED_STAGES or row["expected_domain"] not in ALLOWED_DOMAINS:
                fail(f"{prefix}: invalid stage or domain")
            if row["expected_handling"] not in ALLOWED_HANDLING:
                fail(f"{prefix}: invalid handling")
            invocation = classify_invocation(row["prompt"])
            if row["category"] == "formal" and invocation != "formal":
                fail(f"{prefix}: formal case lacks formal syntax")
            if row["category"] == "shortcut" and invocation != "shortcut":
                fail(f"{prefix}: shortcut case lacks a positive shortcut")
            if row["category"] not in {"formal", "shortcut"} and invocation in {"formal", "shortcut"}:
                fail(f"{prefix}: formal/shortcut syntax has the wrong category")
            if row["category"] in {"formal", "shortcut"} and row["expected_host_loaded"] != "true":
                fail(f"{prefix}: formal and shortcut cases must request host loading")
            if row["category"] == "shortcut" and row["expected_routing_used"] != "true":
                fail(f"{prefix}: positive shortcuts must use routing")
            constraints = set(row["constraints"].split("|"))
            if not constraints <= ALLOWED_CONSTRAINTS:
                fail(f"{prefix}: invalid constraint")
            if row["expected_routing_used"] == "false":
                if row["expected_stage"] != "none" or row["expected_domain"] != "none" or row["expected_handling"] != "direct":
                    fail(f"{prefix}: inactive cases must be none/none/direct")
                if row["expected_external_skill"]:
                    fail(f"{prefix}: inactive case cannot assign an external skill")
            triggers[row["expected_routing_used"]] += 1
            categories[row["category"]] += 1
        if triggers["true"] < 8 or triggers["false"] < 8:
            fail("dataset needs at least eight positive and eight negative cases")
        missing_categories = ALLOWED_CATEGORIES - set(categories)
        if missing_categories:
            fail(f"missing categories: {sorted(missing_categories)}")
        if classify_invocation("不要使用 $agent-academic-squad") != "formal":
            fail("formal host syntax must take precedence over prose negation")
        e2e_counts = {path.name: validate_e2e_manifest(path, set(identifiers)) for path in E2E_MANIFESTS}
        with RECEIPT_SCHEMA.open(encoding="utf-8") as source:
            schema = json.load(source)
        if schema.get("type") != "object" or "answer" not in schema.get("required", []):
            fail("receipt schema is incomplete")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"validated {len(rows)} static cases: {triggers['true']} routed, {triggers['false']} direct; "
        f"categories={dict(sorted(categories.items()))}; e2e={e2e_counts}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
