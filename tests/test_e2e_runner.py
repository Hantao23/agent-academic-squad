from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_e2e_evals  # noqa: E402


class E2ERunnerTests(unittest.TestCase):
    def test_parse_and_observe_successful_trace(self) -> None:
        trace = "\n".join(
            (
                '{"type":"thread.started","thread_id":"t1"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"Review complete: invalid step found."}}',
                '{"type":"turn.completed","usage":{"input_tokens":1}}',
            )
        )
        events, invalid = run_e2e_evals.parse_jsonl(trace)
        observed = run_e2e_evals.event_observations(events, [])
        self.assertEqual(invalid, [])
        self.assertTrue(observed["turn_completed"])
        self.assertIn("review_complete", run_e2e_evals.detect_final_state(observed["final_message"]))

    def test_environment_authentication_failure_is_separate(self) -> None:
        failure = run_e2e_evals.environment_failure(
            1,
            '{"type":"turn.failed"}',
            "401 Unauthorized: invalid_api_key",
            False,
        )
        self.assertEqual(failure, "authentication")

    def test_missing_runner_is_an_environment_failure(self) -> None:
        self.assertEqual(run_e2e_evals.environment_failure(127, "", "not found", False), "runner")

    def test_secret_redaction_and_write_classification(self) -> None:
        self.assertNotIn("secret123", run_e2e_evals.redact("sk-secret123"))
        self.assertEqual(
            run_e2e_evals.classify_write(".cache/agent-academic-squad/plans/a.md"),
            "temporary_plan",
        )
        self.assertEqual(
            run_e2e_evals.classify_write(".agents/plans/a.md"),
            "durable_plan",
        )

    def test_codex_environment_scopes_api_key_to_codex_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            cache_home = workspace / ".cache"
            cache_home.mkdir()
            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "wrong-openai-key", "CODEX_API_KEY": "wrong-codex-key"},
            ):
                environment = run_e2e_evals.codex_environment(
                    cache_home,
                    workspace,
                    strict_isolation=True,
                    api_key="selected-key",
                )

        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertEqual(environment["CODEX_API_KEY"], "selected-key")
        self.assertEqual(environment["XDG_CACHE_HOME"], str(cache_home))
        self.assertEqual(environment["HOME"], str(workspace / ".home"))
        self.assertEqual(environment["CODEX_HOME"], str(workspace / ".codex"))


if __name__ == "__main__":
    unittest.main()
