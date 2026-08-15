#!/usr/bin/env python3
"""Allocate and safely expire temporary academic-squad plan files."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_RETENTION_DAYS = 30
MANAGED_NAME = re.compile(r"^\d{8}T\d{6}Z-[a-z0-9][a-z0-9-]{0,79}\.md$")


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def is_temporary_root(path: Path) -> bool:
    return is_within(path, Path("/tmp")) or is_within(path, Path("/var/tmp"))


def cache_root() -> Path:
    fallback = (Path.home() / ".cache").resolve(strict=False)
    configured = os.environ.get("XDG_CACHE_HOME")
    base = Path(configured).expanduser() if configured else fallback
    if not base.is_absolute():
        base = fallback
    candidate = (base / "agent-academic-squad" / "plans").resolve(strict=False)
    if is_temporary_root(candidate):
        candidate = (fallback / "agent-academic-squad" / "plans").resolve(strict=False)
    if is_temporary_root(candidate):
        raise RuntimeError("no managed cache root is available outside temporary directories")
    return candidate


def prepare_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError(f"managed cache root is not a real directory: {root}")
    try:
        root.chmod(0o700)
    except OSError:
        pass


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return (slug or "plan")[:64].rstrip("-") or "plan"


def validate_retention(days: int) -> int:
    if not 1 <= days <= 365:
        raise ValueError("retention days must be between 1 and 365")
    return days


def cleanup(root: Path, retention_days: int, now: float | None = None) -> list[str]:
    prepare_root(root)
    cutoff = (now if now is not None else time.time()) - retention_days * 86400
    deleted: list[str] = []
    for entry in root.iterdir():
        if not MANAGED_NAME.fullmatch(entry.name):
            continue
        try:
            metadata = entry.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            continue
        if metadata.st_mtime >= cutoff:
            continue
        try:
            entry.unlink()
            deleted.append(entry.name)
        except FileNotFoundError:
            continue
    return sorted(deleted)


def allocate(root: Path, slug: str, retention_days: int) -> tuple[Path, list[str]]:
    deleted = cleanup(root, retention_days)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_slug = slugify(slug)
    for revision in range(1000):
        suffix = "" if revision == 0 else f"-{revision}"
        candidate = root / f"{timestamp}-{safe_slug}{suffix}.md"
        try:
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.close(descriptor)
        return candidate.absolute(), deleted
    raise RuntimeError("could not allocate a unique managed plan path")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("allocate", "cleanup"))
    parser.add_argument("--slug", default="plan", help="Task slug used for an allocated file")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    args = parser.parse_args()

    try:
        retention_days = validate_retention(args.retention_days)
        root = cache_root()
        if args.command == "allocate":
            path, deleted = allocate(root, args.slug, retention_days)
            result = {
                "path": str(path),
                "temporary": True,
                "retention_days": retention_days,
                "deleted": deleted,
            }
        else:
            deleted = cleanup(root, retention_days)
            result = {
                "root": str(root),
                "retention_days": retention_days,
                "deleted": deleted,
            }
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
