from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote, quote_plus, urlsplit
from xml.sax.saxutils import escape as xml_escape


SITEMAP_PATH = "sitemap-complete.xml"
README_PATH = "README.md"
URL_LIST_PATH = "url-list.txt"
ALLOWED_OUTPUTS = (README_PATH, SITEMAP_PATH, URL_LIST_PATH)
BEGIN_MARKER = "<!-- BEGIN MANAGED SITEMAP URLS -->"
END_MARKER = "<!-- END MANAGED SITEMAP URLS -->"
LEGACY_COUNT = re.compile(r"^Number of URLs:\s*[0-9]+\s*$")
LEGACY_LINK = re.compile(
    r"^\s*-\s+\[https://[^\]]+\]\(https://(?:www\.)?google\.com/search\?q=site%3A.+\)\s*$"
)


@dataclass(frozen=True)
class TextStyle:
    bom: bool
    newline: str
    final_newline: bool


@dataclass(frozen=True)
class Page:
    relative_path: str
    url: str
    lastmod: str


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


def parse_nonnegative_integer(value: str, name: str) -> int:
    if not value.isascii() or not value.isdigit():
        fail(f"{name} must be a nonnegative decimal integer")
    return int(value)


def normalize_origin(value: str, label: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    try:
        port = parsed.port
    except ValueError as exc:
        fail(f"{label} has an invalid port: {exc}")
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
        fail(f"{label} must be an HTTPS origin without credentials, port, path, query, or fragment")
    hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    labels = hostname.split(".")
    if (
        len(labels) < 2
        or any(not item or len(item) > 63 for item in labels)
        or any(item.startswith("-") or item.endswith("-") for item in labels)
        or any(not re.fullmatch(r"[a-z0-9-]+", item) for item in labels)
    ):
        fail(f"{label} hostname is invalid")
    return f"https://{hostname}"


def is_tracked(root: Path, relative: str) -> bool:
    result = git_result(root, "ls-files", "--error-unmatch", "--", relative)
    return result.returncode == 0


def decode_document(data: bytes, label: str) -> tuple[str, TextStyle]:
    bom = data.startswith(b"\xef\xbb\xbf")
    payload = data[3:] if bom else data
    try:
        text = payload.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        fail(f"{label} is not strict UTF-8: {exc}")
    without_crlf = text.replace("\r\n", "")
    if "\r" in without_crlf:
        fail(f"{label} contains unsupported bare carriage returns")
    has_crlf = "\r\n" in text
    has_bare_lf = "\n" in text.replace("\r\n", "")
    if has_crlf and has_bare_lf:
        fail(f"{label} contains mixed LF and CRLF newlines")
    newline = "\r\n" if has_crlf else "\n"
    normalized = text.replace("\r\n", "\n")
    final_newline = normalized.endswith("\n")
    return normalized, TextStyle(bom=bom, newline=newline, final_newline=final_newline)


def style_for(path: Path) -> tuple[str, TextStyle]:
    if not path.exists():
        return "", TextStyle(bom=False, newline="\n", final_newline=True)
    if not path.is_file() or path.is_symlink():
        fail(f"output path is not a regular non-symlink file: {path.name}")
    return decode_document(path.read_bytes(), path.name)


def encode_document(normalized: str, style: TextStyle) -> bytes:
    body = normalized.rstrip("\n")
    if style.final_newline:
        body += "\n"
    if style.newline == "\r\n":
        body = body.replace("\n", "\r\n")
    encoded = body.encode("utf-8")
    return (b"\xef\xbb\xbf" if style.bom else b"") + encoded


def resolve_base_url(root: Path, explicit: str, repository: str) -> str:
    if explicit.strip():
        return normalize_origin(explicit, "base_url")
    cname = root / "CNAME"
    if is_tracked(root, "CNAME"):
        text, _ = style_for(cname)
        values = [line.strip() for line in text.split("\n") if line.strip()]
        if len(values) != 1 or any(char.isspace() for char in values[0]):
            fail("tracked CNAME must contain exactly one hostname")
        return normalize_origin(f"https://{values[0]}", "CNAME")
    parts = repository.split("/", 1)
    if len(parts) != 2 or not parts[1].strip():
        fail("repository must use OWNER/NAME form when base_url and tracked CNAME are absent")
    return normalize_origin(f"https://{parts[1].strip().lower()}", "repository name")


def tracked_html_paths(root: Path) -> list[str]:
    raw = git_bytes(root, "ls-files", "-z")
    paths: list[str] = []
    root_resolved = root.resolve()
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            relative = item.decode("utf-8", "strict")
        except UnicodeDecodeError:
            fail("tracked path is not strict UTF-8")
        if not relative.casefold().endswith(".html"):
            continue
        if any(ord(char) < 32 or ord(char) == 127 for char in relative):
            fail(f"tracked HTML path contains a control character: {relative!r}")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
            fail(f"unsafe tracked HTML path: {relative}")
        resolved = (root / Path(*pure.parts)).resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            fail(f"tracked HTML path escapes the repository: {relative}")
        if not resolved.is_file() or resolved.is_symlink():
            fail(f"tracked HTML path is absent, non-file, or symlinked: {relative}")
        paths.append(relative)
    ordered = sorted(set(paths), key=lambda item: item.encode("utf-8"))
    if len(ordered) != len(paths):
        fail("tracked HTML path list contains duplicates")
    return ordered


def git_lastmod_map(root: Path, tracked: list[str]) -> dict[str, str]:
    output = git_bytes(
        root,
        "-c",
        "core.quotepath=false",
        "log",
        "--format=%x1e%cI",
        "--name-only",
        "--no-renames",
        "--",
    )
    wanted = set(tracked)
    found: dict[str, str] = {}
    for record in output.decode("utf-8", "strict").split("\x1e"):
        if not record.strip():
            continue
        lines = record.lstrip("\n").splitlines()
        if not lines:
            continue
        try:
            instant = datetime.fromisoformat(lines[0].strip())
        except ValueError:
            fail(f"Git returned an invalid commit timestamp: {lines[0]!r}")
        if instant.tzinfo is None:
            fail("Git returned a commit timestamp without a timezone")
        lastmod = instant.astimezone(timezone.utc).isoformat(timespec="seconds")
        for relative in lines[1:]:
            if relative in wanted and relative not in found:
                found[relative] = lastmod
        if len(found) == len(wanted):
            break
    missing = sorted(wanted.difference(found), key=lambda item: item.encode("utf-8"))
    if missing:
        fail(f"Git history does not provide lastmod evidence for {len(missing)} tracked HTML paths")
    return found


def route_for(relative: str) -> str:
    pure = PurePosixPath(relative)
    if pure.name.casefold() == "index.html":
        route_parts = pure.parts[:-1]
        suffix = "/"
    else:
        route_parts = (*pure.parts[:-1], pure.name[:-5])
        suffix = ""
    encoded = "/".join(quote(part, safe="-._~") for part in route_parts)
    if not encoded:
        return "/"
    return f"/{encoded}{suffix}"


def build_pages(root: Path, base_url: str, minimum_urls: int) -> list[Page]:
    paths = tracked_html_paths(root)
    if len(paths) < minimum_urls:
        fail(f"tracked HTML URL count {len(paths)} is below required minimum {minimum_urls}")
    if not paths:
        fail("no tracked HTML files were found")
    lastmods = git_lastmod_map(root, paths)
    pages = [Page(path, base_url + route_for(path), lastmods[path]) for path in paths]
    urls = [page.url for page in pages]
    if len(urls) != len(set(urls)):
        duplicates = sorted({url for url in urls if urls.count(url) > 1})
        fail("multiple tracked HTML paths map to the same URL: " + json.dumps(duplicates, ensure_ascii=False))
    return sorted(pages, key=lambda page: page.url.encode("utf-8"))


def render_sitemap(pages: list[Page]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for page in pages:
        lines.extend(
            (
                "  <url>",
                f"    <loc>{xml_escape(page.url)}</loc>",
                f"    <lastmod>{page.lastmod}</lastmod>",
                "    <priority>0.80</priority>",
                "  </url>",
            )
        )
    lines.append("</urlset>")
    return "\n".join(lines)


def search_link(url: str) -> str:
    query = quote_plus(f"site:{url}", safe="")
    return f"- [{url}](https://www.google.com/search?q={query})"


def render_url_list(pages: list[Page]) -> str:
    return "\n".join(search_link(page.url) for page in pages)


def render_managed_block(pages: list[Page]) -> str:
    body = [BEGIN_MARKER, "## Sitemap URLs", f"Number of URLs: {len(pages)}", ""]
    body.extend(search_link(page.url) for page in pages)
    body.append(END_MARKER)
    return "\n".join(body)


def is_legacy_only_readme(text: str) -> bool:
    lines = text.strip("\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) < 2 or lines[0].strip() != "## Sitemap URLs" or not LEGACY_COUNT.fullmatch(lines[1].strip()):
        return False
    content = [line for line in lines[2:] if line.strip()]
    return bool(content) and all(LEGACY_LINK.fullmatch(line) for line in content)


def update_readme(existing: str, block: str) -> str:
    lines = existing.split("\n")
    starts = [index for index, line in enumerate(lines) if line == BEGIN_MARKER]
    ends = [index for index, line in enumerate(lines) if line == END_MARKER]
    marker_text_present = BEGIN_MARKER in existing or END_MARKER in existing
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            fail("README managed sitemap markers are missing, duplicated, or reversed")
        replacement = block.split("\n")
        return "\n".join(lines[: starts[0]] + replacement + lines[ends[0] + 1 :]).rstrip("\n")
    if marker_text_present:
        fail("README managed sitemap markers must occupy exact standalone lines")
    if is_legacy_only_readme(existing):
        return block
    base = existing.rstrip("\n")
    return f"{base}\n\n{block}" if base else block


def atomic_replace(path: Path, data: bytes) -> None:
    if path.exists() and (not path.is_file() or path.is_symlink()):
        fail(f"output path is not a regular non-symlink file: {path.name}")
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
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
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def publish_control_files(
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
        stream.write(f"url_count={summary['url_count']}\n")


def generate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not (root / ".git").is_dir():
        fail("root must be a Git checkout")
    minimum_urls = parse_nonnegative_integer(args.minimum_urls, "minimum_urls")
    if args.url_list_mode not in ("auto", "include", "exclude"):
        fail("url_list_mode must be auto, include, or exclude")
    base_url = resolve_base_url(root, args.base_url, args.repository)
    pages = build_pages(root, base_url, minimum_urls)

    sitemap_path = root / SITEMAP_PATH
    readme_path = root / README_PATH
    url_list_path = root / URL_LIST_PATH
    sitemap_existing, sitemap_style = style_for(sitemap_path)
    readme_existing, readme_style = style_for(readme_path)
    manage_url_list = args.url_list_mode == "include" or (
        args.url_list_mode == "auto" and is_tracked(root, URL_LIST_PATH)
    )
    url_existing, url_style = style_for(url_list_path) if manage_url_list else ("", TextStyle(False, "\n", True))

    desired: dict[str, bytes] = {
        SITEMAP_PATH: encode_document(render_sitemap(pages), sitemap_style),
        README_PATH: encode_document(update_readme(readme_existing, render_managed_block(pages)), readme_style),
    }
    if manage_url_list:
        desired[URL_LIST_PATH] = encode_document(render_url_list(pages), url_style)

    originals = {
        relative: (root / relative).read_bytes() if (root / relative).exists() else None for relative in desired
    }
    changed = sorted(
        [relative for relative, data in desired.items() if originals[relative] != data],
        key=lambda item: item.encode("utf-8"),
    )
    for relative in changed:
        atomic_replace(root / relative, desired[relative])

    summary: dict[str, object] = {
        "schema_version": "sitemap-readme-generation-summary-v1",
        "base_url": base_url,
        "url_count": len(pages),
        "url_list_mode": args.url_list_mode,
        "url_list_managed": manage_url_list,
        "changed_files": changed,
    }
    publish_control_files(
        Path(args.paths_file).resolve(),
        Path(args.summary_file).resolve(),
        Path(args.github_output).resolve(),
        changed,
        summary,
    )
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
        if relative not in ALLOWED_OUTPUTS:
            fail(f"unsafe output path in paths file: {relative}")
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
            fail("rename/copy status is outside the generation contract")
        relative = record[3:].decode("utf-8", "strict")
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
    allowed = {" M", "??"} if args.state == "unstaged" else {"M ", "A "}
    bad = {path: actual[path] for path in expected if actual[path] not in allowed}
    if bad:
        fail(f"unexpected Git status for {args.state}: {json.dumps(bad, separators=(',', ':'))}")
    print(json.dumps({"status": "pass", "state": args.state, "paths": len(expected)}, separators=(",", ":")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    generator = commands.add_parser("generate")
    generator.add_argument("--root", required=True)
    generator.add_argument("--repository", required=True)
    generator.add_argument("--base-url", default="")
    generator.add_argument("--minimum-urls", required=True)
    generator.add_argument("--url-list-mode", required=True)
    generator.add_argument("--paths-file", required=True)
    generator.add_argument("--summary-file", required=True)
    generator.add_argument("--github-output", required=True)
    verifier = commands.add_parser("verify-git")
    verifier.add_argument("--root", required=True)
    verifier.add_argument("--paths-file", required=True)
    verifier.add_argument("--state", required=True, choices=("unstaged", "staged"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "generate":
        return generate(args)
    return verify_git(args)


if __name__ == "__main__":
    raise SystemExit(main())
