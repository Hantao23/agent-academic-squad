#!/usr/bin/env python3
"""Run isolated Codex JSONL evals with tri-state, evidence-aware results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "evals" / "e2e-cases.json"
RECEIPT_SCHEMA = ROOT / "evals" / "receipt-schema.json"
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_*\-]{8,}")
SNAPSHOT_IGNORED_ROOTS = {".git", ".codex", ".home", ".eval-harness"}
RUNTIME_PACKAGE_PATHS = (
    Path("SKILL.md"),
    Path("agents"),
    Path("references"),
    Path("scripts/plan_cache.py"),
    Path("scripts/radar_snapshot.py"),
)
SAFE_ENV_KEYS = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "CURL_CA_BUNDLE",
    "REQUESTS_CA_BUNDLE",
)
EVIDENCE_KINDS = {
    "receipt",
    "workspace",
    "trace_turn",
    "trace_skill",
    "trace_subagents",
    "trace_routes",
    "trace_external_skills",
    "trace_commands",
}
KNOWN_EXTERNAL_SKILLS = (
    "nature-academic-search",
    "nature-reader",
    "nature-writing",
    "nature-polishing",
    "nature-reviewer",
    "nature-statistics",
    "nature-citation",
    "nature-ref-verifier",
    "nature-downloader",
    "nature-figure",
    "nature-response",
    "grilling",
)
FORBIDDEN_ACTIONS = {
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
EVAL_PROTOCOL = """

