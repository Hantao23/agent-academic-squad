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

import plan_cache  # noqa: E402


class PlanCacheTests(unittest.TestCase):
    def test_allocate_and_cleanup_only_managed_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "plans"
            allocated, deleted = plan_cache.allocate(root, "DNA 存储实验计划", 30)
            self.assertEqual(deleted, [])
            self.assertTrue(allocated.is_file())
            self.assertRegex(allocated.name, plan_cache.MANAGED_NAME)
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

            removed = plan_cache.cleanup(root, 30)

            self.assertEqual(removed, [expired.name])
            self.assertFalse(expired.exists())
            self.assertTrue(unmanaged.exists())
            self.assertTrue(linked.is_symlink())
            self.assertTrue(allocated.exists())

    def test_cache_root_does_not_use_tmp(self) -> None:
        with patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/custom-cache"}, clear=False):
            root = plan_cache.cache_root()
        self.assertFalse(plan_cache.is_within(root, Path("/tmp")))
        self.assertFalse(plan_cache.is_within(root, Path("/var/tmp")))

    def test_slug_and_retention_bounds(self) -> None:
        self.assertEqual(plan_cache.slugify("DNA Storage / Ablation"), "dna-storage-ablation")
        self.assertEqual(plan_cache.slugify("中文"), "plan")
        with self.assertRaises(ValueError):
            plan_cache.validate_retention(0)
        with self.assertRaises(ValueError):
            plan_cache.validate_retention(366)


if __name__ == "__main__":
    unittest.main()
