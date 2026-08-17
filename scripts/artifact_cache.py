#!/usr/bin/env python3
"""Allocate and safely expire temporary academic-squad auxiliary artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_RETENTION_DAYS = 30
KIND_DIRECTORIES = {
    "plan": "plans",
    "review": "reviews",
    "handoff": "handoffs",
}
MANAGED_MONTH = re.compile(r"^\d{4}-\d{2}$")
MANAGED_NAME = re.compile(r"^\d{2}T\d{6}Z-[a-z0-9][a-z0-9-]{0,79}\.md$")


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_kind(kind: str) -> str:
    if kind not in KIND_DIRECTORIES:
        raise ValueError(f"unknown auxiliary artifact kind: {kind}")
    return kind


def cache_root(workspace_root: Path | str, kind: str = "plan") -> Path:
    kind = validate_kind(kind)
    workspace = Path(workspace_root).expanduser()
    if not workspace.is_absolute():
        raise ValueError("workspace root must be an absolute path")
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError(f"workspace root is not a directory: {workspace}")
    candidate = workspace
    for component in (".tmp", "agent-academic-squad", KIND_DIRECTORIES[kind]):
        candidate /= component
        if candidate.is_symlink():
            raise RuntimeError(f"managed cache path contains a symlink: {candidate}")
    candidate = candidate.resolve(strict=False)
    if not is_within(candidate, workspace):
        raise RuntimeError("managed cache root escapes the workspace")
    return candidate


def require_git_ignored(workspace_root: Path) -> None:
    try:
        inside = subprocess.run(
            ["git", "-C", str(workspace_root), "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return
    if inside.returncode != 0:
        return
    probe = ".tmp/agent-academic-squad/.write-check"
    ignored = subprocess.run(
        ["git", "-C", str(workspace_root), "check-ignore", "--no-index", "-q", "--", probe],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if ignored.returncode == 1:
        raise RuntimeError(
            "project temporary storage is not ignored by Git; add .tmp/agent-academic-squad/ "
            "to a project or local ignore rule"
        )
    if ignored.returncode != 0:
        raise RuntimeError("could not verify that project temporary storage is ignored by Git")


def prepare_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError(f"managed cache root is not a real directory: {root}")
    try:
        root.chmod(0o700)
    except OSError:
        pass


def valid_month_directory(name: str) -> bool:
    if not MANAGED_MONTH.fullmatch(name):
        return False
    try:
        datetime.strptime(name, "%Y-%m")
    except ValueError:
        return False
    return True


def valid_managed_name(name: str, month: str) -> bool:
    if not MANAGED_NAME.fullmatch(name):
        return False
    try:
        datetime.strptime(f"{month}-{name[:2]}", "%Y-%m-%d")
    except ValueError:
        return False
    return True


def slugify(value: str, fallback: str = "artifact") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return (slug or fallback)[:64].rstrip("-") or fallback


def validate_retention(days: int) -> int:
    if not 1 <= days <= 365:
        raise ValueError("retention days must be between 1 and 365")
    return days


def cleanup(root: Path, retention_days: int, now: float | None = None) -> list[str]:
    prepare_root(root)
    cutoff = (now if now is not None else time.time()) - retention_days * 86400
    deleted: list[str] = []
    for month_root in root.iterdir():
        if not valid_month_directory(month_root.name):
            continue
        try:
            month_metadata = month_root.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(month_metadata.st_mode) or stat.S_ISLNK(month_metadata.st_mode):
            continue
        for entry in month_root.iterdir():
            if not valid_managed_name(entry.name, month_root.name):
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
                deleted.append(str(Path(month_root.name) / entry.name))
            except FileNotFoundError:
                continue
        try:
            month_root.rmdir()
        except (FileNotFoundError, OSError):
            pass
    return sorted(deleted)


def allocate(
    root: Path,
    slug: str,
    retention_days: int,
    fallback: str = "artifact",
    now: float | None = None,
) -> tuple[Path, list[str]]:
    timestamp = now if now is not None else time.time()
    deleted = cleanup(root, retention_days, timestamp)
    instant = datetime.fromtimestamp(timestamp, timezone.utc)
    month_root = root / instant.strftime("%Y-%m")
    prepare_root(month_root)
    time_prefix = instant.strftime("%dT%H%M%SZ")
    safe_slug = slugify(slug, fallback)
    for revision in range(1000):
        suffix = "" if revision == 0 else f"-{revision}"
        candidate = month_root / f"{time_prefix}-{safe_slug}{suffix}.md"
        try:
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.close(descriptor)
        return candidate.absolute(), deleted
    raise RuntimeError("could not allocate a unique managed auxiliary artifact path")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("allocate", "cleanup"))
    parser.add_argument("--workspace-root", required=True, help="Absolute project or workspace root")
    parser.add_argument("--kind", choices=tuple(KIND_DIRECTORIES), default="plan")
    parser.add_argument("--slug", default="artifact", help="Task slug used for an allocated file")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    args = parser.parse_args()

    try:
        retention_days = validate_retention(args.retention_days)
        workspace_root = Path(args.workspace_root).expanduser().resolve(strict=True)
        require_git_ignored(workspace_root)
        root = cache_root(workspace_root, args.kind)
        if args.command == "allocate":
            path, deleted = allocate(root, args.slug, retention_days, args.kind)
            result = {
                "path": str(path),
                "kind": args.kind,
                "temporary": True,
                "retention_days": retention_days,
                "deleted": deleted,
            }
        else:
            deleted = cleanup(root, retention_days)
            result = {
                "root": str(root),
                "kind": args.kind,
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
