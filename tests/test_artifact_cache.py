from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import artifact_cache  # noqa: E402


class ArtifactCacheTests(unittest.TestCase):
    def test_allocate_and_cleanup_only_managed_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "reviews"
            allocated, deleted = artifact_cache.allocate(root, "DNA 存储审查", 30, "review")
            self.assertEqual(deleted, [])
            self.assertTrue(allocated.is_file())
            self.assertRegex(allocated.parent.name, artifact_cache.MANAGED_MONTH)
            self.assertRegex(allocated.name, artifact_cache.MANAGED_NAME)
            self.assertEqual(stat.S_IMODE(allocated.stat().st_mode), 0o600)

            month_root = root / "2020-01"
            month_root.mkdir()
            expired = month_root / "01T000000Z-expired.md"
            unmanaged = month_root / "keep-me.txt"
            linked = month_root / "01T000001Z-linked.md"
            expired.touch()
            unmanaged.touch()
            linked.symlink_to(unmanaged)
            old = time.time() - 40 * 86400
            os.utime(expired, (old, old))
            os.utime(unmanaged, (old, old))

            removed = artifact_cache.cleanup(root, 30)

            self.assertEqual(removed, [f"2020-01/{expired.name}"])
            self.assertFalse(expired.exists())
            self.assertTrue(unmanaged.exists())
            self.assertTrue(linked.is_symlink())
            self.assertTrue(allocated.exists())

    def test_each_kind_uses_an_independent_managed_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            roots = {kind: artifact_cache.cache_root(workspace, kind) for kind in artifact_cache.KIND_DIRECTORIES}
            self.assertEqual(roots["plan"].name, "plans")
            self.assertEqual(roots["review"].name, "reviews")
            self.assertEqual(roots["handoff"].name, "handoffs")
            self.assertEqual(len(set(roots.values())), 3)
            for root in roots.values():
                self.assertTrue(artifact_cache.is_within(root, workspace))

    def test_project_cache_can_live_in_a_temporary_test_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            root = artifact_cache.cache_root(workspace, "handoff")
        self.assertEqual(root, workspace / ".tmp" / "agent-academic-squad" / "handoffs")

    def test_cache_root_rejects_symlinked_managed_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            outside = workspace / "outside"
            outside.mkdir()
            (workspace / ".tmp").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "contains a symlink"):
                artifact_cache.cache_root(workspace, "plan")

    def test_git_workspace_requires_project_temporary_path_to_be_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            with self.assertRaisesRegex(RuntimeError, "not ignored by Git"):
                artifact_cache.require_git_ignored(workspace)
            exclude = workspace / ".git" / "info" / "exclude"
            exclude.write_text(".tmp/agent-academic-squad/\n", encoding="utf-8")
            artifact_cache.require_git_ignored(workspace)

    def test_cleanup_ignores_invalid_month_directories_and_removes_empty_managed_months(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "plans"
            invalid = root / "2026-99"
            valid = root / "2020-01"
            invalid_day = root / "2026-02"
            invalid.mkdir(parents=True)
            valid.mkdir()
            invalid_day.mkdir()
            (invalid / "01T000000Z-keep.md").touch()
            (invalid_day / "31T000000Z-keep.md").touch()

            removed = artifact_cache.cleanup(root, 30)

            self.assertEqual(removed, [])
            self.assertTrue(invalid.exists())
            self.assertTrue(invalid_day.exists())
            self.assertFalse(valid.exists())

    def test_kind_slug_and_retention_validation(self) -> None:
        self.assertEqual(artifact_cache.slugify("DNA Storage / Ablation"), "dna-storage-ablation")
        self.assertEqual(artifact_cache.slugify("中文", "handoff"), "handoff")
        with self.assertRaises(ValueError):
            artifact_cache.validate_kind("report")
        with self.assertRaises(ValueError):
            artifact_cache.validate_retention(0)
        with self.assertRaises(ValueError):
            artifact_cache.validate_retention(366)


if __name__ == "__main__":
    unittest.main()
