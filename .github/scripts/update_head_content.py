#!/usr/bin/env python3
"""Deterministically insert .head content into repository HTML files.

The normalize command plans and validates every file before any replacement.  The
stage command consumes its NUL-delimited manifest and stages only those paths.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

START = "<!-- START of .head content -->"
END = "<!-- END of .head content -->"
SUMMARY_SCHEMA = "html-head-content-summary-v2"
ALLOWED_CANONICAL = {
    ".github/workflows/html-head-content-insertion.yml",
    ".github/scripts/update_head_content.py",
    ".github/scripts/test_update_head_content.py",
}


class HeadContentError(ValueError):
    pass


@dataclass(frozen=True)
class Planned:
    relative: str
    path: Path
    original: bytes
    updated: bytes


@dataclass(frozen=True)
class TransformResult:
    updated: bytes
    skipped_headless: bool = False


def git(root: Path, args: list[str], *, check: bool = True) -> bytes:
    p = subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, check=False)
    if check and p.returncode:
        raise HeadContentError(p.stderr.decode("utf-8", "replace").strip())
    return p.stdout


def split_nul(data: bytes) -> list[bytes]:
    if not data:
        return []
    if not data.endswith(b"\0"):
        raise HeadContentError("NUL-delimited Git output is truncated")
    return data[:-1].split(b"\0")


def safe_rel(value: str) -> str:
    if not value or "\0" in value or value.startswith("/") or "\\" in value:
        raise HeadContentError(f"unsafe path: {value!r}")
    raw_parts = value.split("/")
    if any(p in ("", ".", "..") for p in raw_parts):
        raise HeadContentError(f"unsafe path: {value!r}")
    return value


def reject_lone_cr(text: str, label: str) -> None:
    """Reject carriage returns that are not part of a CRLF token."""
    if re.search(r"\r(?!\n)", text):
        raise HeadContentError(f"{label}: lone CR newline is not supported")


def newline_tokens(text: str) -> list[tuple[int, int, str]]:
    """Return every accepted newline token as (start, end, token)."""
    return [(m.start(), m.end(), m.group(0))
            for m in re.finditer(r"\r\n|\n", text)]


def normalize_head(data: bytes) -> str:
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise HeadContentError(".head is not strict UTF-8") from exc
    reject_lone_cr(text, ".head")
    # A BOM is an encoding marker, never HTML content.
    if text.startswith("\ufeff"):
        text = text[1:]
    # Normalize accepted separators to logical LF; targets choose their local
    # separator independently when the managed block is rendered.
    return text.replace("\r\n", "\n")


def iter_html(root: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git" and not (Path(current) / d).is_symlink()]
        for name in files:
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            if name.endswith(".html"):
                if path.is_symlink():
                    raise HeadContentError(f"symlink HTML target: {rel}")
                if not path.is_file():
                    continue
                found.append((safe_rel(rel), path))
    found.sort(key=lambda item: item[0].encode("utf-8"))
    return found


def block(content_lf: str, style: str) -> bytes:
    content = content_lf.strip("\n").replace("\n", style)
    sep = style
    if content:
        return (START + sep + content + sep + END).encode("utf-8")
    return (START + sep + END).encode("utf-8")


def transform(data: bytes, content_lf: str, rel: str) -> TransformResult:
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise HeadContentError(f"{rel}: file is not strict UTF-8") from exc
    reject_lone_cr(text, rel)
    # Work in original text offsets while preserving BOM and all unrelated bytes.
    starts = [m.start() for m in re.finditer(re.escape(START), text)]
    ends = [m.start() for m in re.finditer(re.escape(END), text)]
    # Detect recognizable but incomplete marker tokens as poison as well.
    if re.search(r"<!-- START of \.head content(?! -->)", text) or re.search(
            r"<!-- END of \.head content(?! -->)", text):
        raise HeadContentError(f"{rel}: missing, duplicated, reversed, nested, or partial markers")
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1:
            raise HeadContentError(f"{rel}: missing, duplicated, reversed, nested, or partial markers")
        if starts[0] > ends[0]:
            raise HeadContentError(f"{rel}: missing, duplicated, reversed, nested, or partial markers")
        # A marker inside the pair is necessarily a nested/duplicate marker.
        if text.find(START, starts[0] + len(START), ends[0]) >= 0 or text.find(END, starts[0] + len(END), ends[0]) >= 0:
            raise HeadContentError(f"{rel}: nested markers")
        tokens = newline_tokens(text)
        begin = starts[0] + len(START); finish = ends[0]
        interior = [tok for tok in tokens if begin <= tok[0] and tok[1] <= finish]
        if interior:
            style = interior[0][2]
        else:
            before = [tok for tok in tokens if tok[1] <= starts[0]]
            after = [tok for tok in tokens if tok[0] >= ends[0] + len(END)]
            style = (before[-1][2] if before else after[0][2] if after else "\n")
        inner = block(content_lf, style).decode("utf-8")[len(START): -len(END)]
        return TransformResult((text[: starts[0] + len(START)] + inner + text[ends[0]:]).encode("utf-8"))
    # Marker-free insertion is the only path that requires a closing head tag.
    closing = list(re.finditer(r"</head\s*>", text, flags=re.IGNORECASE))
    if len(closing) == 0:
        # A marker-free document with no head element has no safe insertion
        # point.  Leave it byte-identical and report it to the caller.
        return TransformResult(data, skipped_headless=True)
    if len(closing) != 1:
        raise HeadContentError(f"{rel}: file must contain exactly one closing </head> tag")
    tokens = newline_tokens(text)
    idx = closing[0].start()
    before = [tok for tok in tokens if tok[1] <= idx]
    after = [tok for tok in tokens if tok[0] >= closing[0].end()]
    style = before[-1][2] if before else after[0][2] if after else "\n"
    insert = block(content_lf, style)
    # Reuse an existing boundary newline when present; otherwise create one
    # using the selected local separator. Unrelated bytes remain untouched.
    prefix = text[:idx]
    leading = "" if (prefix.endswith("\n") or prefix.endswith("\r\n")) else style
    return TransformResult((prefix + leading + insert.decode("utf-8") + style + text[idx:]).encode("utf-8"))


def atomic_replace(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.head-", dir=str(path.parent))
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def normalize(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if not (root / ".git").exists():
        raise HeadContentError(f"root is not a Git worktree: {root}")
    head = root / ".head"
    if head.is_symlink() or not head.is_file():
        raise HeadContentError("missing .head file" if not head.exists() else ".head must be a regular non-symlink file")
    manifest, summary = args.manifest.resolve(), args.summary.resolve()
    if manifest.exists() or summary.exists():
        raise HeadContentError("manifest and summary outputs must be fresh paths")
    if manifest.is_relative_to(root) or summary.is_relative_to(root):
        raise HeadContentError("manifest and summary outputs must be outside the worktree")
    content = normalize_head(head.read_bytes())
    plans: list[Planned] = []
    skipped_headless: list[str] = []
    discovered = 0
    for rel, path in iter_html(root):
        discovered += 1
        original = path.read_bytes()
        result = transform(original, content, rel)
        if result.skipped_headless:
            skipped_headless.append(rel)
            continue
        updated = result.updated
        if updated != original:
            plans.append(Planned(rel, path, original, updated))
    plans.sort(key=lambda p: p.relative.encode("utf-8"))
    skipped_headless.sort(key=lambda p: p.encode("utf-8"))
    for item in plans:
        atomic_replace(item.path, item.updated)
    mdata = b"".join(item.relative.encode("utf-8") + b"\0" for item in plans)
    changed_paths = [p.relative for p in plans]
    summary_obj = {
        "schema_version": SUMMARY_SCHEMA,
        "discovered": discovered,
        "changed": len(changed_paths),
        "unchanged": discovered - len(changed_paths) - len(skipped_headless),
        "skipped_headless": len(skipped_headless),
        "skipped_headless_paths": skipped_headless,
    }
    write_new(manifest, mdata)
    write_new(summary, (json.dumps(summary_obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(summary_obj, ensure_ascii=False, separators=(",", ":")))
    return 0


def git_rows(data: bytes) -> list[tuple[str, str]]:
    vals = split_nul(data)
    if len(vals) % 2:
        raise HeadContentError("malformed Git name-status output")
    rows = []
    for i in range(0, len(vals), 2):
        rows.append((vals[i].decode("ascii", "strict"), safe_rel(vals[i + 1].decode("utf-8", "strict"))))
    return rows


def manifest_paths(path: Path) -> list[str]:
    vals = split_nul(path.read_bytes())
    paths = [safe_rel(v.decode("utf-8", "strict")) for v in vals]
    if paths != sorted(paths, key=lambda p: p.encode("utf-8")) or len(paths) != len(set(paths)):
        raise HeadContentError("manifest traversal or duplicate paths")
    for p in paths:
        if not p.endswith(".html"):
            raise HeadContentError("manifest contains a non-HTML path")
    return paths


def stage(args: argparse.Namespace) -> int:
    root = args.root.resolve(); paths = manifest_paths(args.manifest.resolve())
    # Reject symlink manifest targets and ensure all paths remain beneath root.
    for rel in paths:
        target = root.joinpath(*PurePosixPath(rel).parts)
        if any((root.joinpath(*PurePosixPath(rel).parts[:i])).is_symlink()
               for i in range(1, len(PurePosixPath(rel).parts) + 1)):
            raise HeadContentError(f"manifest path is missing or symlink: {rel}")
        if target.is_symlink() or not target.is_file():
            raise HeadContentError(f"manifest path is missing or symlink: {rel}")
    untracked = [safe_rel(v.decode("utf-8", "strict")) for v in split_nul(git(root, ["ls-files", "--others", "--exclude-standard", "-z"]))]
    if any(p not in ALLOWED_CANONICAL for p in untracked):
        raise HeadContentError("dirty path outside exact manifest and canonical bundle")
    staged = git_rows(git(root, ["diff", "--cached", "--name-status", "-z"]))
    if any(p not in ALLOWED_CANONICAL and p not in paths for _, p in staged):
        raise HeadContentError("pre-staged path outside exact manifest")
    unstaged = git_rows(git(root, ["diff", "--name-status", "-z"]))
    dirty = sorted({p for status, p in unstaged if p not in ALLOWED_CANONICAL}, key=lambda p: p.encode("utf-8"))
    if dirty != paths:
        raise HeadContentError(f"dirty paths do not equal manifest: expected={paths!r} actual={dirty!r}")
    if paths:
        git(root, [f"add", f"--pathspec-from-file={args.manifest.resolve()}", "--pathspec-file-nul"])
    remain = [p for _, p in git_rows(git(root, ["diff", "--name-status", "-z"])) if p not in ALLOWED_CANONICAL]
    if remain:
        raise HeadContentError("unstaged changes remain after exact staging")
    print(json.dumps({"status": "pass", "staged": len(paths), "paths": paths}, separators=(",", ":")))
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    n = sub.add_parser("normalize"); n.add_argument("--root", type=Path, required=True); n.add_argument("--manifest", type=Path, required=True); n.add_argument("--summary", type=Path, required=True); n.set_defaults(handler=normalize)
    s = sub.add_parser("stage"); s.add_argument("--root", type=Path, required=True); s.add_argument("--manifest", type=Path, required=True); s.set_defaults(handler=stage)
    return p


def main() -> int:
    arguments = parser().parse_args()
    try:
        return int(arguments.handler(arguments))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
