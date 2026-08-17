from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_e2e_evals  # noqa: E402


def receipt(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "answer": "Review result.",
        "final_state": "review_complete",
        "task_completed": True,
        "claimed_execution": False,
        "host_loaded": True,
        "routing_used": True,
        "stage": "review",
        "domain": "code_experiment",
        "handling": "subagent",
        "planned_routes": [],
        "runtime_agents": [
            {
                "stage": "review", "role": "reviewer", "role_kind": "reviewer", "model": "gpt-5.6-sol",
                "effort": "xhigh", "external_skill": None,
            }
        ],
        "invoked_external_skills": [],
        "performed_actions": ["subagent"],
        "blocked_reason": None,
    }
    value.update(overrides)
    return value


def case_expected(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "host_loaded": True,
        "routing_used": True,
        "stage": "review",
        "domain": "code_experiment",
        "handling": "subagent",
        "subagents": {"min": 1, "max": 1},
        "allowed_models": ["gpt-5.6-sol"],
        "required_models": ["gpt-5.6-sol"],
        "allowed_efforts": ["high", "xhigh"],
        "required_efforts": [],
        "runtime_role_counts": {},
        "planned_routes": [],
        "invoked_external_skills": [],
        "writes": [],
        "final_states": ["review_complete"],
        "forbidden_actions": ["file_write"],
        "required_evidence": ["receipt", "workspace", "trace_turn"],
    }
    value.update(overrides)
    return {"id": "test", "expected": value}


def observations(receipt_value: dict[str, object] | None, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "turn_completed": True,
        "changed_files": [],
        "write_classes": [],
        "fixture_changes": [],
        "receipt": receipt_value,
        "skill_invoked": None,
        "subagent_count": None,
        "commands": [],
        "command_trace_available": True,
        "trace_runtime_routes": [],
        "invoked_external_skills_trace": [],
        "web_searches": 0,
        "mcp_calls": 0,
    }
    value.update(overrides)
    return value


