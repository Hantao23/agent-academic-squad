from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class SkillContractTests(unittest.TestCase):
    def test_complexity_calibration_and_downstream_fast_path_are_bounded(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        complexity_heading = "## Calibrate task complexity without inflating scope"
        fast_path_heading = "## Use the downstream-artifact fast path"
        self.assertIn(complexity_heading, skill)
        self.assertIn(fast_path_heading, skill)
        complexity = skill.split(complexity_heading, 1)[1].split("\n## ", 1)[0]
        fast_path = skill.split(fast_path_heading, 1)[1].split("\n## ", 1)[0]
        self.assertIn("Repository size, academic importance, file count, tool count", complexity)
        self.assertIn("High decision stakes strengthen verification inside the current boundary", complexity)
        self.assertIn("user correction narrows the output", complexity)
        self.assertIn("Widen inspection or execution only after identifying concrete evidence", complexity)
        self.assertIn("Reuse the existing upstream results", fast_path)
        self.assertIn("Do not perform repository-wide investigation by default", fast_path)
        self.assertIn("Do not launch a pilot, recompute an experiment", fast_path)
        self.assertIn("mismatch cannot by itself override this rule", fast_path)
        self.assertIn("Report the evidence before expanding scope", fast_path)

    def test_downstream_fast_path_regression_case_is_exact(self) -> None:
        import json

        manifest = json.loads(
            (ROOT / "evals" / "hash-boundary-integration-cases.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(manifest["cases"]), 1)
        case = manifest["cases"][0]
        expected_paths = {
            "fixtures/downstream-figure-refresh/plot_results.py",
            "fixtures/downstream-figure-refresh/figures/outputs.txt",
        }
        self.assertEqual(case["source_case_id"], "eval-059")
        self.assertEqual(set(case["allowed_changed_paths"]), expected_paths)
        self.assertEqual(set(case["required_changed_paths"]), expected_paths)
        self.assertEqual(case["expected"]["handling"], "direct")
        self.assertEqual(case["expected"]["subagents"], {"min": 0, "max": 0})
        self.assertEqual(case["expected"]["invoked_external_skills"], ["hash-boundary"])
        self.assertEqual(
            set(case["expected"]["forbidden_actions"]),
            {"subagent", "experiment_execution", "process_launch"},
        )
        for signal in ("180", "24", "8", "pilot", "不要调查"):
            self.assertIn(signal, case["prompt"])

        fixture = ROOT / "evals" / "fixtures" / "downstream-figure-refresh"
        state = json.loads((fixture / "experiment_state.json").read_text(encoding="utf-8"))
        old_outputs = (fixture / "figures" / "outputs.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(state["conditions_completed"], 180)
        self.assertEqual(state["upstream_semantics"], "unchanged")
        self.assertEqual(len(old_outputs), 24)
        self.assertTrue(all(name.startswith("isolated_") for name in old_outputs))
        self.assertIn("isolated_error_performance_group_", (fixture / "verify_outputs.py").read_text(encoding="utf-8"))
        self.assertIn("ERROR_TYPES", (fixture / "plot_results.py").read_text(encoding="utf-8"))

    def test_subagent_final_persistence_contract_is_mechanical_and_honest(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        heading = "## Preserve subagent final deliverables before synthesis"
        self.assertIn(heading, skill)
        section = skill.split(heading, 1)[1].split("\n## ", 1)[0]
        self.assertIn("formal user-facing deliverable", section)
        self.assertIn("status-only notices", section)
        self.assertIn("failed or blocked final", section)
        self.assertIn("verbatim", section)
        self.assertIn("normalized", section)
        self.assertIn("reconstructed", section)
        self.assertIn("persist_final.py save", section)
        self.assertIn("--input-file -", section)
        self.assertIn("Do not create a workspace staging", section)
        self.assertIn("never delete or modify a caller-owned input", section)
        self.assertIn("persist_final.py verify-sources", section)
        self.assertIn("do not rename or move it automatically", section)
        self.assertIn("Do not draft the synthesis until", section)

    def test_subagent_model_disclosure_contract_is_present(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        heading = "## Disclose subagent models used"
        self.assertIn(heading, skill)
        section = skill.split(heading, 1)[1].split("\n## ", 1)[0]
        self.assertIn("exact model ID, reasoning effort, and task", section)
        self.assertIn("If no subagent ran", section)
        self.assertIn("Do not report the dispatcher or main conversation model", section)
        self.assertIn("Keep planned assignments separate from actual use", section)

    def test_sol_effort_uses_a_four_step_complexity_ladder(self) -> None:
        routing = (ROOT / "references" / "routing.md").read_text(encoding="utf-8")
        self.assertIn("Simple, short, and explicit plan | Sol medium", routing)
        self.assertIn("Medium-complexity or standard bounded plan | Sol high", routing)
        self.assertIn("Complex, coupled cross-module, high-cost, or open-ended plan | Sol xhigh", routing)
        self.assertIn("ordinary multi-file work with clear interfaces | Sol high", routing)
        self.assertIn("Complex or coupled cross-module change", routing)
        self.assertIn("Critical algorithm or major architecture decision | Sol max", routing)

    def test_hash_boundary_route_requires_semantic_cause_before_rerun(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        heading = "## Apply hash boundaries before costly reactions"
        self.assertIn(heading, skill)
        section = skill.split(heading, 1)[1].split("\n## ", 1)[0]
        self.assertIn("complete `SKILL.md`", section)
        self.assertIn("does not by itself require another subagent", section)
        self.assertIn("mismatch as evidence, not authorization", section)
        self.assertIn("If no semantic producer input changed, do not rerun or widen scope", section)
        self.assertIn("narrowest affected downstream layer", section)
        self.assertIn("positive cases", section)
        self.assertIn("negative cases", section)

        external = (ROOT / "references" / "external-skills.md").read_text(encoding="utf-8")
        route_heading = "## Hash-boundary route"
        self.assertIn(route_heading, external)
        route = external.split(route_heading, 1)[1].split("\n## ", 1)[0]
        self.assertIn("presence of a hash is not a reason to delegate", route)
        self.assertIn("same planner, executor, or reviewer", route)
        self.assertIn("semantic input allowlist", route)
        self.assertIn("mismatch alone never authorizes", route)

    def test_each_turn_has_an_absolute_two_subagent_limit_and_phase_split(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        heading = "## Delegate proportionately"
        section = skill.split(heading, 1)[1].split("\n## ", 1)[0]
        self.assertIn("absolute limit of two distinct subagents", section)
        self.assertIn("one assistant turn responding to one user message", section)
        self.assertIn("newly started or already exists from an earlier turn", section)
        self.assertIn("Multiple interactions with the same agent", section)
        self.assertIn("every descendant subagent", section)
        self.assertIn("Reset the set at the next user message", section)
        self.assertIn("no per-task or user-override exception", section)
        self.assertIn("Default to no recursive delegation", section)

        route_section = skill.split("## Route the task", 1)[1].split("\n## ", 1)[0]
        self.assertIn("main dispatcher, not a subagent", route_section)
        self.assertIn("Before starting any subagent", route_section)
        self.assertIn("Do not spawn a planning or scouting agent merely", route_section)
        self.assertIn("main model and at most two subagents", route_section)
        self.assertIn("decline to execute the whole scope before work starts", route_section)
        self.assertIn("doing it all at once is likely to take a long time", route_section)
        self.assertIn("difficult-to-control agent, verification, and token consumption", route_section)
        self.assertIn("authorize one stage at a time", route_section)
        self.assertIn("execution has not started", route_section)
        self.assertIn("Do not invent precise time or token estimates", route_section)
        self.assertIn("stop without modifying project artifacts", route_section)
        self.assertIn("declare an emergent overrun at the first safe boundary", route_section)
        self.assertIn("original one-turn estimate no longer holds", route_section)
        self.assertIn("what remains unverified", route_section)
        self.assertIn("does not override the two-subagent limit", route_section)

        artifact_section = skill.split("## Preserve reusable squad auxiliary artifacts", 1)[1].split("\n## ", 1)[0]
        self.assertIn("give the concrete reason", artifact_section)
        self.assertIn("never skip persistence silently", artifact_section)
        self.assertIn(".tmp/agent-academic-squad", artifact_section)
        self.assertIn("<YYYY-MM>", artifact_section)
        self.assertIn("<DDTHHMMSSZ>", artifact_section)
        self.assertIn("verify that `.tmp/agent-academic-squad/` is ignored", artifact_section)
        self.assertIn("Do not edit `.gitignore` or `.git/info/exclude` automatically", artifact_section)
        self.assertIn("managed cache may contain only helper-allocated files", artifact_section)
        self.assertIn("no dispatcher-created staging or scratch file remains", artifact_section)
        self.assertIn("never infer ownership from a filename", artifact_section)


if __name__ == "__main__":
    unittest.main()
