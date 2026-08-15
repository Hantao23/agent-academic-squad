from __future__ import annotations

import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


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
            self.assertRegex(allocated.name, artifact_cache.MANAGED_NAME)
            self.assertEqual(stat.S_IMODE(allocated.stat().st_mode), 0o600)

            expired = root / "20200101T000000Z-expired.md"
            unmanaged = root / "keep-me.txt"
            linked = root / "20200101T000001Z-linked.md"
            expired.touch()
            unmanaged.touch()
            linked.symlink_to(unmanaged)
            old = time.time() - 40 * 86400
            os.utime(expired, (old, old))
            os.utime(unmanaged, (old, old))

            removed = artifact_cache.cleanup(root, 30)

            self.assertEqual(removed, [expired.name])
            self.assertFalse(expired.exists())
            self.assertTrue(unmanaged.exists())
            self.assertTrue(linked.is_symlink())
            self.assertTrue(allocated.exists())

    def test_each_kind_uses_an_independent_managed_root(self) -> None:
        roots = {kind: artifact_cache.cache_root(kind) for kind in artifact_cache.KIND_DIRECTORIES}
        self.assertEqual(roots["plan"].name, "plans")
        self.assertEqual(roots["review"].name, "reviews")
        self.assertEqual(roots["handoff"].name, "handoffs")
        self.assertEqual(len(set(roots.values())), 3)

    def test_cache_root_does_not_use_tmp(self) -> None:
        with patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/custom-cache"}, clear=False):
            root = artifact_cache.cache_root("handoff")
        self.assertFalse(artifact_cache.is_within(root, Path("/tmp")))
        self.assertFalse(artifact_cache.is_within(root, Path("/var/tmp")))

    def test_cache_root_rejects_tmp_home_and_xdg_cache(self) -> None:
        environment = {
            "HOME": "/tmp/test-user",
            "XDG_CACHE_HOME": "/tmp/custom-cache",
        }
        with patch.dict(os.environ, environment, clear=False):
            with self.assertRaisesRegex(RuntimeError, "outside temporary directories"):
                artifact_cache.cache_root("review")

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