[Evaluation protocol]
Return one JSON object matching the supplied output schema. Put the complete
user-facing response in `answer`. Report only what actually happened in
`runtime_agents`, `invoked_external_skills`, and `performed_actions`; use the
most specific `role_kind` for every route; put proposed work only in
`planned_routes`. `host_loaded` means the host loaded this Skill;
`routing_used` means the request passed either implicit academic scope or
explicit opt-in and the Skill's routing behavior was actually used. Use
`blocked` and explain why when required user decisions are still pending or a
requested model or capability is unavailable. This receipt is a self-report
and will be checked against the JSONL trace and workspace artifacts.
""".strip()


def redact(text: str) -> str:
    return SECRET_PATTERN.sub("sk-REDACTED", text)


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("e2e manifest must be an object")
    if not isinstance(payload.get("suite"), str) or not payload["suite"]:
        raise ValueError("e2e manifest suite must be a non-empty string")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("e2e manifest cases must be a list")
    return payload


def parse_jsonl(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    invalid: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            invalid.append(line[:200])
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            invalid.append(line[:200])
    return events, invalid


def environment_failure(exit_code: int, stdout: str, stderr: str, timed_out: bool) -> str | None:
    if timed_out:
        return "timeout"
    combined = f"{stdout}\n{stderr}".lower()
    if any(marker in combined for marker in ("401 unauthorized", "invalid_api_key", "incorrect api key")):
        return "authentication"
    if any(marker in combined for marker in ("failed to connect", "connection refused", "dns error", "tls error")):
        return "network"
    if exit_code != 0 and not stdout.strip():
        return "runner"
    return None


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_workspace(workspace: Path) -> dict[str, dict[str, Any]]:
    """Capture files, directories, modes, and symlink targets without following links."""
    snapshot: dict[str, dict[str, Any]] = {}
    for path in workspace.rglob("*"):
        relative = path.relative_to(workspace)
        if relative.parts and relative.parts[0] in SNAPSHOT_IGNORED_ROOTS:
            continue
        if relative.parts and relative.parts[0] == ".cache":
            managed_cache = (".cache", "agent-academic-squad", "plans")
            if tuple(relative.parts[: min(len(relative.parts), 3)]) != managed_cache[: min(len(relative.parts), 3)]:
                continue
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            entry = {"kind": "symlink", "mode": mode, "target": os.readlink(path)}
        elif stat.S_ISREG(metadata.st_mode):
            entry = {"kind": "file", "mode": mode, "sha256": file_digest(path)}
        elif stat.S_ISDIR(metadata.st_mode):
            entry = {"kind": "directory", "mode": mode}
        else:
            entry = {"kind": "other", "mode": mode}
        snapshot[str(relative)] = entry
    return snapshot


def workspace_changes(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    changes = {
        "created": [],
        "modified": [],
        "deleted": [],
        "type_changed": [],
        "mode_changed": [],
        "symlink_target_changed": [],
    }
    for path in sorted(set(before) | set(after)):
        previous = before.get(path)
        current = after.get(path)
        if previous is None:
            changes["created"].append(path)
            continue
        if current is None:
            changes["deleted"].append(path)
            continue
        if previous["kind"] != current["kind"]:
            changes["type_changed"].append(path)
            continue
        if previous.get("mode") != current.get("mode"):
            changes["mode_changed"].append(path)
        if current["kind"] == "file" and previous.get("sha256") != current.get("sha256"):
            changes["modified"].append(path)
        if current["kind"] == "symlink" and previous.get("target") != current.get("target"):
            changes["symlink_target_changed"].append(path)
    return changes


def changed_files(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> list[str]:
    """Compatibility helper returning the union of all changed paths."""
    changes = workspace_changes(before, after)
    return sorted({path for paths in changes.values() for path in paths})


def classify_write(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/"))
    parts = normalized.parts
    if normalized.is_absolute() or ".." in parts:
        return "workspace"
    if parts[:3] == (".cache", "agent-academic-squad", "plans") and len(parts) > 3 and normalized.suffix.lower() == ".md":
        return "temporary_plan"
    if parts[:2] == (".agents", "plans") and len(parts) > 2 and normalized.suffix.lower() == ".md":
        return "durable_plan"
    if parts and parts[0] in {"tmp", "temporary"} and len(parts) > 1:
        return "temporary_artifacts"
    return "workspace"


def behavior_changed_paths(
    changes: dict[str, list[str]],
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    *,
    include_directories: bool,
) -> list[str]:
    paths = sorted({path for group in changes.values() for path in group})
    if include_directories:
        return paths
    return [
        path
        for path in paths
        if (after.get(path) or before.get(path) or {}).get("kind") != "directory"
    ]


def codex_environment(
    cache_home: Path,
    workspace: Path,
    strict_isolation: bool,
    api_key: str | None,
) -> dict[str, str]:
    environment = {key: os.environ[key] for key in SAFE_ENV_KEYS if os.environ.get(key)}
    if not strict_isolation:
        # Local interactive auth deliberately needs the user's Codex home. Strict
        # isolation replaces both paths and accepts only the selected API key.
        for key in ("HOME", "CODEX_HOME"):
            if os.environ.get(key):
                environment[key] = os.environ[key]
    environment["XDG_CACHE_HOME"] = str(cache_home)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if api_key:
        environment["CODEX_API_KEY"] = api_key
    if strict_isolation:
        isolated_home = workspace / ".home"
        isolated_codex_home = workspace / ".codex"
        isolated_home.mkdir(mode=0o700)
        isolated_codex_home.mkdir(mode=0o700)
        environment["HOME"] = str(isolated_home)
        environment["CODEX_HOME"] = str(isolated_codex_home)
    return environment


def parse_receipt(messages: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    if not messages:
        return None, "missing final agent message"
    try:
        value = json.loads(messages[-1])
    except json.JSONDecodeError as exc:
        return None, f"invalid receipt JSON: {exc.msg}"
    if not isinstance(value, dict):
        return None, "receipt is not an object"
    return value, None


def event_observations(
    events: list[dict[str, Any]],
    changes: dict[str, list[str]] | list[str],
    before: dict[str, dict[str, Any]] | None = None,
    after: dict[str, dict[str, Any]] | None = None,
    fixture_prefix: str | None = None,
) -> dict[str, Any]:
    commands: list[str] = []
    messages: list[str] = []
    subagent_ids: set[str] = set()
    event_types: set[str] = set()
    diagnostic_models: set[str] = set()
    diagnostic_efforts: set[str] = set()
    attributed_routes: dict[str, dict[str, set[str]]] = {}
    invoked_external: set[str] = set()
    skill_signal: bool | None = None
    web_searches = 0
    mcp_calls = 0

    if isinstance(changes, list):
        change_map = {
            "created": list(changes),
            "modified": [],
            "deleted": [],
            "type_changed": [],
            "mode_changed": [],
            "symlink_target_changed": [],
        }
    else:
        change_map = changes
    before = before or {}
    after = after or {}

    def values_for_keys(value: Any, wanted: set[str]) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                if child_key.lower() in wanted and isinstance(child_value, str):
                    found.add(child_value)
                found.update(values_for_keys(child_value, wanted))
        elif isinstance(value, list):
            for child in value:
                found.update(values_for_keys(child, wanted))
        return found

    def inspect_event(value: Any) -> None:
        nonlocal skill_signal
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                lowered = child_key.lower()
                if lowered == "model" and isinstance(child_value, str):
                    diagnostic_models.add(child_value)
                if lowered in {"effort", "reasoning_effort"} and isinstance(child_value, str):
                    diagnostic_efforts.add(child_value)
                if "skill" in lowered and isinstance(child_value, str):
                    if "agent-academic-squad" in child_value:
                        skill_signal = True
                    invoked_external.update(skill for skill in KNOWN_EXTERNAL_SKILLS if skill in child_value)
                inspect_event(child_value)
        elif isinstance(value, list):
            for item in value:
                inspect_event(item)

    for event_index, event in enumerate(events):
        event_type = str(event.get("type", ""))
        event_types.add(event_type)
        item = event.get("item")
        item_type = ""
        if isinstance(item, dict):
            item_type = str(item.get("type", ""))
            event_types.add(item_type)
            serialized_item = json.dumps(item, ensure_ascii=False).lower()
            if item_type == "command_execution" and isinstance(item.get("command"), str):
                commands.append(item["command"])
            elif item_type == "agent_message" and isinstance(item.get("text"), str):
                messages.append(item["text"])
            if "subagent" in item_type.lower() or "collab" in item_type.lower():
                subagent_ids.add(str(item.get("id", f"event-{len(subagent_ids)}")))
            if "skill" in item_type.lower():
                if "agent-academic-squad" in serialized_item:
                    skill_signal = True
                invoked_external.update(skill for skill in KNOWN_EXTERNAL_SKILLS if skill in serialized_item)
            if item_type == "web_search":
                web_searches += 1
            if item_type == "mcp_tool_call":
                mcp_calls += 1
                invoked_external.update(skill for skill in KNOWN_EXTERNAL_SKILLS if skill in serialized_item)
        explicit_ids = values_for_keys(event, {"agentthreadid", "agent_thread_id", "subagent_id"})
        is_attributed_subagent_event = bool(explicit_ids) or "subagent" in item_type.lower() or "collab" in item_type.lower()
        if is_attributed_subagent_event:
            route_ids = explicit_ids or {
                str(item.get("id")) if isinstance(item, dict) and item.get("id") else f"event-{event_index}"
            }
            route_models = values_for_keys(event, {"model"})
            route_efforts = values_for_keys(event, {"effort", "reasoning_effort"})
            for route_id in route_ids:
                subagent_ids.add(route_id)
                route = attributed_routes.setdefault(route_id, {"models": set(), "efforts": set()})
                route["models"].update(route_models)
                route["efforts"].update(route_efforts)
        inspect_event(event)

    receipt, receipt_error = parse_receipt(messages)
    changed_paths = behavior_changed_paths(change_map, before, after, include_directories=True)
    write_paths = behavior_changed_paths(change_map, before, after, include_directories=False)
    fixture_changes = [
        path for path in changed_paths if fixture_prefix and (path == fixture_prefix or path.startswith(f"{fixture_prefix}/"))
    ]
    trace_runtime_routes = [
        {
            "id": route_id,
            "models": sorted(route["models"]),
            "efforts": sorted(route["efforts"]),
        }
        for route_id, route in sorted(attributed_routes.items())
    ]
    return {
        "event_types": sorted(event_types),
        "turn_completed": any(event.get("type") == "turn.completed" for event in events),
        "turn_failed": any(event.get("type") == "turn.failed" for event in events),
        "commands": commands,
        "command_trace_available": bool(events),
        "workspace_changes": change_map,
        "changed_files": changed_paths,
        "write_classes": sorted({classify_write(path) for path in write_paths}),
        "fixture_changes": fixture_changes,
        "final_message": receipt.get("answer", "") if receipt else (messages[-1] if messages else ""),
        "receipt": receipt,
        "receipt_error": receipt_error,
        "skill_invoked": skill_signal,
        "subagent_count": len(subagent_ids) if subagent_ids else None,
        # Generic model/effort keys can belong to the controller. Keep them only
        # for diagnostics; route checks use explicitly attributable records.
        "diagnostic_models": sorted(diagnostic_models),
        "diagnostic_efforts": sorted(diagnostic_efforts),
        "trace_runtime_routes": trace_runtime_routes,
        "invoked_external_skills_trace": sorted(invoked_external),
        "web_searches": web_searches,
        "mcp_calls": mcp_calls,
    }


def receipt_semantic_errors(receipt: dict[str, Any]) -> list[str]:
    """Check relationships that JSON Schema cannot express reliably."""
    errors: list[str] = []
    state = receipt.get("final_state")
    task_completed = receipt.get("task_completed")
    claimed_execution = receipt.get("claimed_execution")
    blocked_reason = receipt.get("blocked_reason")
    runtime_agents = receipt.get("runtime_agents", [])
    performed = set(receipt.get("performed_actions", []))
    host_loaded = receipt.get("host_loaded")
    routing_used = receipt.get("routing_used")
    stage = receipt.get("stage")
    domain = receipt.get("domain")
    handling = receipt.get("handling")

    if routing_used is True and host_loaded is not True:
        errors.append("routing_requires_host_load")
    if routing_used is False and (stage != "none" or domain != "none" or handling != "direct"):
        errors.append("inactive_routing_requires_none_none_direct")
    if routing_used is False and runtime_agents:
        errors.append("inactive_routing_cannot_have_runtime_agents")
    if routing_used is True and (stage == "none" or domain == "none"):
        errors.append("active_routing_requires_task_classification")

    completed_states = {"direct_answer", "plan_ready", "review_complete", "execution_complete", "handoff_ready"}
    active_states = {"launched", "running"}
    if state in completed_states and task_completed is not True:
        errors.append("completed_state_requires_task_completed")
    if state in active_states and task_completed is not False:
        errors.append("active_state_cannot_be_task_completed")
    if state == "blocked":
        if task_completed is not False:
            errors.append("blocked_cannot_be_task_completed")
        if not isinstance(blocked_reason, str) or not blocked_reason.strip():
            errors.append("blocked_requires_reason")
    elif blocked_reason not in (None, ""):
        errors.append("nonblocked_cannot_have_blocked_reason")

    if state == "execution_complete" and claimed_execution is not True:
        errors.append("execution_complete_requires_claimed_execution")
    if state in {"direct_answer", "plan_ready", "review_complete", "handoff_ready"} and claimed_execution is not False:
        errors.append("nonexecution_state_cannot_claim_execution")
    execution_actions = {"artifact_modification", "experiment_execution", "manuscript_write", "report_completed", "process_launch"}
    if performed & execution_actions and claimed_execution is not True:
        errors.append("execution_action_requires_claimed_execution")
    if "subagent" in performed and not runtime_agents:
        errors.append("subagent_action_requires_runtime_agent")
    if runtime_agents and "subagent" not in performed:
        errors.append("runtime_agent_requires_subagent_action")
    return sorted(set(errors))


def detect_final_state(text: str) -> set[str]:
    """Parse only a structured receipt; do not infer readiness from prose keywords."""
    try:
        receipt = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return set()
    state = receipt.get("final_state") if isinstance(receipt, dict) else None
    return {state} if isinstance(state, str) else set()


def command_contains(commands: Iterable[str], patterns: tuple[str, ...]) -> bool:
    return any(any(pattern in command.lower() for pattern in patterns) for command in commands)


def experiment_command_detected(commands: Iterable[str]) -> bool:
    patterns = (
        re.compile(r"\b(?:python\d*|uv\s+run|bash|sh)\b[^\n]*(?:run[_-]?experiment|train(?:\.py)?|benchmark(?:\.py)?)", re.I),
        re.compile(r"\b(?:snakemake|nextflow)\b", re.I),
    )
    return any(any(pattern.search(command) for pattern in patterns) for command in commands)


def route_key(route: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(route.get("stage", "")),
        str(route.get("role", "")),
        str(route.get("role_kind", "")),
        str(route.get("model", "")),
        str(route.get("effort", "")),
        str(route.get("external_skill") or ""),
    )


def evaluate_observations(case: dict[str, Any], observations: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    required_evidence = set(expected.get("required_evidence", []))
    if not required_evidence <= EVIDENCE_KINDS:
        raise ValueError(f"unknown evidence kinds: {sorted(required_evidence - EVIDENCE_KINDS)}")
    passed: list[str] = []
    failed: list[str] = []
    unverifiable: list[str] = []
    required_unverifiable: list[str] = []
    self_report_checks: list[str] = []

    def mark(condition: bool, name: str, detail: str | None = None) -> None:
        (passed if condition else failed).append(name if condition or not detail else f"{name} {detail}")

    def unknown(name: str, evidence: str) -> None:
        unverifiable.append(name)
        if evidence in required_evidence:
            required_unverifiable.append(name)

    receipt = observations.get("receipt")
    changes = observations["changed_files"]
    write_classes = set(observations["write_classes"])
    expected_writes = set(expected.get("writes", []))

    if observations["turn_completed"]:
        passed.append("turn_completed")
    elif observations.get("turn_failed"):
        failed.append("turn_completed trace contains turn.failed")
    else:
        unknown("turn_completed", "trace_turn")
    mark(
        expected_writes == write_classes,
        "writes",
        f"expected={sorted(expected_writes)} observed={sorted(write_classes)}",
    )

    if receipt is None:
        unknown("receipt", "receipt")
        observed_states: set[str] = set()
    else:
        observed_states = {str(receipt.get("final_state", ""))} - {""}
        wanted_states = set(expected.get("final_states", []))
        mark(
            bool(observed_states & wanted_states),
            "final_state",
            f"expected={sorted(wanted_states)} observed={sorted(observed_states)}",
        )
        self_report_checks.append("final_state")
        for field in ("stage", "domain", "handling"):
            mark(
                receipt.get(field) == expected.get(field),
                field,
                f"expected={expected.get(field)!r} observed={receipt.get(field)!r}",
            )
            self_report_checks.append(field)
        for field in ("host_loaded", "routing_used"):
            mark(
                receipt.get(field) == expected.get(field),
                f"{field}:self_report",
                f"expected={expected.get(field)!r} observed={receipt.get(field)!r}",
            )
            self_report_checks.append(f"{field}:self_report")
        for error in receipt_semantic_errors(receipt):
            failed.append(f"receipt_semantics:{error}")

    trace_skill = observations.get("skill_invoked")
    if trace_skill is None:
        unknown("skill_invoked:trace", "trace_skill")
    else:
        mark(trace_skill == expected.get("host_loaded"), "skill_invoked:trace")

    bounds = expected.get("subagents", {"min": 0, "max": 0})
    trace_count = observations.get("subagent_count")
    if trace_count is None:
        unknown("subagent_count:trace", "trace_subagents")
    else:
        mark(
            bounds["min"] <= trace_count <= bounds["max"],
            "subagent_count:trace",
            f"expected={bounds} observed={trace_count}",
        )

    runtime_agents = receipt.get("runtime_agents", []) if receipt else []
    expected_role_counts = expected.get("runtime_role_counts", {})
    if expected_role_counts:
        if receipt is None:
            unknown("runtime_role_counts", "receipt")
        else:
            observed_role_counts = {
                role: sum(agent.get("role_kind") == role for agent in runtime_agents)
                for role in expected_role_counts
            }
            mark(
                observed_role_counts == expected_role_counts,
                "runtime_role_counts:self_report",
                f"expected={expected_role_counts} observed={observed_role_counts}",
            )
            self_report_checks.append("runtime_role_counts:self_report")
    runtime_models = {str(agent.get("model")) for agent in runtime_agents if agent.get("model")}
    runtime_efforts = {str(agent.get("effort")) for agent in runtime_agents if agent.get("effort")}
    allowed_models = set(expected.get("allowed_models", []))
    required_models = set(expected.get("required_models", []))
    allowed_efforts = set(expected.get("allowed_efforts", []))
    required_efforts = set(expected.get("required_efforts", []))

    for name, observed, allowed, required in (
        ("models", runtime_models, allowed_models, required_models),
        ("efforts", runtime_efforts, allowed_efforts, required_efforts),
    ):
        if allowed:
            mark(
                observed <= allowed,
                f"allowed_{name}:self_report",
                f"allowed={sorted(allowed)} observed={sorted(observed)}",
            )
            self_report_checks.append(f"allowed_{name}:self_report")
        if required:
            if receipt is None:
                unknown(f"required_{name}:self_report", "receipt")
            else:
                mark(
                    required <= observed,
                    f"required_{name}:self_report",
                    f"required={sorted(required)} observed={sorted(observed)}",
                )
                self_report_checks.append(f"required_{name}:self_report")

    trace_routes = observations.get("trace_runtime_routes", [])
    trace_models = {
        model for route in trace_routes for model in route.get("models", [])
    }
    trace_efforts = {
        effort for route in trace_routes for effort in route.get("efforts", [])
    }
    if allowed_models or required_models or "trace_routes" in required_evidence:
        if trace_models:
            if allowed_models:
                mark(
                    trace_models <= allowed_models,
                    "allowed_models:trace",
                    f"allowed={sorted(allowed_models)} observed={sorted(trace_models)}",
                )
            if required_models:
                mark(
                    required_models <= trace_models,
                    "required_models:trace",
                    f"required={sorted(required_models)} observed={sorted(trace_models)}",
                )
            if receipt is not None:
                mark(
                    trace_models == runtime_models,
                    "models:receipt_trace_consistency",
                    f"receipt={sorted(runtime_models)} trace={sorted(trace_models)}",
                )
        else:
            unknown("runtime_models:trace", "trace_routes")
    if allowed_efforts or required_efforts or "trace_routes" in required_evidence:
        if trace_efforts:
            if allowed_efforts:
                mark(
                    trace_efforts <= allowed_efforts,
                    "allowed_efforts:trace",
                    f"allowed={sorted(allowed_efforts)} observed={sorted(trace_efforts)}",
                )
            if required_efforts:
                mark(
                    required_efforts <= trace_efforts,
                    "required_efforts:trace",
                    f"required={sorted(required_efforts)} observed={sorted(trace_efforts)}",
                )
            if receipt is not None:
                mark(
                    trace_efforts == runtime_efforts,
                    "efforts:receipt_trace_consistency",
                    f"receipt={sorted(runtime_efforts)} trace={sorted(trace_efforts)}",
                )
        else:
            unknown("runtime_efforts:trace", "trace_routes")
    attributable_pairs = [
        (route["models"][0], route["efforts"][0])
        for route in trace_routes
        if len(route.get("models", [])) == 1 and len(route.get("efforts", [])) == 1
    ]
    if receipt is not None and trace_routes and len(attributable_pairs) == len(trace_routes):
        reported_pairs = Counter(
            (str(agent.get("model")), str(agent.get("effort")))
            for agent in runtime_agents
            if agent.get("model") and agent.get("effort")
        )
        mark(
            Counter(attributable_pairs) == reported_pairs,
            "runtime_routes:receipt_trace_consistency",
            f"receipt={dict(reported_pairs)} trace={dict(Counter(attributable_pairs))}",
        )

    expected_routes = {route_key(route) for route in expected.get("planned_routes", [])}
    if expected_routes:
        if receipt is None:
            unknown("planned_routes", "receipt")
        else:
            observed_routes = {route_key(route) for route in receipt.get("planned_routes", [])}
            mark(
                expected_routes <= observed_routes,
                "planned_routes:self_report",
                f"expected={sorted(expected_routes)} observed={sorted(observed_routes)}",
            )
            self_report_checks.append("planned_routes:self_report")

    expected_invoked = set(expected.get("invoked_external_skills", []))
    traced_invoked = set(observations.get("invoked_external_skills_trace", []))
    if expected_invoked:
        if not traced_invoked:
            unknown("invoked_external_skills:trace", "trace_external_skills")
        else:
            mark(
                expected_invoked <= traced_invoked,
                "invoked_external_skills:trace",
                f"expected={sorted(expected_invoked)} observed={sorted(traced_invoked)}",
            )
    elif traced_invoked:
        mark(False, "invoked_external_skills:trace", f"expected=[] observed={sorted(traced_invoked)}")
    if receipt is not None:
        reported_invoked = set(receipt.get("invoked_external_skills", []))
        mark(
            reported_invoked == expected_invoked,
            "invoked_external_skills:self_report",
            f"expected={sorted(expected_invoked)} observed={sorted(reported_invoked)}",
        )
        self_report_checks.append("invoked_external_skills:self_report")

    forbidden = set(expected.get("forbidden_actions", []))
    unknown_forbidden = forbidden - FORBIDDEN_ACTIONS
    for action in sorted(unknown_forbidden):
        unknown(f"forbidden:{action}:unsupported", "receipt")

    performed = set(receipt.get("performed_actions", [])) if receipt else set()
    commands = observations["commands"]
    if "file_write" in forbidden:
        mark(not changes, "forbidden:file_write")
    if "artifact_modification" in forbidden:
        mark(not observations.get("fixture_changes"), "forbidden:artifact_modification")
    if "process_launch" in forbidden:
        launched = command_contains(commands, ("tmux", "nohup", "systemd-run", "disown"))
        if observations.get("command_trace_available"):
            mark(not launched, "forbidden:process_launch")
        else:
            unknown("forbidden:process_launch", "trace_commands")
    if "subagent" in forbidden:
        if trace_count is not None:
            mark(trace_count == 0, "forbidden:subagent")
        elif runtime_agents:
            failed.append("forbidden:subagent self-report declares runtime agents")
        else:
            unknown("forbidden:subagent", "trace_subagents")
    if "experiment_execution" in forbidden:
        detected = (
            experiment_command_detected(commands)
            or "experiment_execution" in performed
            or bool(receipt and receipt.get("claimed_execution"))
        )
        if detected:
            failed.append("forbidden:experiment_execution")
        elif receipt is None:
            unknown("forbidden:experiment_execution:self_report", "receipt")
        elif not observations.get("command_trace_available"):
            unknown("forbidden:experiment_execution:trace", "trace_commands")
        else:
            passed.append("forbidden:experiment_execution")
    if "literature_search" in forbidden:
        detected = (
            observations.get("web_searches", 0) > 0
            or "nature-academic-search" in observations.get("invoked_external_skills_trace", [])
            or command_contains(commands, ("crossref", "pubmed", "arxiv", "scholar"))
            or "literature_search" in performed
        )
        if detected:
            failed.append("forbidden:literature_search")
        elif receipt is None:
            unknown("forbidden:literature_search:self_report", "receipt")
        elif not observations.get("command_trace_available"):
            unknown("forbidden:literature_search:trace", "trace_commands")
        else:
            passed.append("forbidden:literature_search")
    if "manuscript_write" in forbidden:
        manuscript_paths = [
            path for path in changes if re.search(r"(?:manuscript|paper|article|draft|\.tex$|\.docx$)", path, re.I)
        ]
        detected = bool(manuscript_paths) or "manuscript_write" in performed
        if detected:
            failed.append("forbidden:manuscript_write")
        elif receipt is None:
            unknown("forbidden:manuscript_write", "receipt")
        else:
            passed.append("forbidden:manuscript_write")
    if "report_completed" in forbidden:
        detected = bool(
            receipt
            and (
                receipt.get("final_state") == "execution_complete"
                or "report_completed" in performed
                or (receipt.get("task_completed") and receipt.get("claimed_execution"))
            )
        )
        if receipt is None:
            unknown("forbidden:report_completed", "receipt")
        else:
            mark(not detected, "forbidden:report_completed")
    if "model_substitution" in forbidden:
        if trace_models:
            substituted = bool(allowed_models and not trace_models <= allowed_models)
            mark(not substituted, "forbidden:model_substitution:trace")
        elif runtime_agents:
            substituted = bool(allowed_models and not runtime_models <= allowed_models)
            mark(not substituted, "forbidden:model_substitution:self_report")
            self_report_checks.append("forbidden:model_substitution:self_report")
        elif receipt and receipt.get("final_state") == "blocked":
            passed.append("forbidden:model_substitution:self_report")
            self_report_checks.append("forbidden:model_substitution:self_report")
        else:
            unknown("forbidden:model_substitution", "trace_routes")

    required_unverifiable = sorted(set(required_unverifiable))
    optional_unverifiable = sorted(set(unverifiable) - set(required_unverifiable))
    status = "fail" if failed else ("inconclusive" if required_unverifiable else "pass")
    return {
        "status": status,
        "passed_checks": sorted(set(passed)),
        "failed_checks": sorted(set(failed)),
        "unverifiable_checks": sorted(set(unverifiable)),
        "required_unverifiable_checks": required_unverifiable,
        "optional_unverifiable_checks": optional_unverifiable,
        "required_evidence": sorted(required_evidence),
        "self_report_checks": sorted(set(self_report_checks)),
        "observed_final_states": sorted(observed_states),
    }


def runtime_package_files() -> list[tuple[Path, Path]]:
    """Return only runtime files; eval answers and harness code stay invisible."""
    files: list[tuple[Path, Path]] = []
    for relative in RUNTIME_PACKAGE_PATHS:
        source = ROOT / relative
        if not source.exists():
            raise FileNotFoundError(f"runtime package path missing: {source}")
        if source.is_symlink():
            raise ValueError(f"runtime package cannot contain symlinks: {source}")
        candidates = [source] if source.is_file() else sorted(path for path in source.rglob("*") if path.is_file())
        for candidate in candidates:
            if candidate.is_symlink():
                raise ValueError(f"runtime package cannot contain symlinks: {candidate}")
            files.append((candidate, candidate.relative_to(ROOT)))
    return files


def copy_skill(workspace: Path) -> Path:
    destination = workspace / ".agents" / "skills" / "agent-academic-squad"
    destination.mkdir(parents=True, exist_ok=False)
    for source, relative in runtime_package_files():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def prepare_eval_harness(workspace: Path) -> Path:
    harness = workspace / ".eval-harness"
    harness.mkdir(mode=0o700)
    schema = harness / "receipt-schema.json"
    shutil.copy2(RECEIPT_SCHEMA, schema)
    schema.chmod(0o600)
    return schema


def prepare_fixture(case: dict[str, Any], workspace: Path) -> str | None:
    fixture = case.get("fixture")
    if not fixture:
        return None
    source = ROOT / "evals" / "fixtures" / fixture
    if not source.is_dir():
        raise FileNotFoundError(f"fixture not found: {source}")
    relative = Path("fixtures") / fixture
    shutil.copytree(source, workspace / relative)
    return str(relative)


def install_external_skills(
    case: dict[str, Any], workspace: Path, external_skill_roots: list[Path]
) -> list[str]:
    missing: list[str] = []
    destination_root = workspace / ".agents" / "skills"
    for skill in case.get("required_external_skills", []):
        source = next((root / skill for root in external_skill_roots if (root / skill / "SKILL.md").is_file()), None)
        if source is None:
            missing.append(skill)
            continue
        shutil.copytree(source, destination_root / skill, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    return missing


def run_case(
    case: dict[str, Any],
    run_root: Path,
    codex_binary: str,
    timeout: int,
    strict_isolation: bool,
    api_key: str | None,
    external_skill_roots: list[Path] | None = None,
) -> dict[str, Any]:
    case_id = case["id"]
    workspace = run_root / "workspaces" / case_id
    workspace.mkdir(parents=True, exist_ok=False)
    try:
        copy_skill(workspace)
        receipt_schema = prepare_eval_harness(workspace)
        fixture_prefix = prepare_fixture(case, workspace)
    except (OSError, ValueError) as exc:
        return setup_failure_result(case, "setup", str(exc))
    missing_skills = install_external_skills(case, workspace, external_skill_roots or [])
    if missing_skills:
        return setup_failure_result(case, "missing_external_skill", ", ".join(missing_skills))
    cache_home = workspace / ".cache"
    cache_home.mkdir(mode=0o700)
    before = snapshot_workspace(workspace)
    prompt = f"{case['prompt']}\n\n{EVAL_PROTOCOL}"
    command = [
        codex_binary,
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        case["sandbox"],
        "--output-schema",
        str(receipt_schema),
        "-C",
        str(workspace),
        prompt,
    ]
    environment = codex_environment(cache_home, workspace, strict_isolation, api_key)
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=environment,
            check=False,
        )
        exit_code = completed.returncode
        stdout = redact(completed.stdout)
        stderr = redact(completed.stderr)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = redact(exc.stdout or "")
        stderr = redact(exc.stderr or "")
    except OSError as exc:
        exit_code = 127
        stdout = ""
        stderr = redact(f"{type(exc).__name__}: {exc}")

    events, invalid_lines = parse_jsonl(stdout)
    after = snapshot_workspace(workspace)
    changes = workspace_changes(before, after)
    observations = event_observations(events, changes, before, after, fixture_prefix)
    failure = environment_failure(exit_code, stdout, stderr, timed_out)
    artifact_dir = run_root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / f"{case_id}.jsonl").write_text(stdout, encoding="utf-8")
    (artifact_dir / f"{case_id}.stderr.txt").write_text(stderr, encoding="utf-8")
    if observations.get("receipt") is not None:
        (artifact_dir / f"{case_id}.receipt.json").write_text(
            json.dumps(observations["receipt"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    evaluation = (
        {
            "status": "inconclusive",
            "passed_checks": [],
            "failed_checks": [],
            "unverifiable_checks": ["environment_failure"],
            "required_unverifiable_checks": ["environment_failure"],
            "optional_unverifiable_checks": [],
            "required_evidence": sorted(case.get("expected", {}).get("required_evidence", [])),
            "self_report_checks": [],
            "observed_final_states": [],
        }
        if failure
        else evaluate_observations(case, observations)
    )
    return {
        "id": case_id,
        "source_case_id": case["source_case_id"],
        "command": command[:-1] + ["<prompt>"],
        "exit_code": exit_code,
        "environment_failure": failure,
        "invalid_jsonl_lines": invalid_lines,
        "observations": observations,
        "evaluation": evaluation,
    }


def setup_failure_result(case: dict[str, Any], failure: str, detail: str) -> dict[str, Any]:
    return {
        "id": case["id"],
        "source_case_id": case["source_case_id"],
        "command": [],
        "exit_code": 2,
        "environment_failure": failure,
        "environment_failure_detail": detail,
        "invalid_jsonl_lines": [],
        "observations": {},
        "evaluation": {
            "status": "inconclusive",
            "passed_checks": [],
            "failed_checks": [],
            "unverifiable_checks": ["environment_failure"],
            "required_unverifiable_checks": ["environment_failure"],
            "optional_unverifiable_checks": [],
            "required_evidence": sorted(case.get("expected", {}).get("required_evidence", [])),
            "self_report_checks": [],
            "observed_final_states": [],
        },
    }


def command_output(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr).strip()
    return redact(output) if output else None


def git_commit() -> str | None:
    return command_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"])


def provenance(manifest_path: Path) -> dict[str, Any]:
    return {
        "runner_commit": git_commit(),
        "runner_sha256": file_digest(Path(__file__)),
        "manifest_sha256": file_digest(manifest_path),
        "platform": platform.platform(),
    }


def outcome_exit_code(environment_failures: int, failed: int, inconclusive: int, strict: bool) -> int:
    if environment_failures:
        return 2
    if failed or (strict and inconclusive):
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--case", action="append", dest="case_ids", default=[])
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--codex", default="codex", help="Codex CLI executable")
    parser.add_argument("--run-id", help="Output run identifier")
    parser.add_argument("--external-skill-root", type=Path, action="append", default=[])
    parser.add_argument(
        "--strict-isolation",
        action="store_true",
        help="Use isolated HOME/CODEX_HOME; requires CODEX_API_KEY",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero for inconclusive as well as failed cases",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0 or (args.max_cases is not None and args.max_cases <= 0):
        parser.error("timeout and max-cases must be positive")

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2
    cases = manifest["cases"]
    if args.list:
        for case in cases:
            print(case["id"])
        return 0
    if args.case_ids:
        requested = set(args.case_ids)
        selected = [case for case in cases if case["id"] in requested]
        missing = requested - {case["id"] for case in selected}
        if missing:
            print(f"unknown cases: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
        cases = selected
    if args.max_cases is not None:
        cases = cases[: args.max_cases]
    if args.dry_run:
        print(json.dumps({"suite": manifest["suite"], "case_ids": [case["id"] for case in cases]}, indent=2))
        return 0

    api_key = os.environ.pop("CODEX_API_KEY", None)
    if args.strict_isolation and not api_key:
        print("strict isolation requires CODEX_API_KEY", file=sys.stderr)
        return 2
    if not RECEIPT_SCHEMA.is_file():
        print(f"missing receipt schema: {RECEIPT_SCHEMA}", file=sys.stderr)
        return 2

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = ROOT / "evals" / "results" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    results = [
        run_case(
            case,
            run_root,
            args.codex,
            args.timeout,
            args.strict_isolation,
            api_key,
            args.external_skill_root,
        )
        for case in cases
    ]
    environment_failures = sum(result["environment_failure"] is not None for result in results)
    statuses = {status: 0 for status in ("pass", "fail", "inconclusive")}
    for result in results:
        if result["environment_failure"] is None:
            statuses[result["evaluation"]["status"]] += 1
    totals = {
        "selected": len(results),
        "environment_failures": environment_failures,
        "passed": statuses["pass"],
        "failed": statuses["fail"],
        "inconclusive": statuses["inconclusive"],
    }
    summary = {
        "suite": manifest["suite"],
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance(args.manifest),
        "cases": results,
        "totals": totals,
    }
    summary_path = run_root / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), **totals}, ensure_ascii=False))
    return outcome_exit_code(environment_failures, statuses["fail"], statuses["inconclusive"], args.strict)


if __name__ == "__main__":
    sys.exit(main())
