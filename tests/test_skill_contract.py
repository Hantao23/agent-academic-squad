from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class SkillContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
