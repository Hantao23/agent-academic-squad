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


if __name__ == "__main__":
    unittest.main()
