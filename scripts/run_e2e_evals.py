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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "evals" / "e2e-cases.json"
RECEIPT_SCHEMA = ROOT / "evals" / "receipt-schema.json"
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_*\-]{8,}")
SKIP_COPY_NAMES = {".git", "__pycache__", "artifacts", "results", "workspaces"}
SNAPSHOT_IGNORED_ROOTS = {".git", ".codex", ".home", ".eval-harness"}
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
`planned_routes`. Use `blocked` and explain why when a
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
    normalized = path.replace("\\", "/")
    if "/agent-academic-squad/plans/" in f"/{normalized}" and normalized.endswith(".md"):
        return "temporary_plan"
    if normalized.startswith(".agents/plans/") and normalized.endswith(".md"):
        return "durable_plan"
    if normalized.startswith(("tmp/", "temporary/")):
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
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("CODEX_API_KEY", None)
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
    models: set[str] = set()
    efforts: set[str] = set()
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

    def inspect_event(value: Any, key: str = "") -> None:
        nonlocal skill_signal
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                lowered = child_key.lower()
                if lowered in {"agentthreadid", "agent_thread_id", "subagent_id"} and isinstance(child_value, str):
                    subagent_ids.add(child_value)
                if lowered == "model" and isinstance(child_value, str):
                    models.add(child_value)
                if lowered in {"effort", "reasoning_effort"} and isinstance(child_value, str):
                    efforts.add(child_value)
                if "skill" in lowered and isinstance(child_value, str):
                    if "agent-academic-squad" in child_value:
                        skill_signal = True
                    invoked_external.update(skill for skill in KNOWN_EXTERNAL_SKILLS if skill in child_value)
                inspect_event(child_value, child_key)
        elif isinstance(value, list):
            for item in value:
                inspect_event(item, key)

    for event in events:
        event_type = str(event.get("type", ""))
        event_types.add(event_type)
        item = event.get("item")
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
        inspect_event(event)

    receipt, receipt_error = parse_receipt(messages)
    changed_paths = behavior_changed_paths(change_map, before, after, include_directories=True)
    write_paths = behavior_changed_paths(change_map, before, after, include_directories=False)
    fixture_changes = [
        path for path in changed_paths if fixture_prefix and (path == fixture_prefix or path.startswith(f"{fixture_prefix}/"))
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
        "models": sorted(models),
        "efforts": sorted(efforts),
        "invoked_external_skills_trace": sorted(invoked_external),
        "web_searches": web_searches,
        "mcp_calls": mcp_calls,
    }


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
    passed: list[str] = []
    failed: list[str] = []
    unverifiable: list[str] = []
    self_report_checks: list[str] = []

    def mark(condition: bool, name: str, detail: str | None = None) -> None:
        (passed if condition else failed).append(name if condition or not detail else f"{name} {detail}")

    def unknown(name: str) -> None:
        unverifiable.append(name)

    receipt = observations.get("receipt")
    changes = observations["changed_files"]
    write_classes = set(observations["write_classes"])
    expected_writes = set(expected.get("writes", []))

    mark(bool(observations["turn_completed"]), "turn_completed")
    mark(
        expected_writes == write_classes,
        "writes",
        f"expected={sorted(expected_writes)} observed={sorted(write_classes)}",
    )

    if receipt is None:
        unknown("receipt")
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
        if receipt.get("skill_used") == expected.get("should_trigger"):
            passed.append("skill_used:self_report")
        else:
            failed.append(
                f"skill_used:self_report expected={expected.get('should_trigger')} observed={receipt.get('skill_used')}"
            )
        self_report_checks.append("skill_used:self_report")

    trace_skill = observations.get("skill_invoked")
    if trace_skill is None:
        unknown("skill_invoked:trace")
    else:
        mark(trace_skill == expected.get("should_trigger"), "skill_invoked:trace")

    bounds = expected.get("subagents", {"min": 0, "max": 0})
    trace_count = observations.get("subagent_count")
    if trace_count is None:
        unknown("subagent_count:trace")
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
            unknown("runtime_role_counts")
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
            if not observed:
                unknown(f"required_{name}:runtime")
            else:
                mark(
                    required <= observed,
                    f"required_{name}:self_report",
                    f"required={sorted(required)} observed={sorted(observed)}",
                )
                self_report_checks.append(f"required_{name}:self_report")

    expected_routes = {route_key(route) for route in expected.get("planned_routes", [])}
    if expected_routes:
        if receipt is None:
            unknown("planned_routes")
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
            unknown("invoked_external_skills:trace")
        else:
            mark(
                expected_invoked <= traced_invoked,
                "invoked_external_skills:trace",
                f"expected={sorted(expected_invoked)} observed={sorted(traced_invoked)}",
            )
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
        unknown(f"forbidden:{action}:unsupported")

    performed = set(receipt.get("performed_actions", [])) if receipt else set()
    commands = observations["commands"]
    if "file_write" in forbidden:
        mark(not changes, "forbidden:file_write")
    if "artifact_modification" in forbidden:
        mark(not observations.get("fixture_changes"), "forbidden:artifact_modification")
    if "process_launch" in forbidden:
        launched = command_contains(commands, ("tmux", "nohup", "systemd-run", "disown"))
        mark(not launched, "forbidden:process_launch")
    if "subagent" in forbidden:
        if trace_count is not None:
            mark(trace_count == 0, "forbidden:subagent")
        elif runtime_agents:
            failed.append("forbidden:subagent self-report declares runtime agents")
        else:
            unknown("forbidden:subagent")
    if "experiment_execution" in forbidden:
        detected = (
            experiment_command_detected(commands)
            or "experiment_execution" in performed
            or bool(receipt and receipt.get("claimed_execution"))
        )
        if detected:
            failed.append("forbidden:experiment_execution")
        elif receipt is None:
            unknown("forbidden:experiment_execution")
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
            unknown("forbidden:literature_search")
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
            unknown("forbidden:manuscript_write")
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
            unknown("forbidden:report_completed")
        else:
            mark(not detected, "forbidden:report_completed")
    if "model_substitution" in forbidden:
        if runtime_agents:
            substituted = bool(allowed_models and not runtime_models <= allowed_models)
            mark(not substituted, "forbidden:model_substitution")
        elif receipt and receipt.get("final_state") == "blocked":
            passed.append("forbidden:model_substitution:self_report")
            self_report_checks.append("forbidden:model_substitution:self_report")
        else:
            unknown("forbidden:model_substitution")

    required_unverifiable = sorted(set(unverifiable))
    status = "fail" if failed else ("inconclusive" if required_unverifiable else "pass")
    return {
        "status": status,
        "passed_checks": sorted(set(passed)),
        "failed_checks": sorted(set(failed)),
        "unverifiable_checks": sorted(set(unverifiable)),
        "required_unverifiable_checks": required_unverifiable,
        "self_report_checks": sorted(set(self_report_checks)),
        "observed_final_states": sorted(observed_states),
    }


def copy_skill(workspace: Path) -> None:
    destination = workspace / ".agents" / "skills" / "agent-academic-squad"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns(*SKIP_COPY_NAMES))


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
    copy_skill(workspace)
    try:
        fixture_prefix = prepare_fixture(case, workspace)
    except OSError as exc:
        return setup_failure_result(case, "fixture", str(exc))
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
        str(workspace / ".agents" / "skills" / "agent-academic-squad" / "evals" / "receipt-schema.json"),
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
