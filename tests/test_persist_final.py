from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

import sys

sys.path.insert(0, str(ROOT / "scripts"))

import persist_final  # noqa: E402


class PersistFinalTests(unittest.TestCase):
    def test_verbatim_persistence_is_byte_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            body = "# Frozen report\n\n结论与公式 $x^2$.\n".encode("utf-8")
            path, deleted, payload = persist_final.persist(
                workspace, "review", "voiceark-reviewer-1-technical-review", body, "verbatim"
            )
            self.assertEqual(deleted, [])
            self.assertEqual(payload, body)
            self.assertEqual(path.read_bytes(), body)
            self.assertIn("voiceark-reviewer-1-technical-review", path.name)

    def test_normalized_persistence_requires_and_records_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            with self.assertRaisesRegex(ValueError, "require a provenance note"):
                persist_final.persist(
                    workspace, "review", "dnaterra-dispatcher-synthesis", b"body", "normalized"
                )
            path, _, _ = persist_final.persist(
                workspace,
                "review",
                "dnaterra-dispatcher-synthesis",
                b"body",
                "normalized",
                provenance_note="Synthesized from two verified frozen reports.",
            )
            self.assertTrue(path.read_bytes().startswith(b"> Provenance:"))

    def test_reconstructed_status_requires_honest_slug(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            with self.assertRaisesRegex(ValueError, "reconstructed.*slug"):
                persist_final.persist(
                    workspace, "review", "dnaterra-reviewer-1-technical-review", b"body", "reconstructed"
                )
            path, _, _ = persist_final.persist(
                workspace,
                "review",
                "dnaterra-reviewer-1-reconstructed-technical-review",
                b"body",
                "reconstructed",
            )
            self.assertIn("not a verbatim frozen source report", path.read_text(encoding="utf-8"))

    def test_verify_sources_rejects_empty_duplicate_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.md"
            empty = root / "empty.md"
            linked = root / "linked.md"
            first.write_text("report", encoding="utf-8")
            empty.touch()
            linked.symlink_to(first)
            records = persist_final.verify_sources([first])
            self.assertEqual(records[0]["bytes"], len(b"report"))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                persist_final.verify_sources([first, first])
            with self.assertRaisesRegex(ValueError, "empty"):
                persist_final.verify_sources([empty])
            with self.assertRaisesRegex(ValueError, "symlink"):
                persist_final.verify_sources([linked])


if __name__ == "__main__":
    unittest.main()
