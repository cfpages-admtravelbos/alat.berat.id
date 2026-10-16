#!/usr/bin/env python3
"""High-Efficiency Heuristic Image Alt, 80/20 Internal Linking, & Robots.txt Engine.

Features:
- Standardizes robots.txt across commercial sites (Disallow /cdn-cgi/ to prevent Cloudflare 404s).
- Isolates Short.io tracker subdomains (track.*, link.*, klik.*) with Disallow: /.
- Infers page context from permalink / directory / filename in < 0.1ms per file (zero DOM overhead).
- Supports both flat files (page.html) and pretty permalink folders (dir/index.html).
- Wraps unlinked content images with internal links weighted 80% to Tier-1 high-value cities.
- Injects descriptive Indonesian alt attributes while preserving HTML byte integrity.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Tier-1 Indonesian Commercial Powerhouse Cities (~20% locations, ~80% revenue)
TIER1_CITIES: Set[str] = {
    # Jabodetabek Megapolitan
    "jakarta",
    "jakarta-pusat",
    "jakarta-selatan",
    "jakarta-barat",
    "jakarta-timur",
    "jakarta-utara",
    "bogor",
    "depok",
    "tangerang",
    "tangerang-selatan",
    "bekasi",
    # Java Economic Hubs
    "surabaya",
    "bandung",
    "semarang",
    "solo",
    "surakarta",
    "malang",
    "sidoarjo",
    "cirebon",
    "yogyakarta",
    "sleman",
    # Major Outer-Island Commercial Hubs
    "medan",
    "makassar",
    "denpasar",
    "badung",
    "palembang",
    "balikpapan",
    "samarinda",
    "batam",
    "pekanbaru",
    "bandar-lampung",
}

UTILITY_PAGES: Set[str] = {
    "index.html",
    "404.html",
    "about.html",
    "contact.html",
    "privacy-policy.html",
    "terms.html",
    "disclaimer.html",
    "sitemap.html",
}

EXCLUDED_DIRS: Set[str] = {
    ".git",
    ".github",
    ".opencodereview",
    "wp-content",
    "wp-includes",
    "wp-json",
    "node_modules",
    "dist",
    "assets",
    "css",
    "js",
    "img",
    "images",
    "fonts",
}

TRACKER_PREFIXES: Tuple[str, ...] = ("track.", "link.", "klik.")


@dataclass(frozen=True)
class PageContext:
    file_path: Path
    slug: str
    target_href: str
    product_title: str
    city_title: str
    is_tier1: bool


def is_tracker_domain(domain_or_repo: str) -> bool:
    clean = domain_or_repo.lower().strip()
    return any(clean.startswith(prefix) for prefix in TRACKER_PREFIXES)


def detect_domain(root: Path, repo_name: Optional[str] = None) -> str:
    # 1. CNAME file
    cname_file = root / "CNAME"
    if cname_file.is_file():
        domain = cname_file.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[0]
        if domain:
            return domain.lower()

    # 2. Canonical tag in index.html or first HTML
    for html_file in root.glob("*.html"):
        try:
            head = html_file.read_text(encoding="utf-8", errors="ignore")[:4000]
            m = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']https?://([^/\'"]+)', head, re.I)
            if m:
                return m.group(1).lower()
        except Exception:
            continue

    # 3. Fallback to repo name or folder name
    name = repo_name or root.name
    return name.lower()


def ensure_robots_txt(root: Path, domain: str) -> Tuple[bool, str]:
    robots_path = root / "robots.txt"
    is_tracker = is_tracker_domain(domain) or is_tracker_domain(root.name)

    if is_tracker:
        expected = "User-agent: *\nDisallow: /\n"
    else:
        sitemap_name = "sitemap-complete.xml" if (root / "sitemap-complete.xml").is_file() else "sitemap.xml"
        expected = f"User-agent: *\nAllow: /\nDisallow: /cdn-cgi/\n\nSitemap: https://{domain}/{sitemap_name}\n"

    if not robots_path.is_file():
        robots_path.write_text(expected, encoding="utf-8")
        return True, "created"

    current = robots_path.read_text(encoding="utf-8", errors="ignore")
    if is_tracker:
        if "Disallow: /" in current and "Allow: /" not in current:
            return False, "already_tracker_clean"
        robots_path.write_text(expected, encoding="utf-8")
        return True, "overwritten_tracker"
    else:
        if "Disallow: /cdn-cgi/" in current:
            return False, "already_has_cdn_cgi"
        # Append Disallow: /cdn-cgi/ under User-agent: *
        if "User-agent: *" in current:
            updated = re.sub(r"(User-agent:\s*\*[^\n]*\n)", r"\1Disallow: /cdn-cgi/\n", current, count=1, flags=re.I)
        else:
            updated = f"User-agent: *\nDisallow: /cdn-cgi/\n\n{current}"
        robots_path.write_text(updated, encoding="utf-8")
        return True, "appended_cdn_cgi"


def clean_slug_to_title(slug: str) -> str:
    tokens = slug.replace("_", "-").split("-")
    cleaned = [t.capitalize() for t in tokens if t and not t.isdigit()]
    return " ".join(cleaned)


def extract_image_keywords(src: str) -> str:
    filename = os.path.basename(urllib.parse.urlsplit(src).path)
    base, _ = os.path.splitext(filename)
    base = urllib.parse.unquote(base)
    tokens = re.findall(r"[a-zA-Z]+", base)
    stop = {
        "wp", "content", "uploads", "img", "image", "dsc", "photo",
        "s", "jpg", "jpeg", "png", "webp", "gif", "large", "thumb"
    }
    meaningful = [t.capitalize() for t in tokens if len(t) > 2 and t.lower() not in stop]
    return " ".join(meaningful[:2])


def detect_common_product_prefix(slugs: List[str]) -> str:
    candidates: Dict[str, int] = {}
    for base in slugs:
        parts = base.split("-")
        for i in range(1, min(len(parts), 5)):
            prefix = "-".join(parts[:i])
            candidates[prefix] = candidates.get(prefix, 0) + 1
    if not candidates:
        return "Layanan"
    sorted_prefixes = sorted(candidates.items(), key=lambda x: (-x[1], -len(x[0])))
    best_prefix, best_count = sorted_prefixes[0]
    return best_prefix if best_count >= max(2, len(slugs) * 0.2) else ""


def parse_page_context(slug: str, common_prefix: str) -> Tuple[str, str, str]:
    if common_prefix and slug.startswith(common_prefix + "-"):
        city_slug = slug[len(common_prefix) + 1 :]
        product_slug = common_prefix
    else:
        parts = slug.split("-")
        if len(parts) >= 2:
            city_slug = parts[-1]
            product_slug = "-".join(parts[:-1])
        else:
            city_slug = slug
            product_slug = "Layanan"

    product_title = clean_slug_to_title(product_slug) or "Layanan"
    city_title = clean_slug_to_title(city_slug) or "Indonesia"
    return product_title, city_title, city_slug


def discover_pages(root: Path) -> List[PageContext]:
    raw_pages: List[Tuple[Path, str, str]] = []  # (file_path, slug, target_href)

    # 1. Flat root HTML files
    for f in root.glob("*.html"):
        if f.name not in UTILITY_PAGES:
            slug = f.stem
            target_href = f"/{f.name}"
            raw_pages.append((f, slug, target_href))

    # 2. Subdirectory index.html files (pretty permalinks)
    for d in root.iterdir():
        if d.is_dir() and d.name not in EXCLUDED_DIRS and not d.name.startswith("."):
            idx_file = d / "index.html"
            if idx_file.is_file():
                slug = d.name
                target_href = f"/{d.name}/"
                raw_pages.append((idx_file, slug, target_href))

    if not raw_pages:
        return []

    slugs = [slug for _, slug, _ in raw_pages]
    common_prefix = detect_common_product_prefix(slugs)

    contexts: List[PageContext] = []
    for f_path, slug, href in raw_pages:
        p_title, c_title, c_slug = parse_page_context(slug, common_prefix)
        is_t1 = c_slug.lower() in TIER1_CITIES
        contexts.append(
            PageContext(
                file_path=f_path,
                slug=slug,
                target_href=href,
                product_title=p_title,
                city_title=c_title,
                is_tier1=is_t1,
            )
        )
    return contexts


def process_html_file(
    current: PageContext,
    all_pages: List[PageContext],
) -> Tuple[bool, int, int]:
    html = current.file_path.read_text(encoding="utf-8", errors="ignore")

    # Filter out current page from candidate target pools
    candidates = [p for p in all_pages if p.slug != current.slug]
    t1_pool = [p for p in candidates if p.is_tier1]
    regional_pool = [p for p in candidates if not p.is_tier1]

    # Target content section only
    content_match = re.search(
        r"(<div[^>]*class=[\"'][^\"']*entry-content[^\"']*[\"'][^>]*>|<article\b[^>]*>|<main\b[^>]*>)(.*?)(</article>|</main>|<footer|<!-- \.entry-content)",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not content_match:
        return False, 0, 0

    content_start = content_match.start(2)
    content_end = content_match.end(2)
    content_body = content_match.group(2)

    img_matches = list(re.finditer(r"<img\b[^>]*>", content_body, re.IGNORECASE))
    if not img_matches:
        return False, 0, 0

    replacements: List[Tuple[int, int, str]] = []
    links_added = 0
    alts_enriched = 0

    for idx, m in enumerate(img_matches):
        img_tag = m.group(0)
        img_start, img_end = m.start(), m.end()

        # Check if img is already wrapped in an anchor
        pre = content_body[max(0, img_start - 300) : img_start]
        is_in_anchor = False
        a_open_idx = pre.lower().rfind("<a ")
        if a_open_idx != -1:
            a_close_idx = pre.lower().rfind("</a>")
            if a_close_idx < a_open_idx:
                is_in_anchor = True

        src_m = re.search(r'src=["\']([^"\']+)["\']', img_tag, re.IGNORECASE)
        alt_m = re.search(r'alt=["\']([^"\']*)["\']', img_tag, re.IGNORECASE)
        src = src_m.group(1) if src_m else ""
        existing_alt = alt_m.group(1).strip() if alt_m else ""

        img_kw = extract_image_keywords(src)
        needs_alt = not existing_alt

        if is_in_anchor:
            # Preserve anchor, update alt if empty
            if needs_alt:
                desc_parts = [current.product_title]
                if img_kw and img_kw.lower() not in current.product_title.lower():
                    desc_parts.append(img_kw)
                desc_parts.append(current.city_title)
                new_alt = " ".join(desc_parts)

                if alt_m:
                    new_tag = img_tag[: alt_m.start(1)] + new_alt + img_tag[alt_m.end(1) :]
                else:
                    new_tag = img_tag[:-1] + f' alt="{new_alt}">'
                replacements.append((img_start, img_end, new_tag))
                alts_enriched += 1
        else:
            # Unlinked image: pick target city using 80/20 Pareto rule
            seed_str = f"{current.slug}:{src}:{idx}"
            seed_int = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:8], 16)
            prob = seed_int % 100

            if prob < 80 and t1_pool:
                target = t1_pool[seed_int % len(t1_pool)]
            elif regional_pool:
                target = regional_pool[seed_int % len(regional_pool)]
            elif candidates:
                target = candidates[seed_int % len(candidates)]
            else:
                continue

            # Alt phrasing variations
            var_idx = (seed_int >> 8) % 4
            if var_idx == 0:
                alt_base = f"{target.product_title} {target.city_title}"
            elif var_idx == 1:
                alt_base = f"Jual & Pasang {target.product_title} di {target.city_title}"
            elif var_idx == 2:
                alt_base = f"Spesialis {target.product_title} Berkualitas {target.city_title}"
            else:
                alt_base = f"Pemasangan {target.product_title} Proyek {target.city_title}"

            # Blend image keyword if distinct
            if img_kw and img_kw.lower() not in alt_base.lower():
                alt_base = f"{alt_base} - {img_kw}"

            if alt_m:
                new_img_tag = img_tag[: alt_m.start(1)] + alt_base + img_tag[alt_m.end(1) :]
            else:
                new_img_tag = img_tag[:-1] + f' alt="{alt_base}">'

            wrapped_tag = f'<a href="{target.target_href}" title="{target.product_title} {target.city_title}">{new_img_tag}</a>'
            replacements.append((img_start, img_end, wrapped_tag))
            links_added += 1
            alts_enriched += 1

    if not replacements:
        return False, 0, 0

    # Apply replacements from back to front to maintain character offsets
    replacements.sort(key=lambda x: x[0], reverse=True)
    mod_body = content_body
    for s, e, new_str in replacements:
        mod_body = mod_body[:s] + new_str + mod_body[e:]

    new_html = html[:content_start] + mod_body + html[content_end:]
    current.file_path.write_text(new_html, encoding="utf-8")
    return True, links_added, alts_enriched


def run(root_dir: str, domain: Optional[str] = None, check_only: bool = False) -> Dict[str, object]:
    root = Path(root_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"Target directory does not exist: {root}")

    detected_dom = domain or detect_domain(root)

    # 1. Robots.txt
    robots_changed, robots_status = False, "unchanged"
    if not check_only:
        robots_changed, robots_status = ensure_robots_txt(root, detected_dom)

    # 2. Discover all pages (flat and pretty permalink)
    all_pages = discover_pages(root)
    t1_count = sum(1 for p in all_pages if p.is_tier1)
    reg_count = len(all_pages) - t1_count

    modified_files = 0
    total_links_added = 0
    total_alts_enriched = 0

    if not check_only:
        for page in all_pages:
            changed, links, alts = process_html_file(page, all_pages)
            if changed:
                modified_files += 1
                total_links_added += links
                total_alts_enriched += alts

    return {
        "status": "success",
        "domain": detected_dom,
        "is_tracker": is_tracker_domain(detected_dom),
        "robots_status": robots_status,
        "robots_changed": robots_changed,
        "total_html_files": len(all_pages),
        "tier1_city_pages": t1_count,
        "regional_city_pages": reg_count,
        "modified_files": modified_files,
        "total_links_added": total_links_added,
        "total_alts_enriched": total_alts_enriched,
    }


def main():
    parser = argparse.ArgumentParser(description="Portfolio SEO Robots.txt & Image Linking Engine")
    parser.add_argument("--root", default=".", help="Root directory of repository")
    parser.add_argument("--domain", default=None, help="Explicit domain override")
    parser.add_argument("--check-only", action="store_true", help="Audit mode without file mutation")
    args = parser.parse_args()

    result = run(args.root, args.domain, args.check_only)
    print(
        f"Domain: {result['domain']} (Tracker: {result['is_tracker']}) | "
        f"Robots: {result['robots_status']} | "
        f"Files: {result['modified_files']}/{result['total_html_files']} modified | "
        f"Links: +{result['total_links_added']} | "
        f"Alts: +{result['total_alts_enriched']}"
    )


if __name__ == "__main__":
    main()
