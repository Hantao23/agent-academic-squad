from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate_eval_cases  # noqa: E402


class EvalValidatorTests(unittest.TestCase):
    def test_recognizes_formal_and_natural_invocations(self) -> None:
        prompts = (
            "$agent-academic-squad 审查实验",
            "小分队：审查实验",
            "小分队，审查实验",
            "小分队 审查实验",
            "小分队帮我审查实验",
            "这个交给小分队，只规划。",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertTrue(validate_eval_cases.has_explicit_invocation(prompt))

    def test_rejects_negations_and_discussion_only_mentions(self) -> None:
        prompts = (
            "不用小分队，直接回答。",
            "不要交给小分队。",
            "不要使用 $agent-academic-squad，直接回答。",
            "别调用 $agent-academic-squad，我只想自己处理。",
            "我只是在讨论小分队的名字。",
            "小分队这个称呼是否合适？",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertFalse(validate_eval_cases.has_explicit_invocation(prompt))


if __name__ == "__main__":
    unittest.main()
