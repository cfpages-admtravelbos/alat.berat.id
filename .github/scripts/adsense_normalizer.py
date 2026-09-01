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
TARGET_SCRIPT_URL = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"
PUBLISHER_RE = re.compile(r"[0-9]{16}")
SCRIPT_BLOCK_RE = re.compile(r"<script\b(?P<attrs>[^<>]*)>(?P<body>.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
SRC_ATTR_RE = re.compile(r"""\bsrc\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""", re.IGNORECASE | re.DOTALL)
TARGET_LITERAL_RE = re.compile(re.escape("pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"), re.IGNORECASE)
HEAD_CLOSE_RE = re.compile(r"</head\s*>", re.IGNORECASE)


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


def validate_publisher_id(value: str) -> str:
    if not PUBLISHER_RE.fullmatch(value):
        fail("publisher_id must contain exactly 16 ASCII digits")
    return value


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
    if not ordered:
        fail("no tracked HTML files were found")
    return names


def canonical_script(publisher_id: str) -> str:
    return (
        '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
        f'?client=ca-pub-{publisher_id}" crossorigin="anonymous"></script>'
    )


def target_script_spans(text: str, label: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for block in SCRIPT_BLOCK_RE.finditer(text):
        attrs = block.group("attrs")
        sources = list(SRC_ATTR_RE.finditer(attrs))
        targets = [
            source
            for source in sources
            if source.group("value").strip().split("?", 1)[0].casefold() == TARGET_SCRIPT_URL.casefold()
        ]
        if not targets:
            continue
        if len(sources) != 1 or len(targets) != 1:
            fail(f"{label} has an ambiguous AdSense target script src attribute")
        if block.group("body").strip():
            fail(f"{label} has inline content inside the AdSense target script")
        spans.append(block.span())
    for literal in TARGET_LITERAL_RE.finditer(text):
        if not any(start <= literal.start() < end for start, end in spans):
            fail(f"{label} contains malformed or unsupported AdSense target script syntax")
    return spans


def normalize_html(text: str, publisher_id: str, label: str) -> str:
    desired_script = canonical_script(publisher_id)
    spans = target_script_spans(text, label)
    if spans:
        pieces: list[str] = []
        cursor = 0
        for index, (start, end) in enumerate(spans):
            pieces.append(text[cursor:start])
            if index == 0:
                pieces.append(desired_script)
            cursor = end
        pieces.append(text[cursor:])
        result = "".join(pieces)
    else:
        anchors = list(HEAD_CLOSE_RE.finditer(text))
        if len(anchors) != 1:
            fail(f"{label} requires exactly one closing </head> anchor for insertion; found {len(anchors)}")
        position = anchors[0].start()
        line_start = text.rfind("\n", 0, position) + 1
        prefix = text[line_start:position]
        if not prefix.strip():
            result = text[:line_start] + prefix + desired_script + "\n" + text[line_start:]
        else:
            result = text[:position] + "\n" + desired_script + "\n" + text[position:]
    final_spans = target_script_spans(result, label)
    if len(final_spans) != 1 or result[final_spans[0][0] : final_spans[0][1]] != desired_script:
        fail(f"{label} did not converge to one canonical AdSense script")
    return result


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


def write_new(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def outside_root(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return resolved
    fail(f"{label} must be outside the repository root")


def publish_controls(
    paths_file: Path,
    summary_file: Path,
    github_output: Path,
    changed: list[str],
    summary: dict[str, object],
) -> None:
    write_new(paths_file, b"".join(path.encode("utf-8") + b"\0" for path in changed))
    write_new(
        summary_file,
        (json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
    )
    with github_output.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"changed={'true' if changed else 'false'}\n")
        stream.write(f"changed_files={len(changed)}\n")
        stream.write(f"html_files={summary['html_files']}\n")


def apply_normalization(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        fail("root must be a Git checkout")
    publisher_id = validate_publisher_id(args.publisher_id)
    paths_file = outside_root(Path(args.paths_file), root, "paths_file")
    summary_file = outside_root(Path(args.summary_file), root, "summary_file")
    github_output = outside_root(Path(args.github_output), root, "github_output")
    html_paths = tracked_html_paths(root)
    desired: dict[str, bytes] = {}
    original: dict[str, bytes | None] = {}
    for relative in html_paths:
        path = root / Path(*PurePosixPath(relative).parts)
        before = path.read_bytes()
        text, style = decode_document(before, relative)
        desired[relative] = encode_document(normalize_html(text, publisher_id, relative), style)
        original[relative] = before
    ads_path = root / ADS_TXT_PATH
    if ads_path.exists() and (not ads_path.is_file() or ads_path.is_symlink()):
        fail("ads.txt must be absent or a regular non-symlink file")
    original[ADS_TXT_PATH] = ads_path.read_bytes() if ads_path.exists() else None
    desired[ADS_TXT_PATH] = (
        f"google.com, pub-{publisher_id}, DIRECT, f08c47fec0942fa0\n".encode("ascii")
    )
    changed = sorted(
        [relative for relative, data in desired.items() if original[relative] != data],
        key=lambda item: item.encode("utf-8"),
    )
    for relative in changed:
        path = root / Path(*PurePosixPath(relative).parts)
        atomic_replace(path, desired[relative])
    summary: dict[str, object] = {
        "schema_version": "adsense-normalization-summary-v1",
        "publisher_id": publisher_id,
        "html_files": len(html_paths),
        "changed_files": changed,
    }
    publish_controls(paths_file, summary_file, github_output, changed, summary)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


def read_paths_file(path: Path) -> list[str]:
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\0"):
        fail("paths file is not NUL terminated")
    paths: list[str] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            relative = item.decode("utf-8", "strict")
        except UnicodeDecodeError:
            fail("paths file contains non-UTF-8 bytes")
        safe_relative_path(relative, "paths-file entry")
        if relative != ADS_TXT_PATH and not relative.casefold().endswith(".html"):
            fail(f"unsafe output path in paths file: {relative!r}")
        paths.append(relative)
    if paths != sorted(set(paths), key=lambda item: item.encode("utf-8")):
        fail("paths file must be unique and bytewise sorted")
    return paths


def porcelain(root: Path) -> dict[str, str]:
    records = git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    result: dict[str, str] = {}
    for record in records:
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            fail("unsupported porcelain record")
        status_code = record[:2].decode("ascii", "strict")
        if "R" in status_code or "C" in status_code:
            fail("rename/copy status is outside the normalization contract")
        relative = record[3:].decode("utf-8", "strict")
        if relative in result:
            fail(f"duplicate porcelain path: {relative!r}")
        result[relative] = status_code
    return result


def verify_git(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    expected = read_paths_file(Path(args.paths_file).resolve())
    actual = porcelain(root)
    actual_paths = sorted(actual, key=lambda item: item.encode("utf-8"))
    if actual_paths != expected:
        fail(
            "Git path boundary mismatch: "
            + json.dumps({"expected": expected, "actual": actual_paths}, ensure_ascii=False, separators=(",", ":"))
        )
    allowed = {" M", "??"} if args.state == "unstaged" else {"M ", "A "}
    bad = {path: actual[path] for path in expected if actual[path] not in allowed}
    if bad:
        fail(f"unexpected Git status for {args.state}: {json.dumps(bad, ensure_ascii=False, separators=(',', ':'))}")
    print(json.dumps({"status": "pass", "state": args.state, "paths": len(expected)}, separators=(",", ":")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--root", required=True)
    apply_parser.add_argument("--publisher-id", required=True)
    apply_parser.add_argument("--paths-file", required=True)
    apply_parser.add_argument("--summary-file", required=True)
    apply_parser.add_argument("--github-output", required=True)
    verifier = commands.add_parser("verify-git")
    verifier.add_argument("--root", required=True)
    verifier.add_argument("--paths-file", required=True)
    verifier.add_argument("--state", required=True, choices=("unstaged", "staged"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return apply_normalization(args) if args.command == "apply" else verify_git(args)


if __name__ == "__main__":
    raise SystemExit(main())
