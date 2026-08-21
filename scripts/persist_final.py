#!/usr/bin/env python3
"""Persist and verify academic-squad final deliverables safely."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

import artifact_cache


SOURCE_STATUSES = ("verbatim", "normalized", "reconstructed")
RECONSTRUCTED_NOTE = (
    "> Provenance: reconstructed after the original final answer became unavailable. "
    "This is not a verbatim frozen source report.\n\n"
)


def read_input(input_file: str | None) -> bytes:
    if input_file is None or input_file == "-":
        return sys.stdin.buffer.read()
    source = Path(input_file).expanduser().resolve(strict=True)
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"input must be a regular non-symlink file: {source}")
    return source.read_bytes()


def prepare_payload(
    body: bytes,
    source_status: str,
    slug: str,
    provenance_note: str | None = None,
) -> bytes:
    if source_status not in SOURCE_STATUSES:
        raise ValueError(f"unknown source status: {source_status}")
    if not body:
        raise ValueError("refusing to persist an empty final deliverable")
    if source_status == "verbatim":
        if provenance_note:
            raise ValueError("verbatim source reports cannot add a provenance note")
        return body
    if source_status == "normalized":
        if not provenance_note or not provenance_note.strip():
            raise ValueError("normalized artifacts require a provenance note")
        note = f"> Provenance: {provenance_note.strip()}\n\n".encode("utf-8")
        return note + body
    if "reconstructed" not in artifact_cache.slugify(slug):
        raise ValueError("reconstructed artifacts require 'reconstructed' in the slug")
    note = provenance_note.strip() if provenance_note else None
    prefix = (
        f"> Provenance: {note}\n\n".encode("utf-8") if note else RECONSTRUCTED_NOTE.encode("utf-8")
    )
    return prefix + body


def write_reserved_path(path: Path, payload: bytes) -> None:
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        temporary_path = None
        if path.read_bytes() != payload:
            raise RuntimeError(f"post-write byte comparison failed: {path}")
    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def persist(
    workspace_root: Path,
    kind: str,
    slug: str,
    body: bytes,
    source_status: str,
    retention_days: int = artifact_cache.DEFAULT_RETENTION_DAYS,
    provenance_note: str | None = None,
) -> tuple[Path, list[str], bytes]:
    workspace = workspace_root.expanduser().resolve(strict=True)
    artifact_cache.require_git_ignored(workspace)
    root = artifact_cache.cache_root(workspace, kind)
    payload = prepare_payload(body, source_status, slug, provenance_note)
    path, deleted = artifact_cache.allocate(root, slug, retention_days, kind)
    write_reserved_path(path, payload)
    return path, deleted, payload


def verify_sources(paths: list[Path]) -> list[dict[str, object]]:
    if not paths:
        raise ValueError("at least one source path is required")
    resolved: set[Path] = set()
    records: list[dict[str, object]] = []
    for supplied in paths:
        if supplied.is_symlink():
            raise ValueError(f"source must not be a symlink: {supplied}")
        path = supplied.expanduser().resolve(strict=True)
        if path in resolved:
            raise ValueError(f"duplicate source path: {path}")
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"source must be a regular file: {path}")
        if metadata.st_size == 0:
            raise ValueError(f"source is empty: {path}")
        resolved.add(path)
        records.append({"path": str(path), "bytes": metadata.st_size})
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    save = subparsers.add_parser("save", help="allocate, write, and byte-verify one deliverable")
    save.add_argument("--workspace-root", required=True)
    save.add_argument("--kind", choices=tuple(artifact_cache.KIND_DIRECTORIES), default="review")
    save.add_argument("--slug", required=True)
    save.add_argument("--source-status", choices=SOURCE_STATUSES, required=True)
    save.add_argument("--provenance-note")
    save.add_argument("--input-file", default="-", help="input file, or '-' for stdin")
    save.add_argument("--retention-days", type=int, default=artifact_cache.DEFAULT_RETENTION_DAYS)

    verify = subparsers.add_parser("verify-sources", help="verify source files before synthesis")
    verify.add_argument("--source", action="append", required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "save":
            retention_days = artifact_cache.validate_retention(args.retention_days)
            body = read_input(args.input_file)
            path, deleted, payload = persist(
                Path(args.workspace_root),
                args.kind,
                args.slug,
                body,
                args.source_status,
                retention_days,
                args.provenance_note,
            )
            result = {
                "path": str(path),
                "kind": args.kind,
                "source_status": args.source_status,
                "bytes": len(payload),
                "temporary": True,
                "retention_days": retention_days,
                "deleted": deleted,
            }
        else:
            result = {"sources": verify_sources([Path(value) for value in args.source])}
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
