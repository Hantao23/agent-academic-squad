#!/usr/bin/env python3
"""Run isolated Codex JSONL smoke evals and summarize observable behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "evals" / "e2e-cases.json"
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_*\-]{8,}")
SKIP_COPY_NAMES = {".git", "__pycache__", "artifacts", "results", "workspaces"}


def redact(text: str) -> str:
    return SECRET_PATTERN.sub("sk-REDACTED", text)


def load_manifest(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported e2e manifest schema")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("e2e manifest cases must be a list")
    return cases


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


def snapshot_workspace(workspace: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    skill_root = workspace / ".agents" / "skills"
    for path in workspace.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(workspace)
        if relative.parts and relative.parts[0] in {".codex", ".home"}:
            continue
        try:
            path.relative_to(skill_root)
            continue
        except ValueError:
            pass
        snapshot[str(relative)] = file_digest(path)
    return snapshot


def classify_write(path: str) -> str:
    normalized = path.replace("\\", "/")
    if "/agent-academic-squad/plans/" in f"/{normalized}" and normalized.endswith(".md"):
        return "temporary_plan"
    if normalized.startswith(".agents/plans/") and normalized.endswith(".md"):
        return "durable_plan"
    if normalized.startswith("tmp/") or normalized.startswith("temporary/"):
        return "temporary_artifacts"
    return "workspace"


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(path for path, digest in after.items() if before.get(path) != digest)


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


def event_observations(events: list[dict[str, Any]], changed: list[str]) -> dict[str, Any]:
    commands: list[str] = []
    messages: list[str] = []
    subagent_ids: set[str] = set()
    event_types: set[str] = set()
    models: set[str] = set()
    efforts: set[str] = set()
    skill_signal = False

    def walk(value: Any, key: str = "") -> None:
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
                if "skill" in lowered and "agent-academic-squad" in str(child_value):
                    skill_signal = True
                walk(child_value, child_key)
        elif isinstance(value, list):
            for item in value:
                walk(item, key)

    for event in events:
        event_type = str(event.get("type", ""))
        event_types.add(event_type)
        item = event.get("item")
        if isinstance(item, dict):
            item_type = str(item.get("type", ""))
            event_types.add(item_type)
            if item_type == "command_execution" and isinstance(item.get("command"), str):
                commands.append(item["command"])
            if item_type == "agent_message" and isinstance(item.get("text"), str):
                messages.append(item["text"])
            if "subagent" in item_type.lower() or "collab" in item_type.lower():
                subagent_ids.add(str(item.get("id", f"event-{len(subagent_ids)}")))
            if "skill" in item_type.lower() and "agent-academic-squad" in json.dumps(item, ensure_ascii=False):
                skill_signal = True
        walk(event)

    serialized = json.dumps(events, ensure_ascii=False).lower()
    external_skills = sorted(
        skill
        for skill in (
            "nature-academic-search",
            "nature-reader",
            "nature-writing",
            "nature-polishing",
            "nature-reviewer",
            "nature-statistics",
        )
        if skill in serialized or any(skill in message.lower() for message in messages)
    )
    return {
        "event_types": sorted(event_types),
        "turn_completed": any(event.get("type") == "turn.completed" for event in events),
        "turn_failed": any(event.get("type") == "turn.failed" for event in events),
        "commands": commands,
        "changed_files": changed,
        "write_classes": sorted({classify_write(path) for path in changed}),
        "final_message": messages[-1] if messages else "",
        "skill_invoked": True if skill_signal else None,
        "subagent_count": len(subagent_ids) if subagent_ids else None,
        "models": sorted(models),
        "efforts": sorted(efforts),
        "external_skills": external_skills,
    }


def detect_final_state(text: str) -> set[str]:
    lowered = text.lower()
    states: set[str] = set()
    if text.strip():
        states.add("direct_answer")
    if any(marker in lowered for marker in ("plan", "计划")):
        states.add("plan_ready")
    if any(marker in lowered for marker in ("review", "finding", "审查", "结论", "invalid step")):
        states.add("review_complete")
    if any(marker in lowered for marker in ("launched", "已启动")):
        states.add("launched")
    if any(marker in lowered for marker in ("running", "运行中")):
        states.add("running")
    if all(marker in lowered for marker in ("tmux", "log")) or all(marker in lowered for marker in ("tmux", "日志")):
        states.add("handoff_ready")
    return states


def evaluate_observations(case: dict[str, Any], observations: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    passed: list[str] = []
    failed: list[str] = []
    unverifiable: list[str] = []
    changed = observations["changed_files"]
    write_classes = set(observations["write_classes"])
    expected_writes = set(expected["writes"])

    if observations["turn_completed"]:
        passed.append("turn_completed")
    else:
        failed.append("turn_completed")

    if expected_writes == write_classes:
        passed.append("writes")
    else:
        failed.append(f"writes expected={sorted(expected_writes)} observed={sorted(write_classes)}")

    forbidden = set(expected["forbidden_actions"])
    if "file_write" in forbidden:
        (failed if changed else passed).append("forbidden:file_write")
    if "subagent" in forbidden:
        count = observations["subagent_count"]
        if count is None:
            unverifiable.append("forbidden:subagent")
        else:
            (failed if count else passed).append("forbidden:subagent")
    if "process_launch" in forbidden:
        launched = any("tmux" in command or "nohup" in command for command in observations["commands"])
        (failed if launched else passed).append("forbidden:process_launch")
    if "report_completed" in forbidden:
        text = observations["final_message"].lower()
        claimed = any(marker in text for marker in ("experiment completed", "实验已完成", "实验完成"))
        (failed if claimed else passed).append("forbidden:report_completed")

    observed_states = detect_final_state(observations["final_message"])
    if observed_states & set(expected["final_states"]):
        passed.append("final_state")
    else:
        failed.append(
            f"final_state expected={expected['final_states']} observed={sorted(observed_states)}"
        )

    if observations["skill_invoked"] is None:
        unverifiable.append("skill_invoked")
    elif observations["skill_invoked"] == expected["should_trigger"]:
        passed.append("skill_invoked")
    else:
        failed.append("skill_invoked")

    for field in ("stage", "domain", "handling"):
        unverifiable.append(field)
    if observations["subagent_count"] is None:
        unverifiable.append("subagent_count")
    else:
        bounds = expected["subagents"]
        count = observations["subagent_count"]
        if bounds["min"] <= count <= bounds["max"]:
            passed.append("subagent_count")
        else:
            failed.append(f"subagent_count expected={bounds} observed={count}")
    for field in ("models", "efforts", "external_skills"):
        observed = set(observations[field])
        wanted = set(expected[field])
        if not wanted:
            continue
        if not observed:
            unverifiable.append(field)
        elif wanted <= observed:
            passed.append(field)
        else:
            failed.append(f"{field} expected={sorted(wanted)} observed={sorted(observed)}")

    return {
        "passed": not failed,
        "passed_checks": passed,
        "failed_checks": failed,
        "unverifiable_checks": sorted(set(unverifiable)),
        "observed_final_states": sorted(observed_states),
    }


def copy_skill(workspace: Path) -> None:
    destination = workspace / ".agents" / "skills" / "agent-academic-squad"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(*SKIP_COPY_NAMES),
    )


def run_case(
    case: dict[str, Any],
    run_root: Path,
    codex_binary: str,
    timeout: int,
    strict_isolation: bool,
    api_key: str | None,
) -> dict[str, Any]:
    case_id = case["id"]
    workspace = run_root / "workspaces" / case_id
    workspace.mkdir(parents=True, exist_ok=False)
    copy_skill(workspace)
    cache_home = workspace / ".cache"
    cache_home.mkdir(mode=0o700)
    before = snapshot_workspace(workspace)
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
        "-C",
        str(workspace),
        case["prompt"],
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
    changed = changed_files(before, after)
    observations = event_observations(events, changed)
    failure = environment_failure(exit_code, stdout, stderr, timed_out)
    artifact_dir = run_root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / f"{case_id}.jsonl").write_text(stdout, encoding="utf-8")
    (artifact_dir / f"{case_id}.stderr.txt").write_text(stderr, encoding="utf-8")

    evaluation = (
        {
            "passed": False,
            "passed_checks": [],
            "failed_checks": [],
            "unverifiable_checks": ["environment_failure"],
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--case", action="append", dest="case_ids", default=[])
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--codex", default="codex", help="Codex CLI executable")
    parser.add_argument("--run-id", help="Output run identifier")
    parser.add_argument(
        "--strict-isolation",
        action="store_true",
        help="Use isolated HOME/CODEX_HOME; requires CODEX_API_KEY",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0 or (args.max_cases is not None and args.max_cases <= 0):
        parser.error("timeout and max-cases must be positive")
    api_key = os.environ.pop("CODEX_API_KEY", None)
    if args.strict_isolation and not api_key:
        print("strict isolation requires CODEX_API_KEY", file=sys.stderr)
        return 2

    try:
        cases = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2
    if args.list:
        for case in cases:
            print(case["id"])
        return 0
    if args.case_ids:
        selected = [case for case in cases if case["id"] in set(args.case_ids)]
        missing = set(args.case_ids) - {case["id"] for case in selected}
        if missing:
            print(f"unknown cases: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
        cases = selected
    if args.max_cases is not None:
        cases = cases[: args.max_cases]
    if args.dry_run:
        print(json.dumps({"case_ids": [case["id"] for case in cases]}, indent=2))
        return 0

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = ROOT / "evals" / "results" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    results = [
        run_case(case, run_root, args.codex, args.timeout, args.strict_isolation, api_key)
        for case in cases
    ]
    environment_failures = sum(result["environment_failure"] is not None for result in results)
    failed = sum(not result["evaluation"]["passed"] for result in results if not result["environment_failure"])
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cases": results,
        "totals": {
            "selected": len(results),
            "environment_failures": environment_failures,
            "evaluated_failures": failed,
            "passed": len(results) - environment_failures - failed,
        },
    }
    summary_path = run_root / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), **summary["totals"]}, ensure_ascii=False))
    if environment_failures:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
