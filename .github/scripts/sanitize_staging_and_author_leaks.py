#!/usr/bin/env python3
"""Canonical Engine: Sanitize Staging URLs, Rank Math Schema & Author Leaks.

Eradicates cross-site footprints:
1. Purges leftover staging URLs (http://adisty.my.id, https://adisty.my.id, httpsadisty.my.id, escaped JSON).
2. Converts asset URLs (/wp-content/, /wp-includes/, /wp-admin/) to root-relative paths.
3. Sanitizes Rank Math JSON-LD schema and on-page author elements referencing "Syamsul Alam"
   or author archives, replacing them with site-branded Organization schema.
4. Deletes leftover WordPress static author archive directories (author/Syamsul Alam, author/syamsul-alam, author/admin).
5. Preserves UTF-8 BOM, line endings (CRLF/LF), and guarantees 100% idempotency.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Set, Tuple


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


def decode_document(data: bytes, label: str) -> Tuple[str, TextStyle]:
    bom = data.startswith(b"\xef\xbb\xbf")
    payload = data[3:] if bom else data
    try:
        text = payload.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} is not strict UTF-8: {exc}")
    has_crlf = "\r\n" in text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
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


def detect_domain_and_brand(root: Path) -> Tuple[str, str]:
    """Detect authoritative domain and human brand name from repository evidence."""
    domain = ""
    cname_file = root / "CNAME"
    if cname_file.is_file():
        cname_val = cname_file.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        if cname_val and "." in cname_val[0]:
            domain = cname_val[0].strip().lower()

    if not domain:
        index_file = root / "index.html"
        if index_file.is_file():
            content = index_file.read_text(encoding="utf-8", errors="ignore")
            canon_match = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']https?://([^/\s"\'>]+)', content, re.IGNORECASE)
            if canon_match and "." in canon_match.group(1):
                cand = canon_match.group(1).lower()
                if "adisty.my.id" not in cand and "bajabesi.co.id" not in cand:
                    domain = cand

    if not domain:
        proc = subprocess.run(["git", "-C", str(root), "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=False)
        url = proc.stdout.strip()
        if url:
            repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
            if "." in repo_name:
                domain = repo_name.lower()

    if not domain:
        dir_name = root.resolve().name
        if "." in dir_name:
            domain = dir_name.lower()
        else:
            domain = "official-site.co.id"

    # Derive clean Brand Name from domain
    base = domain
    for prefix in ("www.", "cfpages-"):
        if base.startswith(prefix):
            base = base[len(prefix):]
    parts = base.split(".")
    if len(parts) >= 2:
        brand_raw = parts[0]
        # if multi-level subdomain like plat.besi.co.id
        if len(parts) > 2 and parts[-2] in ("co", "net", "web", "or", "biz") and parts[-1] == "id":
            if len(parts) > 3:
                brand_raw = f"{parts[0]} {parts[1]}"
            else:
                brand_raw = parts[0]
        brand_name = brand_raw.title().replace("-", " ")
    else:
        brand_name = base.title()

    return domain, brand_name


def tracked_text_paths(root: Path) -> List[str]:
    raw = git_bytes(root, "-c", "core.quotepath=false", "ls-files", "-z")
    candidates: List[Tuple[str, PurePosixPath]] = []
    text_extensions = {".html", ".htm", ".xml", ".xsl", ".json"}
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            relative = item.decode("utf-8", "strict")
        except UnicodeDecodeError:
            continue
        pure = safe_relative_path(relative, "tracked path")
        suffix = pure.suffix.casefold()
        if suffix in text_extensions or relative in ("robots.txt", "_redirects"):
            candidates.append((relative, pure))
    ordered = sorted(candidates, key=lambda item: item[0].encode("utf-8"))
    return [item[0] for item in ordered]


def sanitize_text_content(content: str, domain: str, brand: str) -> Tuple[str, int, int]:
    """Sanitize staging domain URLs, Rank Math Schema, and author entity leaks in text content.
    
    Returns (sanitized_text, staging_url_replacements_count, author_replacements_count).
    """
    modified = content
    staging_count = 0
    author_count = 0

    # 1. Clean Staging Domain URLs (adisty.my.id)
    # 1a. Escaped JSON patterns
    json_patterns = [
        (re.compile(r"https?:\\/\\/(?:www\.)?adisty\.my\.id\\/wp-content\\/", re.IGNORECASE), r"\/wp-content\/"),
        (re.compile(r"https?:\\/\\/(?:www\.)?adisty\.my\.id\\/wp-includes\\/", re.IGNORECASE), r"\/wp-includes\/"),
        (re.compile(r"https?:\\/\\/(?:www\.)?adisty\.my\.id\\/wp-admin\\/", re.IGNORECASE), r"\/wp-admin\/"),
        (re.compile(r"https?:\\/\\/(?:www\.)?adisty\.my\.id\\/wp-json\\/", re.IGNORECASE), r"\/wp-json\/"),
        (re.compile(r"https?:\\/\\/(?:www\.)?adisty\.my\.id\\/author\\/", re.IGNORECASE), r"\/"),
        (re.compile(r"https?:\\/\\/(?:www\.)?adisty\.my\.id\\/", re.IGNORECASE), r"\/"),
        (re.compile(r"https?:\\/\\/(?:www\.)?adisty\.my\.id", re.IGNORECASE), f"https:\\/\\/{domain}"),
    ]
    for pattern, repl in json_patterns:
        matches = len(pattern.findall(modified))
        if matches > 0:
            modified = pattern.sub(repl, modified)
            staging_count += matches

    # 1b. Standard HTML / Plain text URL patterns
    text_patterns = [
        # wp-content, wp-includes, wp-admin root-relative
        (re.compile(r"https?://(?:www\.)?adisty\.my\.id/wp-content/", re.IGNORECASE), "/wp-content/"),
        (re.compile(r"https?://(?:www\.)?adisty\.my\.id/wp-includes/", re.IGNORECASE), "/wp-includes/"),
        (re.compile(r"https?://(?:www\.)?adisty\.my\.id/wp-admin/", re.IGNORECASE), "/wp-admin/"),
        (re.compile(r"https?://(?:www\.)?adisty\.my\.id/wp-json/", re.IGNORECASE), "/wp-json/"),
        (re.compile(r"httpsadisty\.my\.id/wp-content/", re.IGNORECASE), "/wp-content/"),
        (re.compile(r"httpsadisty\.my\.id/wp-includes/", re.IGNORECASE), "/wp-includes/"),
        (re.compile(r"httpsadisty\.my\.id/wp-admin/", re.IGNORECASE), "/wp-admin/"),
        # Redirect stubs / window.location
        (re.compile(r'content=["\']0;\s*url=httpsadisty\.my\.id/([^"\']*)["\']', re.IGNORECASE), r'content="0;url=/\1"'),
        (re.compile(r'window\.location\s*=\s*["\']httpsadisty\.my\.id/([^"\']*)["\']', re.IGNORECASE), r'window.location = "/\1"'),
        (re.compile(r'<a\s+href=["\']httpsadisty\.my\.id/([^"\']*)["\']', re.IGNORECASE), r'<a href="/\1"'),
        # Schema and generic leftover httpsadisty.my.id
        (re.compile(r"httpsadisty\.my\.id/#", re.IGNORECASE), f"https://{domain}/#"),
        (re.compile(r"httpsadisty\.my\.id/", re.IGNORECASE), f"https://{domain}/"),
        (re.compile(r"httpsadisty\.my\.id", re.IGNORECASE), f"https://{domain}"),
        (re.compile(r"https?://(?:www\.)?adisty\.my\.id/", re.IGNORECASE), f"https://{domain}/"),
        (re.compile(r"https?://(?:www\.)?adisty\.my\.id", re.IGNORECASE), f"https://{domain}"),
    ]
    for pattern, repl in text_patterns:
        matches = len(pattern.findall(modified))
        if matches > 0:
            modified = pattern.sub(repl, modified)
            staging_count += matches

    # 2. Clean Author and Syamsul Alam Entity Leaks
    # 2a. Rank Math JSON-LD Schema
    def clean_rank_math_schema(match: re.Match[str]) -> str:
        nonlocal author_count
        raw_schema = match.group(1)
        schema_text = raw_schema
        # Replace author Person/Organization references
        schema_text = re.sub(
            r'\["Person",\s*"Organization"\]',
            '"Organization"',
            schema_text,
        )
        schema_text = re.sub(
            r'\{"@type":\s*"Person",\s*"@id":\s*"[^"]*author[^"]*",\s*"name":\s*"[^"]*"(?:,\s*"[^"]*":\s*(?:\{[^{}]*\}|"[^"]*"))*\}',
            f'{{"@type":"Organization","@id":"https://{domain}/#organization","name":"{brand}"}}',
            schema_text,
        )
        # Author field in Article
        schema_text = re.sub(
            r'"author":\s*\{"@id":\s*"[^"]*",\s*"name":\s*"(?:Syamsul Alam|syamsul|admin)"\}',
            f'"author":{{"@id":"https://{domain}/#organization","name":"{brand}"}}',
            schema_text,
            flags=re.IGNORECASE,
        )
        schema_text = re.sub(
            r'"author":\s*\{"@type":\s*"Person",\s*"name":\s*"(?:Syamsul Alam|syamsul|admin)"\}',
            f'"author":{{"@type":"Organization","name":"{brand}"}}',
            schema_text,
            flags=re.IGNORECASE,
        )
        # Publisher references
        schema_text = re.sub(
            r'"publisher":\s*\{"@id":\s*"(?:/#person|https://[^"]*/#person)"\}',
            f'"publisher":{{"@id":"https://{domain}/#organization"}}',
            schema_text,
        )
        # Any residual "name":"Syamsul Alam" in schema
        schema_text = re.sub(
            r'"name":\s*"(?:Syamsul Alam|syamsul)"',
            f'"name":"{brand}"',
            schema_text,
            flags=re.IGNORECASE,
        )
        if schema_text != raw_schema:
            author_count += 1
        return f'<script type="application/ld+json" class="rank-math-schema">{schema_text}</script>'

    modified = re.sub(
        r'<script\s+type=["\']application/ld\+json["\']\s+class=["\']rank-math-schema["\']>(.*?)</script>',
        clean_rank_math_schema,
        modified,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 2b. Visible Author Bio Elements (Elementor / Astra)
    visible_patterns = [
        # Elementor author name box
        (
            re.compile(r'(<div class="elementor-icon-box-title">\s*<span>)\s*Syamsul\s+Alam\s*(</span>\s*</div>)', re.IGNORECASE),
            rf'\1Tim {brand}\2',
        ),
        # Elementor author description box
        (
            re.compile(r'(<p class="elementor-icon-box-description">\s*)Founder\s+[^<]+(\s*</p>)', re.IGNORECASE),
            rf'\1Tim Layanan {brand}\2',
        ),
        # On-page author links
        (
            re.compile(r'href=["\'](?:https?://[^"\']*)?/author/(?:syamsul-alam|Syamsul%20Alam|syamsul|admin)/?["\']', re.IGNORECASE),
            'href="/"',
        ),
        # OpenGraph / Meta author URLs
        (
            re.compile(r'<meta\s+property=["\']og:url["\']\s+content=["\'][^"\']*/author/[^"\']*["\']>', re.IGNORECASE),
            f'<meta property="og:url" content="https://{domain}/">',
        ),
        (
            re.compile(r'<meta\s+property=["\']og:title["\']\s+content=["\']-\s*Syamsul\s+Alam[^"\']*["\']>', re.IGNORECASE),
            f'<meta property="og:title" content="{brand}">',
        ),
        (
            re.compile(r'<link\s+rel=["\']author["\']\s+href=["\'][^"\']*["\']>', re.IGNORECASE),
            "",
        ),
    ]
    for pattern, repl in visible_patterns:
        matches = len(pattern.findall(modified))
        if matches > 0:
            modified = pattern.sub(repl, modified)
            author_count += matches

    return modified, staging_count, author_count


def delete_tracked_author_archives(root: Path, apply: bool) -> List[str]:
    """Find and delete tracked author archive files and directories."""
    raw = git_bytes(root, "-c", "core.quotepath=false", "ls-files", "-z")
    deleted: List[str] = []
    author_prefixes = ("author/syamsul", "author/Syamsul", "author/admin", "author/feed")
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            rel = item.decode("utf-8", "strict")
        except UnicodeDecodeError:
            continue
        rel_norm = rel.replace("\\", "/")
        if any(rel_norm.startswith(prefix) for prefix in author_prefixes):
            deleted.append(rel)

    if deleted and apply:
        # Use git rm for tracked files
        for chunk_start in range(0, len(deleted), 50):
            chunk = deleted[chunk_start:chunk_start + 50]
            git_result(root, "rm", "-f", "--ignore-unmatch", "--", *chunk)
        # Also clean empty local directories if present
        author_dir = root / "author"
        if author_dir.is_dir():
            try:
                shutil.rmtree(str(author_dir), ignore_errors=True)
            except Exception:
                pass
    return deleted


def run(root: Path, apply: bool, check: bool) -> int:
    domain, brand = detect_domain_and_brand(root)
    print(f"[{root.name}] Target domain: {domain} | Brand identity: {brand}")

    tracked_paths = tracked_text_paths(root)
    modified_files: List[str] = []
    total_staging_purged = 0
    total_author_purged = 0

    for relative_path in tracked_paths:
        file_path = root / relative_path
        if not file_path.is_file():
            continue
        try:
            data = file_path.read_bytes()
            content, style = decode_document(data, relative_path)
        except Exception:
            continue

        sanitized, staging_c, author_c = sanitize_text_content(content, domain, brand)
        if sanitized != content:
            total_staging_purged += staging_c
            total_author_purged += author_c
            modified_files.append(relative_path)
            if apply:
                encoded = encode_document(sanitized, style)
                file_path.write_bytes(encoded)

    deleted_author_files = delete_tracked_author_archives(root, apply)

    summary = {
        "repository": root.name,
        "domain": domain,
        "brand": brand,
        "files_scanned": len(tracked_paths),
        "files_modified": len(modified_files),
        "staging_urls_purged": total_staging_purged,
        "author_leaks_purged": total_author_purged,
        "author_archive_files_deleted": len(deleted_author_files),
    }
    print(json.dumps(summary, indent=2))

    if check:
        if modified_files or deleted_author_files:
            print(f"FAIL: Repository contains {len(modified_files)} un-sanitized files and {len(deleted_author_files)} author archive files.")
            return 1
        print("PASS: Repository is 100% clean of staging URLs and author entity leaks.")
        return 0

    if apply and (modified_files or deleted_author_files):
        print(f"Sanitized {len(modified_files)} files and deleted {len(deleted_author_files)} author archive files.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Sanitize staging URLs, Rank Math Schema, and author entity leaks.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Root directory of the repository.")
    parser.add_argument("--apply", action="store_true", help="Apply sanitization in-place.")
    parser.add_argument("--check", action="store_true", help="Assert repository is 100% sanitized without writing.")
    args = parser.parse_args()

    exit_code = run(args.root.resolve(), apply=args.apply, check=args.check)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
