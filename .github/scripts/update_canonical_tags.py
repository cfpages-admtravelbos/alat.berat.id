#!/usr/bin/env python3
"""Normalize existing HTML canonical-link hrefs without reserializing HTML."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import quote, urlsplit


SUMMARY_SCHEMA = "html-canonical-normalizer-summary-v1"
DNS_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
FALLBACK_SUFFIXES = (
    ".id",
    ".com",
    ".net",
    ".org",
    ".example",
)
ATTRIBUTE_NAME = re.compile(rb"[^\s=/>]+")
ASCII_SPACE = b" \t\r\n\f"


class NormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalTag:
    href_start: int
    href_end: int
    href: str


@dataclass(frozen=True)
class PlannedChange:
    relative_path: str
    path: Path
    original: bytes
    updated: bytes


def run_git(root: Path, arguments: list[str], *, check: bool = True) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise NormalizationError(
            f"git {' '.join(arguments)} failed ({process.returncode}): {message}"
        )
    return process.stdout


def split_nul(data: bytes) -> list[bytes]:
    if not data:
        return []
    if not data.endswith(b"\0"):
        raise NormalizationError("NUL-delimited Git output is truncated")
    return data[:-1].split(b"\0")


def decode_git_path(value: bytes) -> str:
    try:
        path = value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise NormalizationError("tracked path is not strict UTF-8") from exc
    if not path or "\0" in path or path.startswith("/") or "\\" in path:
        raise NormalizationError(f"unsupported tracked path: {path!r}")
    parts = PurePosixPath(path).parts
    if any(part in ("", ".", "..") for part in parts):
        raise NormalizationError(f"unsafe tracked path: {path!r}")
    return path


def tracked_html_paths(root: Path) -> list[str]:
    values = split_nul(run_git(root, ["ls-files", "-z"]))
    paths = [
        decode_git_path(value)
        for value in values
        if value.lower().endswith(b".html")
    ]
    paths.sort(key=lambda item: item.encode("utf-8"))
    if len(paths) != len(set(paths)):
        raise NormalizationError("tracked HTML path list contains duplicates")
    return paths


def validate_hostname(hostname: str) -> str:
    host = hostname.rstrip(".").lower()
    if len(host) > 253 or "." not in host:
        raise NormalizationError(f"invalid canonical hostname: {hostname!r}")
    labels = host.split(".")
    if any(not DNS_LABEL.fullmatch(label) for label in labels):
        raise NormalizationError(f"invalid canonical hostname: {hostname!r}")
    return host


def normalize_origin(value: str) -> str:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise NormalizationError(f"invalid canonical origin: {value!r}") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise NormalizationError(f"invalid canonical origin: {value!r}")
    return f"https://{validate_hostname(parsed.hostname)}"


def absolute_href_origin(href: str) -> str | None:
    parsed = urlsplit(href.strip())
    if not parsed.scheme and not parsed.netloc:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise NormalizationError(f"canonical href has an unsupported origin: {href!r}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise NormalizationError(f"canonical href has an invalid port: {href!r}") from exc
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise NormalizationError(f"canonical href has an unsupported origin: {href!r}")
    return f"https://{validate_hostname(parsed.hostname)}"


def comment_ranges(data: bytes) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    position = 0
    lower = data.lower()
    while True:
        start = lower.find(b"<!--", position)
        if start < 0:
            break
        end = lower.find(b"-->", start + 4)
        if end < 0:
            raise NormalizationError("unterminated HTML comment")
        ranges.append((start, end + 3))
        position = end + 3
    return ranges


def inside_ranges(position: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in ranges)


def link_tag_ranges(data: bytes) -> Iterable[tuple[int, int]]:
    lower = data.lower()
    comments = comment_ranges(data)
    position = 0
    while True:
        start = lower.find(b"<link", position)
        if start < 0:
            return
        boundary = start + 5
        if boundary < len(data) and data[boundary : boundary + 1] not in ASCII_SPACE + b"/>":
            position = boundary
            continue
        if inside_ranges(start, comments):
            position = boundary
            continue
        quote_byte: int | None = None
        cursor = boundary
        while cursor < len(data):
            byte = data[cursor]
            if quote_byte is None and byte in (34, 39):
                quote_byte = byte
            elif quote_byte is not None and byte == quote_byte:
                quote_byte = None
            elif quote_byte is None and byte == 62:
                yield start, cursor + 1
                position = cursor + 1
                break
            cursor += 1
        else:
            raise NormalizationError("unterminated link tag")


def parse_attributes(
    data: bytes, tag_start: int, tag_end: int
) -> list[tuple[str, bytes | None, int | None, int | None, bool]]:
    cursor = tag_start + 5
    limit = tag_end - 1
    attributes: list[tuple[str, bytes | None, int | None, int | None, bool]] = []
    while cursor < limit:
        while cursor < limit and data[cursor : cursor + 1] in ASCII_SPACE + b"/":
            cursor += 1
        if cursor >= limit:
            break
        match = ATTRIBUTE_NAME.match(data, cursor, limit)
        if not match:
            raise NormalizationError("malformed link-tag attribute")
        try:
            name = match.group(0).decode("ascii").lower()
        except UnicodeDecodeError as exc:
            raise NormalizationError("non-ASCII link-tag attribute name") from exc
        cursor = match.end()
        while cursor < limit and data[cursor : cursor + 1] in ASCII_SPACE:
            cursor += 1
        if cursor >= limit or data[cursor : cursor + 1] != b"=":
            attributes.append((name, None, None, None, False))
            continue
        cursor += 1
        while cursor < limit and data[cursor : cursor + 1] in ASCII_SPACE:
            cursor += 1
        if cursor >= limit:
            raise NormalizationError(f"attribute {name!r} has no value")
        quote_byte = data[cursor]
        if quote_byte in (34, 39):
            value_start = cursor + 1
            value_end = data.find(bytes((quote_byte,)), value_start, limit)
            if value_end < 0:
                raise NormalizationError(f"attribute {name!r} has an unterminated value")
            value = data[value_start:value_end]
            cursor = value_end + 1
            attributes.append((name, value, value_start, value_end, True))
            continue
        value_start = cursor
        while cursor < limit and data[cursor : cursor + 1] not in ASCII_SPACE + b">":
            cursor += 1
        attributes.append(
            (name, data[value_start:cursor], value_start, cursor, False)
        )
    return attributes


def canonical_tag(data: bytes, relative_path: str) -> CanonicalTag | None:
    matches: list[CanonicalTag] = []
    for start, end in link_tag_ranges(data):
        attributes = parse_attributes(data, start, end)
        rel_values = [item for item in attributes if item[0] == "rel"]
        canonical = False
        for _, value, _, _, _ in rel_values:
            if value is None:
                continue
            tokens = value.decode("utf-8", errors="strict").lower().split()
            if "canonical" in tokens:
                canonical = True
        if not canonical:
            continue
        href_values = [item for item in attributes if item[0] == "href"]
        if len(href_values) != 1:
            raise NormalizationError(
                f"{relative_path}: canonical link must have exactly one href"
            )
        _, value, value_start, value_end, quoted = href_values[0]
        if (
            value is None
            or value_start is None
            or value_end is None
            or not quoted
            or not value
        ):
            raise NormalizationError(
                f"{relative_path}: canonical href must be one nonempty quoted value"
            )
        href = value.decode("utf-8", errors="strict")
        matches.append(CanonicalTag(value_start, value_end, href))
    if len(matches) > 1:
        raise NormalizationError(
            f"{relative_path}: multiple canonical link tags are ambiguous"
        )
    return matches[0] if matches else None


def canonical_path(relative_path: str) -> str:
    parts = list(PurePosixPath(relative_path).parts)
    leaf = parts[-1]
    if not leaf.lower().endswith(".html"):
        raise NormalizationError(f"not an HTML path: {relative_path}")
    encoded_parents = [quote(part, safe="-._~") for part in parts[:-1]]
    if leaf.lower() == "index.html":
        if not encoded_parents:
            return "/"
        return "/" + "/".join(encoded_parents) + "/"
    stem = leaf[:-5]
    encoded_leaf = quote(stem, safe="-._~")
    return "/" + "/".join([*encoded_parents, encoded_leaf])


def repository_origin(repository: str) -> str:
    if repository.count("/") != 1:
        raise NormalizationError(
            "repository must use the owner/name shape for origin fallback"
        )
    name = repository.split("/", 1)[1]
    hostname = validate_hostname(name)
    if not hostname.endswith(FALLBACK_SUFFIXES):
        raise NormalizationError(
            f"repository-derived hostname requires an explicit or existing origin: {hostname!r}"
        )
    return f"https://{hostname}"


def atomic_replace(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.canonical-", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def plan_normalization(
    root: Path, repository: str, explicit_origin: str
) -> tuple[list[PlannedChange], dict[str, int | str | list[str]]]:
    paths = tracked_html_paths(root)
    candidates: list[tuple[str, Path, bytes, CanonicalTag]] = []
    existing_origins: set[str] = set()
    skipped_no_tag = 0
    skipped_non_regular = 0

    for relative_path in paths:
        path = root.joinpath(*PurePosixPath(relative_path).parts)
        if path.is_symlink() or not path.is_file():
            skipped_non_regular += 1
            continue
        original = path.read_bytes()
        try:
            original.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise NormalizationError(
                f"{relative_path}: file is not strict UTF-8"
            ) from exc
        tag = canonical_tag(original, relative_path)
        if tag is None:
            skipped_no_tag += 1
            continue
        origin = absolute_href_origin(tag.href)
        if origin is not None:
            existing_origins.add(origin)
        candidates.append((relative_path, path, original, tag))

    if len(existing_origins) > 1:
        raise NormalizationError(
            "multiple existing canonical origins are ambiguous: "
            + ", ".join(sorted(existing_origins))
        )
    normalized_explicit = normalize_origin(explicit_origin) if explicit_origin else ""
    existing_origin = next(iter(existing_origins), "")
    if normalized_explicit and existing_origin and normalized_explicit != existing_origin:
        raise NormalizationError(
            f"explicit origin {normalized_explicit} conflicts with existing origin {existing_origin}"
        )
    origin = normalized_explicit or existing_origin or repository_origin(repository)

    changes: list[PlannedChange] = []
    unchanged = 0
    for relative_path, path, original, tag in candidates:
        desired = (origin + canonical_path(relative_path)).encode("utf-8")
        updated = original[: tag.href_start] + desired + original[tag.href_end :]
        if updated == original:
            unchanged += 1
            continue
        changes.append(PlannedChange(relative_path, path, original, updated))

    changes.sort(key=lambda item: item.relative_path.encode("utf-8"))
    summary: dict[str, int | str | list[str]] = {
        "schema_version": SUMMARY_SCHEMA,
        "repository": repository,
        "origin": origin,
        "tracked_html": len(paths),
        "eligible": len(candidates),
        "changed": len(changes),
        "unchanged": unchanged,
        "skipped_no_tag": skipped_no_tag,
        "skipped_non_regular": skipped_non_regular,
        "changed_paths": [item.relative_path for item in changes],
    }
    return changes, summary


def normalize_command(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if not (root / ".git").exists():
        raise NormalizationError(f"root is not a Git worktree: {root}")
    manifest = args.manifest.resolve()
    summary_path = args.summary.resolve()
    if manifest.exists() or summary_path.exists():
        raise NormalizationError("manifest and summary outputs must be fresh paths")
    try:
        manifest.relative_to(root)
        manifest_inside = True
    except ValueError:
        manifest_inside = False
    if manifest_inside:
        raise NormalizationError("changed-path manifest must be outside the worktree")
    try:
        summary_path.relative_to(root)
        summary_inside = True
    except ValueError:
        summary_inside = False
    if summary_inside:
        raise NormalizationError("summary output must be outside the worktree")

    changes, summary = plan_normalization(root, args.repository, args.site_origin)
    for change in changes:
        atomic_replace(change.path, change.updated)

    manifest_data = b"".join(
        item.relative_path.encode("utf-8") + b"\0" for item in changes
    )
    summary_data = (
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    write_new(manifest, manifest_data)
    write_new(summary_path, summary_data)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


def parse_name_status(data: bytes, label: str) -> list[tuple[str, str]]:
    values = split_nul(data)
    if len(values) % 2:
        raise NormalizationError(f"{label} name-status output is malformed")
    rows: list[tuple[str, str]] = []
    for index in range(0, len(values), 2):
        status_value = values[index].decode("ascii", errors="strict")
        path = decode_git_path(values[index + 1])
        rows.append((status_value, path))
    return rows


def manifest_paths(path: Path) -> list[str]:
    data = path.read_bytes()
    paths = [decode_git_path(item) for item in split_nul(data)]
    if paths != sorted(paths, key=lambda item: item.encode("utf-8")):
        raise NormalizationError("changed-path manifest is not ordinal-sorted")
    if len(paths) != len(set(paths)):
        raise NormalizationError("changed-path manifest contains duplicates")
    if any(not item.lower().endswith(".html") for item in paths):
        raise NormalizationError("changed-path manifest contains a non-HTML path")
    return paths


def assert_exact_worktree(root: Path, expected: list[str]) -> None:
    if split_nul(run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"])):
        raise NormalizationError("worktree contains untracked paths")
    if parse_name_status(
        run_git(root, ["diff", "--cached", "--name-status", "-z"]), "staged"
    ):
        raise NormalizationError("worktree contains pre-staged changes")
    rows = parse_name_status(
        run_git(root, ["diff", "--name-status", "-z"]), "unstaged"
    )
    if any(status_value != "M" for status_value, _ in rows):
        raise NormalizationError("worktree contains a non-modification change")
    actual = sorted((path for _, path in rows), key=lambda item: item.encode("utf-8"))
    if actual != expected:
        raise NormalizationError(
            f"worktree changes do not equal manifest: expected={expected!r} actual={actual!r}"
        )


def stage_command(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    manifest = args.manifest.resolve()
    paths = manifest_paths(manifest)
    assert_exact_worktree(root, paths)
    if paths:
        run_git(
            root,
            [
                "add",
                f"--pathspec-from-file={manifest}",
                "--pathspec-file-nul",
            ],
        )
    unstaged = parse_name_status(
        run_git(root, ["diff", "--name-status", "-z"]), "post-stage unstaged"
    )
    if unstaged:
        raise NormalizationError("unstaged changes remain after exact staging")
    staged_rows = parse_name_status(
        run_git(root, ["diff", "--cached", "--name-status", "-z"]),
        "post-stage staged",
    )
    if any(status_value != "M" for status_value, _ in staged_rows):
        raise NormalizationError("staged set contains a non-modification change")
    staged = sorted(
        (path for _, path in staged_rows), key=lambda item: item.encode("utf-8")
    )
    if staged != paths:
        raise NormalizationError("staged paths do not equal manifest")
    print(
        json.dumps(
            {"status": "pass", "staged": len(staged), "paths": staged},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser("normalize")
    normalize.add_argument("--root", required=True, type=Path)
    normalize.add_argument("--repository", required=True)
    normalize.add_argument("--site-origin", default="")
    normalize.add_argument("--manifest", required=True, type=Path)
    normalize.add_argument("--summary", required=True, type=Path)
    normalize.set_defaults(handler=normalize_command)

    stage = subparsers.add_parser("stage")
    stage.add_argument("--root", required=True, type=Path)
    stage.add_argument("--manifest", required=True, type=Path)
    stage.set_defaults(handler=stage_command)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
