#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


ADS_TXT_PATH = "ads.txt"
SCRIPT_BLOCK_RE = re.compile(r"[ \t]*<script\b(?P<attrs>[^<>]*)>(?P<body>.*?)</script\s*>[ \t]*\r?\n?", re.IGNORECASE | re.DOTALL)
INS_BLOCK_RE = re.compile(r"[ \t]*<ins\b[^>]*class=[\"'][^\"']*adsbygoogle[^\"']*[\"'][^>]*>.*?</ins\s*>[ \t]*\r?\n?", re.IGNORECASE | re.DOTALL)
TARGET_LITERAL_RE = re.compile(r"pagead2\.googlesyndication\.com|adsbygoogle", re.IGNORECASE)

LEGACY_FILES_TO_PURGE = [
    ".github/workflows/adsense.yaml",
    ".github/workflows/adsense-normalization.yml",
    ".github/scripts/adsense_normalizer.py",
    ".github/scripts/test_adsense_normalizer.py",
]


@dataclass(frozen=True)
class TextStyle:
    bom: bool
    newline: str
    final_newline: bool


def fail(message: str) -> None:
    raise SystemExit(message)


def git_result(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_bytes(root: Path, *args: str) -> bytes:
    result = git_result(root, *args)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        fail(message or f"git {' '.join(args)} failed")
    return result.stdout


def decode_document(data: bytes, label: str) -> tuple[str, TextStyle]:
    bom = data.startswith(b"\xef\xbb\xbf")
    payload = data[3:] if bom else data
    try:
        text = payload.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        fail(f"{label} is not strict UTF-8: {exc}")
    if "\r" in text.replace("\r\n", ""):
        fail(f"{label} contains unsupported bare carriage returns")
    has_crlf = "\r\n" in text
    has_lf = "\n" in text.replace("\r\n", "")
    if has_crlf and has_lf:
        fail(f"{label} contains mixed LF and CRLF newlines")
    normalized = text.replace("\r\n", "\n")
    return normalized, TextStyle(bom, "\r\n" if has_crlf else "\n", normalized.endswith("\n"))


def encode_document(normalized: str, style: TextStyle) -> bytes:
    body = normalized.replace("\n", "\r\n") if style.newline == "\r\n" else normalized
    encoded = body.encode("utf-8")
    return (b"\xef\xbb\xbf" if style.bom else b"") + encoded


def safe_relative_path(relative: str, label: str) -> PurePosixPath:
    if any(ord(char) < 32 or ord(char) == 127 for char in relative):
        fail(f"{label} contains a control character: {relative!r}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        fail(f"unsafe {label}: {relative!r}")
    return pure


def tracked_html_paths(root: Path) -> list[str]:
    raw = git_bytes(root, "-c", "core.quotepath=false", "ls-files", "-z")
    candidates: list[tuple[str, PurePosixPath]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            relative = item.decode("utf-8", "strict")
        except UnicodeDecodeError:
            fail("tracked path is not strict UTF-8")
        if relative.casefold().endswith(".html"):
            candidates.append((relative, safe_relative_path(relative, "tracked HTML path")))
    ordered = sorted(candidates, key=lambda item: item[0].encode("utf-8"))
    names = [relative for relative, _ in ordered]
    if len(names) != len(set(names)):
        fail("tracked HTML path list contains duplicates")
    casefolded: dict[str, str] = {}
    for relative in names:
        folded = relative.casefold()
        if folded in casefolded:
            fail(f"tracked HTML paths collide by case: {casefolded[folded]!r} and {relative!r}")
        casefolded[folded] = relative
    root_resolved = root.resolve()
    for relative, pure in ordered:
        candidate = root / Path(*pure.parts)
        if candidate.is_symlink() or not candidate.is_file():
            fail(f"tracked HTML path is absent, non-file, or symlinked: {relative!r}")
        try:
            candidate.resolve().relative_to(root_resolved)
        except ValueError:
            fail(f"tracked HTML path escapes the repository: {relative!r}")
    return names


def purge_adsense_from_html(text: str) -> tuple[str, bool]:
    modified = False

    def script_replacer(match: re.Match[str]) -> str:
        nonlocal modified
        full = match.group(0)
        attrs = match.group("attrs")
        body = match.group("body")
        if "pagead2.googlesyndication.com" in attrs.casefold() or "pagead2.googlesyndication.com" in body.casefold() or "adsbygoogle" in body.casefold():
            modified = True
            return ""
        return full

    def ins_replacer(match: re.Match[str]) -> str:
        nonlocal modified
        modified = True
        return ""

    result = SCRIPT_BLOCK_RE.sub(script_replacer, text)
    result = INS_BLOCK_RE.sub(ins_replacer, result)

    # Check if any leftover literal AdSense tags exist
    if "pagead2.googlesyndication.com" in result:
        # Fallback line-by-line purge for any non-standard syntax
        lines = []
        for line in result.split("\n"):
            if "pagead2.googlesyndication.com" in line.casefold():
                modified = True
                continue
            lines.append(line)
        result = "\n".join(lines)

    return result, modified


def atomic_replace(path: Path, data: bytes) -> None:
    if path.exists() and (not path.is_file() or path.is_symlink()):
        fail(f"output path is not a regular non-symlink file: {path}")
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def outside_root(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return resolved
    fail(f"{label} must be outside the repository root")


def apply_purge(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        fail("root must be a Git checkout")

    paths_file = outside_root(Path(args.paths_file), root, "paths_file") if args.paths_file else None
    summary_file = outside_root(Path(args.summary_file), root, "summary_file") if args.summary_file else None
    github_output = outside_root(Path(args.github_output), root, "github_output") if args.github_output else None

    html_paths = tracked_html_paths(root)
    changed_html: list[str] = []

    for relative in html_paths:
        path = root / Path(*PurePosixPath(relative).parts)
        before = path.read_bytes()
        text, style = decode_document(before, relative)
        cleaned_text, modified = purge_adsense_from_html(text)
        if modified:
            after = encode_document(cleaned_text, style)
            atomic_replace(path, after)
            changed_html.append(relative)

    # Handle ads.txt
    deleted_files: list[str] = []
    modified_files: list[str] = list(changed_html)

    ads_path = root / ADS_TXT_PATH
    if ads_path.exists():
        if not ads_path.is_file() or ads_path.is_symlink():
            fail("ads.txt must be a regular non-symlink file")
        raw_ads = ads_path.read_text(encoding="utf-8", errors="ignore")
        lines = [line.strip() for line in raw_ads.splitlines() if line.strip()]
        # Check if lines contain non-AdSense entries
        non_adsense = [line for line in lines if "pub-" not in line.casefold() and "google.com" not in line.casefold()]
        if not non_adsense:
            ads_path.unlink()
            deleted_files.append(ADS_TXT_PATH)
        else:
            ads_path.write_text("\n".join(non_adsense) + "\n", encoding="utf-8")
            modified_files.append(ADS_TXT_PATH)

    # Handle legacy AdSense workflows & scripts
    for legacy in LEGACY_FILES_TO_PURGE:
        legacy_path = root / PurePosixPath(legacy)
        if legacy_path.exists():
            legacy_path.unlink()
            deleted_files.append(legacy)

    all_changed = sorted(set(modified_files + deleted_files), key=lambda item: item.encode("utf-8"))

    summary: dict[str, object] = {
        "schema_version": "adsense-purge-summary-v1",
        "html_files_scanned": len(html_paths),
        "html_files_purged": len(changed_html),
        "deleted_files": sorted(deleted_files),
        "changed_files": all_changed,
    }

    if paths_file:
        paths_file.write_bytes(b"".join(path.encode("utf-8") + b"\0" for path in all_changed))
    if summary_file:
        summary_file.write_bytes((json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    if github_output:
        with github_output.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"changed={'true' if all_changed else 'false'}\n")
            stream.write(f"changed_files={len(all_changed)}\n")
            stream.write(f"html_purged={len(changed_html)}\n")
            stream.write(f"deleted_count={len(deleted_files)}\n")

    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Purge Google AdSense script, ads.txt, and workflows from repository")
    commands = parser.add_subparsers(dest="command", required=True)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--root", required=True, help="Repository root directory")
    apply_parser.add_argument("--paths-file", required=False, help="Optional NUL-separated output changed paths file")
    apply_parser.add_argument("--summary-file", required=False, help="Optional JSON summary output file")
    apply_parser.add_argument("--github-output", required=False, help="Optional GITHUB_OUTPUT file path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "apply":
        return apply_purge(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