class E2ERunnerTests(unittest.TestCase):
    def test_grilling_external_skill_trace_is_detected(self) -> None:
        trace = "\n".join((
            '{"type":"thread.started","thread_id":"t1"}',
            '{"type":"item.completed","item":{"type":"skill_call","skill":"grilling"}}',
            '{"type":"turn.completed","usage":{"input_tokens":1}}',
        ))
        events, invalid = run_e2e_evals.parse_jsonl(trace)
        observed = run_e2e_evals.event_observations(events, [])
        self.assertEqual(invalid, [])
        self.assertIn("grilling", observed["invoked_external_skills_trace"])

    def test_explicit_general_route_is_semantically_valid(self) -> None:
        value = receipt(domain="general")
        self.assertEqual(run_e2e_evals.receipt_semantic_errors(value), [])

    def test_parse_and_observe_structured_receipt(self) -> None:
        trace = "\n".join(
            (
                '{"type":"thread.started","thread_id":"t1"}',
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(receipt())}}),
                '{"type":"turn.completed","usage":{"input_tokens":1}}',
            )
        )
        events, invalid = run_e2e_evals.parse_jsonl(trace)
        observed = run_e2e_evals.event_observations(events, [])
        self.assertEqual(invalid, [])
        self.assertTrue(observed["turn_completed"])
        self.assertEqual(observed["receipt"]["final_state"], "review_complete")
        self.assertEqual(observed["final_message"], "Review result.")

    def test_prose_keywords_do_not_claim_a_final_state(self) -> None:
        self.assertEqual(run_e2e_evals.detect_final_state("I could not produce the requested plan."), set())
        self.assertEqual(
            run_e2e_evals.detect_final_state(json.dumps({"final_state": "blocked"})),
            {"blocked"},
        )

    def test_optional_missing_trace_signals_do_not_poison_a_behavioral_case(self) -> None:
        result = run_e2e_evals.evaluate_observations(case_expected(), observations(receipt()))
        self.assertEqual(result["status"], "pass")
        self.assertIn("skill_invoked:trace", result["optional_unverifiable_checks"])
        self.assertIn("subagent_count:trace", result["optional_unverifiable_checks"])
        self.assertEqual(result["required_unverifiable_checks"], [])

    def test_case_contract_can_require_subagent_and_route_trace(self) -> None:
        expected = case_expected(
            required_evidence=["receipt", "workspace", "trace_turn", "trace_subagents", "trace_routes"]
        )
        result = run_e2e_evals.evaluate_observations(expected, observations(receipt()))
        self.assertEqual(result["status"], "inconclusive")
        self.assertIn("subagent_count:trace", result["required_unverifiable_checks"])
        self.assertIn("runtime_models:trace", result["required_unverifiable_checks"])

    def test_optional_subagent_trace_still_fails_on_explicit_contradiction(self) -> None:
        direct_receipt = receipt(
            final_state="direct_answer",
            host_loaded=False,
            routing_used=False,
            stage="none",
            domain="none",
            handling="direct",
            runtime_agents=[],
            performed_actions=[],
        )
        direct_case = case_expected(
            host_loaded=False,
            routing_used=False,
            stage="none",
            domain="none",
            handling="direct",
            subagents={"min": 0, "max": 0},
            allowed_models=[],
            required_models=[],
            allowed_efforts=[],
            forbidden_actions=["file_write", "subagent"],
            final_states=["direct_answer"],
        )
        result = run_e2e_evals.evaluate_observations(
            direct_case,
            observations(direct_receipt, skill_invoked=False, subagent_count=1),
        )
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("subagent_count:trace" in item for item in result["failed_checks"]))

    def test_allowed_effort_means_any_observed_effort_may_be_allowed(self) -> None:
        result = run_e2e_evals.evaluate_observations(
            case_expected(),
            observations(receipt(), skill_invoked=True, subagent_count=1),
        )
        self.assertEqual(result["status"], "pass")
        self.assertIn("allowed_efforts:self_report", result["passed_checks"])
        self.assertFalse(any("allowed_efforts" in item for item in result["failed_checks"]))

    def test_user_model_override_rejects_silent_effort_substitution(self) -> None:
        expected = case_expected(
            allowed_efforts=["high"], required_efforts=["high"],
            forbidden_actions=["file_write", "model_substitution"],
        )
        result = run_e2e_evals.evaluate_observations(
            expected,
            observations(receipt(), skill_invoked=True, subagent_count=1),
        )
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("allowed_efforts" in item for item in result["failed_checks"]))

    def test_single_writer_checks_runtime_role_counts(self) -> None:
        runtime_agents = [
            {"stage": "review", "role": "A", "role_kind": "analyst", "model": "gpt-5.6-sol", "effort": "xhigh", "external_skill": None},
            {"stage": "review", "role": "B", "role_kind": "analyst", "model": "gpt-5.6-sol", "effort": "xhigh", "external_skill": None},
            {"stage": "write", "role": "final", "role_kind": "writer", "model": "gpt-5.6-sol", "effort": "xhigh", "external_skill": None},
        ]
        expected = case_expected(
            subagents={"min": 3, "max": 3},
            runtime_role_counts={"analyst": 2, "writer": 1},
        )
        result = run_e2e_evals.evaluate_observations(
            expected,
            observations(receipt(runtime_agents=runtime_agents), skill_invoked=True, subagent_count=3),
        )
        self.assertEqual(result["status"], "pass")
        self.assertIn("runtime_role_counts:self_report", result["passed_checks"])

    def test_unknown_forbidden_action_is_inconclusive_not_pass(self) -> None:
        expected = case_expected(forbidden_actions=["telepathy"])
        result = run_e2e_evals.evaluate_observations(
            expected, observations(receipt(), skill_invoked=True, subagent_count=1)
        )
        self.assertEqual(result["status"], "inconclusive")
        self.assertIn("forbidden:telepathy:unsupported", result["unverifiable_checks"])

    def test_workspace_snapshot_detects_delete_mode_type_and_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            deleted = workspace / "deleted.txt"
            mode_file = workspace / "mode.txt"
            typed = workspace / "typed"
            target_a = workspace / "target-a"
            target_b = workspace / "target-b"
            link = workspace / "link"
            deleted.write_text("gone", encoding="utf-8")
            mode_file.write_text("mode", encoding="utf-8")
            mode_file.chmod(0o644)
            typed.write_text("file", encoding="utf-8")
            target_a.write_text("a", encoding="utf-8")
            target_b.write_text("b", encoding="utf-8")
            link.symlink_to("target-a")
            before = run_e2e_evals.snapshot_workspace(workspace)

            deleted.unlink()
            mode_file.chmod(0o600)
            typed.unlink()
            typed.mkdir()
            link.unlink()
            link.symlink_to("target-b")
            after = run_e2e_evals.snapshot_workspace(workspace)
            changes = run_e2e_evals.workspace_changes(before, after)

        self.assertIn("deleted.txt", changes["deleted"])
        self.assertIn("mode.txt", changes["mode_changed"])
        self.assertIn("typed", changes["type_changed"])
        self.assertIn("link", changes["symlink_target_changed"])

    def test_skill_copy_is_not_excluded_from_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            skill_file = workspace / ".agents" / "skills" / "agent-academic-squad" / "SKILL.md"
            skill_file.parent.mkdir(parents=True)
            skill_file.write_text("before", encoding="utf-8")
            before = run_e2e_evals.snapshot_workspace(workspace)
            skill_file.write_text("after", encoding="utf-8")
            after = run_e2e_evals.snapshot_workspace(workspace)
        self.assertIn(".agents/skills/agent-academic-squad/SKILL.md", run_e2e_evals.workspace_changes(before, after)["modified"])

    def test_fixture_modification_is_observed(self) -> None:
        changed = {"created": [], "modified": ["fixtures/demo/data.json"], "deleted": [], "type_changed": [], "mode_changed": [], "symlink_target_changed": []}
        observed = run_e2e_evals.event_observations([], changed, fixture_prefix="fixtures/demo")
        self.assertEqual(observed["fixture_changes"], ["fixtures/demo/data.json"])

    def test_environment_authentication_failure_is_separate(self) -> None:
        failure = run_e2e_evals.environment_failure(1, '{"type":"turn.failed"}', "401 Unauthorized: invalid_api_key", False)
        self.assertEqual(failure, "authentication")

    def test_missing_runner_is_an_environment_failure(self) -> None:
        self.assertEqual(run_e2e_evals.environment_failure(127, "", "not found", False), "runner")

    def test_secret_redaction_and_write_classification(self) -> None:
        self.assertNotIn("secret123", run_e2e_evals.redact("sk-secret123"))
        self.assertEqual(run_e2e_evals.classify_write(".tmp/agent-academic-squad/plans/2026-08/17T120000Z-a.md"), "temporary_plan")
        self.assertEqual(run_e2e_evals.classify_write(".agents/plans/a.md"), "durable_plan")
        self.assertEqual(run_e2e_evals.classify_write(".tmp/agent-academic-squad/reviews/2026-08/17T120000Z-a.md"), "temporary_review")
        self.assertEqual(run_e2e_evals.classify_write(".agents/reviews/a.md"), "durable_review")
        self.assertEqual(run_e2e_evals.classify_write(".tmp/agent-academic-squad/handoffs/2026-08/17T120000Z-a.md"), "temporary_handoff")
        self.assertEqual(run_e2e_evals.classify_write(".agents/handoffs/a.md"), "durable_handoff")
        self.assertEqual(run_e2e_evals.classify_write("temporary/a.json"), "temporary_artifacts")
        self.assertEqual(
            run_e2e_evals.classify_write("wrong/agent-academic-squad/plans/fake.md"),
            "workspace",
        )
        self.assertEqual(run_e2e_evals.classify_write(".tmp/agent-academic-squad/plans/../fake.md"), "workspace")

    def test_strict_mode_rejects_inconclusive(self) -> None:
        self.assertEqual(run_e2e_evals.outcome_exit_code(0, 0, 1, strict=False), 0)
        self.assertEqual(run_e2e_evals.outcome_exit_code(0, 0, 1, strict=True), 1)
        self.assertEqual(run_e2e_evals.outcome_exit_code(1, 0, 0, strict=False), 2)

    def test_runtime_cache_noise_is_ignored_but_managed_auxiliary_files_are_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            runtime_cache = workspace / ".cache" / "codex" / "state.json"
            plan = workspace / ".tmp" / "agent-academic-squad" / "plans" / "2026-08" / "17T120000Z-plan.md"
            review = workspace / ".tmp" / "agent-academic-squad" / "reviews" / "2026-08" / "17T120000Z-review.md"
            runtime_cache.parent.mkdir(parents=True)
            plan.parent.mkdir(parents=True)
            review.parent.mkdir(parents=True)
            runtime_cache.write_text("noise", encoding="utf-8")
            plan.write_text("plan", encoding="utf-8")
            review.write_text("review", encoding="utf-8")
            snapshot = run_e2e_evals.snapshot_workspace(workspace)
        self.assertNotIn(".cache/codex/state.json", snapshot)
        self.assertIn(".tmp/agent-academic-squad/plans/2026-08/17T120000Z-plan.md", snapshot)
        self.assertIn(".tmp/agent-academic-squad/reviews/2026-08/17T120000Z-review.md", snapshot)

    def test_codex_environment_scopes_api_key_to_codex_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            cache_home = workspace / ".cache"
            cache_home.mkdir()
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "wrong-openai-key",
                "CODEX_API_KEY": "wrong-codex-key",
                "AWS_SECRET_ACCESS_KEY": "ambient-secret",
                "SOME_PRIVATE_TOKEN": "ambient-token",
            }):
                environment = run_e2e_evals.codex_environment(cache_home, workspace, True, "selected-key")
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
        self.assertNotIn("SOME_PRIVATE_TOKEN", environment)
        self.assertEqual(environment["CODEX_API_KEY"], "selected-key")
        self.assertEqual(environment["HOME"], str(workspace / ".home"))

    def test_runtime_package_is_blind_to_eval_answers_and_harness_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            destination = run_e2e_evals.copy_skill(workspace)
            schema = run_e2e_evals.prepare_eval_harness(workspace)
            copied = {str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()}
            schema_exists = schema.is_file()
            runtime_eval_dir_exists = (destination / "evals").exists()
        self.assertIn("SKILL.md", copied)
        self.assertIn("references/routing.md", copied)
        self.assertIn("scripts/artifact_cache.py", copied)
        self.assertNotIn("evals/e2e-cases.json", copied)
        self.assertNotIn("evals/receipt-schema.json", copied)
        self.assertNotIn("scripts/run_e2e_evals.py", copied)
        self.assertNotIn("README.md", copied)
        self.assertTrue(schema_exists)
        self.assertFalse(runtime_eval_dir_exists)
        self.assertEqual(schema.parent.name, ".eval-harness")

    def test_receipt_semantics_reject_contradictory_completion_claims(self) -> None:
        broken = receipt(
            final_state="blocked",
            task_completed=True,
            claimed_execution=False,
            blocked_reason=None,
        )
        errors = run_e2e_evals.receipt_semantic_errors(broken)
        self.assertIn("blocked_cannot_be_task_completed", errors)
        self.assertIn("blocked_requires_reason", errors)
        execution_errors = run_e2e_evals.receipt_semantic_errors(
            receipt(
                final_state="execution_complete",
                task_completed=True,
                claimed_execution=False,
                blocked_reason=None,
            )
        )
        self.assertIn("execution_complete_requires_claimed_execution", execution_errors)

    def test_formal_host_load_does_not_force_routing(self) -> None:
        direct_receipt = receipt(
            final_state="direct_answer",
            host_loaded=True,
            routing_used=False,
            stage="none",
            domain="none",
            handling="direct",
            runtime_agents=[],
            performed_actions=[],
        )
        self.assertEqual(run_e2e_evals.receipt_semantic_errors(direct_receipt), [])

    def test_attributable_trace_must_match_receipt_route(self) -> None:
        trace = "\n".join((
            json.dumps({
                "type": "item.completed",
                "item": {
                    "id": "agent-1",
                    "type": "collab_tool_call",
                    "subagent_id": "agent-1",
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "max",
                },
            }),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(receipt())}}),
            '{"type":"turn.completed"}',
        ))
        events, _ = run_e2e_evals.parse_jsonl(trace)
        observed = run_e2e_evals.event_observations(events, [])
        result = run_e2e_evals.evaluate_observations(
            case_expected(required_evidence=["receipt", "workspace", "trace_turn", "trace_routes"]),
            observed,
        )
        self.assertEqual(observed["trace_runtime_routes"][0]["models"], ["gpt-5.6-terra"])
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("models:receipt_trace_consistency" in item for item in result["failed_checks"]))

    def test_provenance_records_reproducibility_fields(self) -> None:
        data = run_e2e_evals.provenance(ROOT / "evals" / "e2e-cases.json")
        self.assertEqual(
            set(data),
            {"runner_commit", "runner_sha256", "manifest_sha256", "platform"},
        )
        self.assertRegex(data["manifest_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
