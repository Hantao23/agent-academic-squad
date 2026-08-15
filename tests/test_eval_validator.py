from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate_eval_cases  # noqa: E402


class EvalValidatorTests(unittest.TestCase):
    def test_distinguishes_formal_and_natural_invocations(self) -> None:
        self.assertEqual(validate_eval_cases.classify_invocation("$agent-academic-squad 审查实验"), "formal")
        for prompt in ("小分队：审查实验", "小分队帮我审查实验", "这个交给小分队，只规划。"):
            with self.subTest(prompt=prompt):
                self.assertEqual(validate_eval_cases.classify_invocation(prompt), "shortcut")

    def test_natural_negations_and_discussion_do_not_invoke(self) -> None:
        for prompt in ("不用小分队，直接回答。", "不要交给小分队。"):
            with self.subTest(prompt=prompt):
                self.assertEqual(validate_eval_cases.classify_invocation(prompt), "negated")
                self.assertFalse(validate_eval_cases.has_explicit_invocation(prompt))
        self.assertEqual(validate_eval_cases.classify_invocation("我只是在讨论小分队的名字。"), "discussion")

    def test_formal_host_syntax_wins_over_prose_negation(self) -> None:
        prompt = "不要使用 $agent-academic-squad，直接回答。"
        self.assertEqual(validate_eval_cases.classify_invocation(prompt), "formal")
        self.assertTrue(validate_eval_cases.has_explicit_invocation(prompt))


if __name__ == "__main__":
    unittest.main()
