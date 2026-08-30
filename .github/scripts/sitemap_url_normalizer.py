from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


NEEDLE = b"loc>/"


def fail(message: str) -> None:
    raise SystemExit(message)


def normalize_base_url(value: str, repository: str) -> str:
    candidate = value.strip()
    if not candidate:
        parts = repository.split("/", 1)
        if len(parts) != 2 or not parts[1].strip():
            fail("repository must use OWNER/NAME form when base_url is blank")
        candidate = f"https://{parts[1].strip().lower()}"
    parsed = urlsplit(candidate)
    try:
        port = parsed.port
    except ValueError as exc:
        fail(f"base_url has an invalid port: {exc}")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        fail("base_url must be an HTTPS origin without credentials, port, path, query, or fragment")
    hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    if hostname.startswith(".") or hostname.endswith(".") or ".." in hostname:
        fail("base_url hostname is invalid")
    return f"https://{hostname}"


def parse_nonnegative_integer(value: str, name: str) -> int:
    if not value.isascii() or not value.isdigit():
        fail(f"{name} must be a nonnegative decimal integer")
    return int(value)


def git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        fail(result.stderr.decode("utf-8", "replace").strip() or f"git {' '.join(args)} failed")
    return result.stdout


def tracked_xml_paths(root: Path) -> list[str]:
    raw = git_bytes(root, "ls-files", "-z")
    paths: list[str] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            relative = item.decode("utf-8", "strict")
        except UnicodeDecodeError:
            fail("tracked XML path is not strict UTF-8")
        path = Path(relative)
        if not relative.casefold().endswith(".xml"):
            continue
        if path.is_absolute() or ".." in path.parts:
            fail(f"unsafe tracked XML path: {relative}")
        resolved = (root / path).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            fail(f"tracked XML path escapes repository root: {relative}")
        if not resolved.is_file() or resolved.is_symlink():
            fail(f"tracked XML path is absent, non-file, or symlinked: {relative}")
        paths.append(relative.replace("\\", "/"))
    return sorted(set(paths), key=lambda item: item.encode("utf-8"))


def atomic_replace(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def publish_outputs(paths_file: Path, summary_file: Path, github_output: Path, changed: list[str], summary: dict) -> None:
    write_new(paths_file, b"".join(path.encode("utf-8") + b"\0" for path in changed))
    write_new(
        summary_file,
        (json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
    )
    with github_output.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"changed={'true' if changed else 'false'}\n")
        stream.write(f"changed_files={len(changed)}\n")
        stream.write(f"replacements={summary['replacements']}\n")


def normalize(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        fail("root must be a Git checkout")
    base_url = normalize_base_url(args.base_url, args.repository)
    minimum = parse_nonnegative_integer(args.minimum_replacements, "minimum_replacements")
    replacement = f"loc>{base_url}/".encode("ascii")
    changed: list[str] = []
    replacements = 0
    scanned = tracked_xml_paths(root)
    for relative in scanned:
        path = root / relative
        original = path.read_bytes()
        count = original.count(NEEDLE)
        if count == 0:
            continue
        updated = original.replace(NEEDLE, replacement)
        if updated.count(NEEDLE) != 0 or updated == original:
            fail(f"postcondition failed for {relative}")
        atomic_replace(path, updated)
        changed.append(relative)
        replacements += count
    if replacements < minimum:
        fail(f"replacement count {replacements} is below required minimum {minimum}")
    if replacements == 0 and not args.allow_noop:
        fail("no relative sitemap locations matched; use allow_noop only after reviewing an idempotent post-state")
    summary = {
        "schema_version": "sitemap-url-normalization-summary-v1",
        "base_url": base_url,
        "tracked_xml_scanned": len(scanned),
        "changed_files": len(changed),
        "replacements": replacements,
        "allow_noop": bool(args.allow_noop),
    }
    publish_outputs(
        Path(args.paths_file).resolve(),
        Path(args.summary_file).resolve(),
        Path(args.github_output).resolve(),
        changed,
        summary,
    )
    print(json.dumps(summary, separators=(",", ":")))
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
        if Path(relative).is_absolute() or ".." in Path(relative).parts or not relative.casefold().endswith(".xml"):
            fail(f"unsafe path in paths file: {relative}")
        paths.append(relative)
    if paths != sorted(set(paths), key=lambda item: item.encode("utf-8")):
        fail("paths file must be unique and bytewise sorted")
    return paths


def porcelain(root: Path) -> dict[str, str]:
    raw = git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    records = raw.split(b"\0")
    result: dict[str, str] = {}
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            fail("unsupported porcelain record")
        status_code = record[:2].decode("ascii", "strict")
        if "R" in status_code or "C" in status_code:
            fail("rename/copy status is outside the sitemap normalization contract")
        try:
            relative = record[3:].decode("utf-8", "strict")
        except UnicodeDecodeError:
            fail("porcelain path is not strict UTF-8")
        if relative in result:
            fail(f"duplicate porcelain path: {relative}")
        result[relative] = status_code
    return result


def verify_git(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    expected = read_paths_file(Path(args.paths_file).resolve())
    actual = porcelain(root)
    if sorted(actual, key=lambda item: item.encode("utf-8")) != expected:
        fail(
            "Git path boundary mismatch: "
            + json.dumps({"expected": expected, "actual": sorted(actual)}, separators=(",", ":"))
        )
    wanted = " M" if args.state == "unstaged" else "M "
    bad = {path: actual[path] for path in expected if actual[path] != wanted}
    if bad:
        fail(f"unexpected Git status for {args.state}: {json.dumps(bad, separators=(',', ':'))}")
    print(json.dumps({"status": "pass", "state": args.state, "paths": len(expected)}, separators=(",", ":")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    normalizer = commands.add_parser("normalize")
    normalizer.add_argument("--root", required=True)
    normalizer.add_argument("--repository", required=True)
    normalizer.add_argument("--base-url", default="")
    normalizer.add_argument("--minimum-replacements", required=True)
    normalizer.add_argument("--allow-noop", action="store_true")
    normalizer.add_argument("--paths-file", required=True)
    normalizer.add_argument("--summary-file", required=True)
    normalizer.add_argument("--github-output", required=True)
    verifier = commands.add_parser("verify-git")
    verifier.add_argument("--root", required=True)
    verifier.add_argument("--paths-file", required=True)
    verifier.add_argument("--state", required=True, choices=("unstaged", "staged"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "normalize":
        return normalize(args)
    return verify_git(args)


if __name__ == "__main__":
    raise SystemExit(main())
