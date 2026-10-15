#!/usr/bin/env python3
"""Safely update checked-in HTML floating-contact markup from .clients."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote, urlsplit


class ClientsError(Exception):
    pass


@dataclass(frozen=True)
class Filter:
    clauses: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]
    simple: tuple[str, ...] = ()
    basename: tuple[str, ...] = ()
    page: tuple[str, ...] = ()


@dataclass(frozen=True)
class Client:
    row: int
    name: str
    phone: str | None
    whatsapp: str | None
    telephone: str | None
    filter: Filter | None
    address: str | None
    derive_routes: bool = False


FILTER_ATOM = r"-?[a-z0-9][a-z0-9._-]*"
SIMPLE_FILTER_RE = re.compile(rf"{FILTER_ATOM}(?:,{FILTER_ATOM})*\Z")
BASENAME_FILTER_RE = re.compile(rf"basename:{FILTER_ATOM}(?:,{FILTER_ATOM})*\Z")
PAGE_FILTER_RE = re.compile(rf"page:{FILTER_ATOM}(?:,{FILTER_ATOM})*\Z")
CATEGORY_FILTER_RE = re.compile(
    rf"{FILTER_ATOM}(?:,{FILTER_ATOM})*:{FILTER_ATOM}(?:,{FILTER_ATOM})*"
    rf"(?:;{FILTER_ATOM}(?:,{FILTER_ATOM})*:{FILTER_ATOM}(?:,{FILTER_ATOM})*)*\Z"
)
PHONE_RE = re.compile(r"\+?[0-9][0-9 ()+.\-]{6,}[0-9]\Z")
ADDRESS_RE = re.compile(r"(?:Jl\.|Jalan|Ruko|Perumahan)\s+[^<\r\n]+")
DIV_RE = re.compile(
    r"<div\b(?P<attrs>[^>]*\bclass\s*=\s*(?P<q>[\"'])"
    r"(?P<class>[^\"']*\b(?:whatsapp-floating|sms-floating|tlp-floating)\b[^\"']*)"
    r"(?P=q)[^>]*)>"
    r"(?P<body>.*?)</div\s*>",
    re.IGNORECASE | re.DOTALL,
)
NAV_RE = re.compile(
    r"<nav\b(?P<attrs>[^>]*)>(?P<body>.*?)</nav\s*>",
    re.IGNORECASE | re.DOTALL,
)
CLASS_ATTR_RE = re.compile(
    r"\bclass\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL
)
LI_RE = re.compile(r"<li\b(?P<attrs>[^>]*)>(?P<body>.*?)</li\s*>", re.IGNORECASE | re.DOTALL)
ANCHOR_RE = re.compile(
    r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a\s*>",
    re.IGNORECASE | re.DOTALL,
)
HREF_RE = re.compile(r"\bhref\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
SPAN_RE = re.compile(r"<span\b[^>]*>([^<>]+)</span\s*>", re.IGNORECASE | re.DOTALL)
DISPLAY_RE = re.compile(r"\+?[0-9][0-9 ()+.\-]{6,}[0-9]\s*\([^<>\r\n()]+\)")
MARKERS = {"whatsapp-floating", "sms-floating", "tlp-floating"}


def _error(row: int, reason: str) -> ClientsError:
    return ClientsError(f"row {row}: {reason}")


def _valid_url(value: str) -> tuple[str, str]:
    split = urlsplit(value)
    if split.scheme == "tel":
        if not split.path:
            raise ValueError
    elif split.scheme not in {"http", "https"} or not split.netloc:
        raise ValueError
    return split.scheme.lower(), (split.hostname or "").lower()


def _route_role(value: str) -> str | None:
    try:
        scheme, host = _valid_url(value)
    except ValueError:
        return None
    decoded = unquote(value)
    lower = decoded.casefold()
    whatsapp = (
        "💬" in decoded
        or "whatsapp" in lower
        or host == "wa.me"
        or host.endswith(".whatsapp.com")
    )
    telephone = (
        scheme == "tel"
        or "📞" in value
        or "☎" in value
        or "telephone" in lower
        or "contact" in lower
    )
    if whatsapp and telephone:
        return "ambiguous"
    if whatsapp:
        return "whatsapp"
    if telephone:
        return "telephone"
    return None


def _phone(value: str) -> bool:
    if not PHONE_RE.fullmatch(value):
        return False
    digits = re.sub(r"\D", "", value)
    return 8 <= len(digits) <= 16


def _parse_filter(value: str) -> Filter | None:
    lower = value.casefold()
    if PAGE_FILTER_RE.fullmatch(lower):
        return Filter((), (), (), tuple(lower.removeprefix("page:").split(",")))
    if BASENAME_FILTER_RE.fullmatch(lower):
        return Filter((), (), tuple(lower.removeprefix("basename:").split(",")))
    if CATEGORY_FILTER_RE.fullmatch(lower):
        clauses = []
        for clause in lower.split(";"):
            categories, cities = clause.split(":")
            clauses.append((tuple(categories.split(",")), tuple(cities.split(","))))
        return Filter(tuple(clauses))
    if SIMPLE_FILTER_RE.fullmatch(lower) and value == lower:
        return Filter((), tuple(lower.split(",")))
    return None


def parse_clients(path: Path) -> list[Client]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise ClientsError(".clients is missing") from None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ClientsError(".clients is not strict UTF-8") from None

    clients = []
    for row, source in enumerate(text.splitlines(), 1):
        if not source.strip():
            continue
        if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in source):
            raise _error(row, "unsafe control character")
        values = [part.strip() for part in source.split("|")]
        if any(not value for value in values):
            raise _error(row, "empty field")
        roles: dict[str, str] = {}
        derive_routes = False
        remaining = []
        for value in values:
            if value.casefold() == "derive-routes":
                if derive_routes:
                    raise _error(row, "duplicate derive-routes option")
                derive_routes = True
                continue
            route = _route_role(value)
            if route == "ambiguous":
                raise _error(row, "ambiguous route")
            if route:
                if route in roles:
                    raise _error(row, f"duplicate {route} route")
                roles[route] = value
            elif _phone(value):
                if "phone" in roles:
                    raise _error(row, "duplicate phone")
                roles["phone"] = value
            elif ADDRESS_RE.match(value):
                if "address" in roles:
                    raise _error(row, "duplicate address")
                roles["address"] = value
            else:
                remaining.append(value)

        filter_value = None
        names = []
        for value in remaining:
            parsed = _parse_filter(value)
            if parsed is not None:
                if filter_value is not None:
                    raise _error(row, "duplicate filter")
                filter_value = parsed
            elif any(mark in value for mark in (":", ",", ";")):
                raise _error(row, "malformed filter")
            else:
                names.append(value)
        if len(names) != 1:
            raise _error(row, "missing name" if not names else "extra unclassified field")
        if derive_routes:
            if roles:
                raise _error(row, "derive-routes cannot include contact values")
        else:
            for required in ("phone", "whatsapp", "telephone"):
                if required not in roles:
                    raise _error(row, f"missing {required}")
        clients.append(
            Client(
                row,
                names[0],
                roles.get("phone"),
                roles.get("whatsapp"),
                roles.get("telephone"),
                filter_value,
                roles.get("address"),
                derive_routes,
            )
        )
    return clients


def _filter_path(path: str) -> str:
    """Normalize the complete relative HTML path used by every filter."""
    return str(path).replace("\\", "/").casefold()


def _terms_match(terms: tuple[str, ...], path: str) -> bool:
    path = _filter_path(path)
    positives = tuple(term for term in terms if not term.startswith("-"))
    negatives = tuple(term[1:] for term in terms if term.startswith("-"))
    return (not positives or any(term in path for term in positives)) and not any(
        term in path for term in negatives
    )


def _filter_matches(rule: Filter, path: str) -> bool:
    path = _filter_path(path)
    if rule.page:
        filename = path.rsplit("/", 1)[-1]
        candidates = [filename]
        if filename == "index.html" and "/" in path:
            candidates.extend(path.rsplit("/", 1)[0].split("/"))
        negatives = tuple(term[1:] for term in rule.page if term.startswith("-"))
        if any(term in candidate for term in negatives for candidate in candidates):
            return False
        positives = tuple(term for term in rule.page if not term.startswith("-"))
        return not positives or any(
            term in candidate for term in positives for candidate in candidates
        )
    if rule.basename:
        return _terms_match(rule.basename, path.rsplit("/", 1)[-1])
    if rule.simple:
        return _terms_match(rule.simple, path)
    for categories, cities in rule.clauses:
        negative = tuple(
            term[1:]
            for term in categories + cities
            if term.startswith("-")
        )
        if any(term in path for term in negative):
            continue
        positive_categories = tuple(term for term in categories if not term.startswith("-"))
        positive_cities = tuple(term for term in cities if not term.startswith("-"))
        if not positive_categories or not positive_cities:
            continue
        if any(
            category in path and city in path[path.index(category) + len(category) :]
            for category in positive_categories
            for city in positive_cities
        ):
            return True
    return False


def _html_paths(root: Path) -> list[Path]:
    paths = []
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names if name != ".git")
        base = Path(directory)
        for name in sorted(files):
            path = base / name
            if path.suffix.casefold() != ".html":
                continue
            if path.is_symlink():
                raise ClientsError("HTML symlink is not supported")
            paths.append(path)
    return paths


def _one(values: list[str], role: str, required: bool = True) -> str | None:
    unique = tuple(dict.fromkeys(values))
    if len(unique) > 1:
        raise ClientsError(f"matched HTML has ambiguous {role}")
    if not unique:
        if required:
            raise ClientsError(f"matched HTML is missing {role}")
        return None
    return unique[0]


def _derive_route(display: str, whatsapp: bool) -> str:
    phone = display.rsplit("(", 1)[0].strip()
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    if not digits.startswith("62") or not 8 <= len(digits) <= 16:
        raise ClientsError("matched HTML displayed phone is not an Indonesian international number")
    return f"https://wa.me/{digits}" if whatsapp else f"tel:+{digits}"


def _derive_routes_from_display(text: str) -> tuple[bool, str]:
    result = text
    has_whatsapp = False
    has_telephone = False
    for anchor in reversed(list(ANCHOR_RE.finditer(text))):
        hrefs = list(HREF_RE.finditer(anchor.group(0)))
        if len(hrefs) != 1:
            continue
        href = hrefs[0]
        try:
            scheme, host = _valid_url(href.group(2))
        except ValueError:
            continue
        whatsapp = host in {"what.sapp.my.id", "wa.me"}
        telephone = host == "con.tact.my.id" or scheme == "tel"
        if not whatsapp and not telephone:
            continue
        if whatsapp == telephone:
            raise ClientsError("matched HTML has ambiguous contact route")
        displays = DISPLAY_RE.findall(re.sub(r"<[^>]*>", "", anchor.group("body")))
        if len(displays) != 1:
            raise ClientsError("derive-routes contact link must contain one displayed phone/name")
        route = _derive_route(displays[0], whatsapp)
        replacement = anchor.group(0)[: href.start(2)] + route + anchor.group(0)[href.end(2) :]
        result = result[: anchor.start()] + replacement + result[anchor.end() :]
        has_whatsapp |= whatsapp
        has_telephone |= telephone
    if not has_whatsapp or not has_telephone:
        raise ClientsError("derive-routes requires WhatsApp and telephone contact links")
    return True, result


def _transform(text: str, client: Client) -> tuple[bool, str]:
    if client.derive_routes:
        return _derive_routes_from_display(text)
    blocks = []
    for match in DIV_RE.finditer(text):
        classes = set(match.group("class").casefold().split())
        markers = classes & MARKERS
        if markers:
            blocks.append((markers, match.group("body"), match))
    if not blocks:
        nav_matches = []
        for nav in NAV_RE.finditer(text):
            class_match = CLASS_ATTR_RE.search(nav.group("attrs"))
            classes = set(class_match.group(2).casefold().split()) if class_match else set()
            if "menu-info-kontak-container" in classes:
                nav_matches.append(nav)
        if len(nav_matches) > 1:
            raise ClientsError("matched HTML has multiple contact nav containers")
        if not nav_matches:
            return False, text
        if client.address is not None:
            raise ClientsError("fallback contact cannot include address")

        nav = nav_matches[0]
        recognized: list[tuple[re.Match[str], str]] = []
        for item in LI_RE.finditer(nav.group("body")):
            anchors = list(ANCHOR_RE.finditer(item.group("body")))
            anchor_openings = re.findall(r"<a\b", item.group("body"), re.IGNORECASE)
            visible = re.sub(r"<[^>]*>", "", item.group("body"))
            displays = DISPLAY_RE.findall(visible)
            if not displays:
                continue
            if len(anchor_openings) != 1 or len(anchors) != 1 or len(displays) != 1:
                raise ClientsError("fallback contact item must contain one anchor and one displayed phone/name")
            anchor = anchors[0]
            hrefs = HREF_RE.findall(anchor.group("attrs"))
            if len(hrefs) != 1:
                raise ClientsError("fallback contact item has ambiguous anchor destination")
            recognized.append((item, displays[0]))
        if not recognized:
            return False, text

        body = nav.group("body")
        first_item, display = recognized[0]
        first_anchor = next(ANCHOR_RE.finditer(first_item.group("body")))
        anchor_text = first_anchor.group(0)
        href_match = HREF_RE.search(first_anchor.group("attrs"))
        assert href_match is not None
        anchor_text = anchor_text.replace(
            href_match.group(2), client.whatsapp, 1
        ).replace(display, f"{client.phone} ({client.name})", 1)
        first_body = first_item.group("body").replace(first_anchor.group(0), anchor_text, 1)
        body = body.replace(first_item.group(0), first_item.group(0).replace(first_item.group("body"), first_body, 1), 1)
        for item, _ in recognized[1:]:
            body = body.replace(item.group(0), "", 1)
        result = text[: nav.start()] + nav.group(0).replace(nav.group("body"), body, 1) + text[nav.end() :]
        return True, result

    empty_image_blocks = all(
        not HREF_RE.search(body)
        and not DISPLAY_RE.search(re.sub(r"<[^>]*>", "", body))
        and len(re.findall(r"<img\b", body, re.IGNORECASE)) == 1
        for _, body, _ in blocks
    )
    if empty_image_blocks:
        has_whatsapp = any(markers & {"whatsapp-floating", "sms-floating"} for markers, _, _ in blocks)
        has_telephone = any("tlp-floating" in markers for markers, _, _ in blocks)
        if not has_whatsapp or not has_telephone:
            raise ClientsError("matched HTML has incomplete empty-image contact blocks")
        result = text
        for markers, body, match in reversed(blocks):
            whatsapp_marker = bool(markers & {"whatsapp-floating", "sms-floating"})
            telephone_marker = "tlp-floating" in markers
            if whatsapp_marker == telephone_marker:
                raise ClientsError("matched HTML has ambiguous empty-image contact block")
            route = client.whatsapp if whatsapp_marker else client.telephone
            inner = f'<a href="{route}">{body}<span>{client.phone} ({client.name})</span></a>'
            replacement = match.group(0).replace(body, inner, 1)
            result = result[: match.start()] + replacement + result[match.end() :]
        if client.address is not None:
            old_address = _one(ADDRESS_RE.findall(result), "address")
            result = result.replace(old_address, client.address, 1)
        return True, result

    displays: list[str] = []
    whatsapp: list[str] = []
    telephone: list[str] = []
    whatsapp_duplicates_safe = True
    telephone_duplicates_safe = True
    for markers, body, _ in blocks:
        block_displays = [
            display
            for span in SPAN_RE.findall(body)
            for display in DISPLAY_RE.findall(span)
        ]
        if not block_displays:
            block_displays = DISPLAY_RE.findall(re.sub(r"<[^>]*>", "", body))
        displays.extend(block_displays)
        hrefs = [href for _, href in HREF_RE.findall(body)]
        if markers & {"whatsapp-floating", "sms-floating"}:
            whatsapp.extend(hrefs)
            whatsapp_duplicates_safe &= len(hrefs) == 1 and bool(block_displays)
        if "tlp-floating" in markers:
            telephone.extend(hrefs)
            telephone_duplicates_safe &= len(hrefs) == 1 and bool(block_displays)

    old_displays = tuple(dict.fromkeys(displays))
    if not old_displays:
        raise ClientsError("matched HTML is missing displayed phone/name")
    old_whatsapp = tuple(dict.fromkeys(whatsapp))
    old_telephone = tuple(dict.fromkeys(telephone))
    if not old_whatsapp:
        raise ClientsError("matched HTML is missing WhatsApp route")
    if not old_telephone:
        raise ClientsError("matched HTML is missing telephone route")
    if len(old_whatsapp) > 1 and not whatsapp_duplicates_safe:
        raise ClientsError("matched HTML has ambiguous WhatsApp route")
    if len(old_telephone) > 1 and not telephone_duplicates_safe:
        raise ClientsError("matched HTML has ambiguous telephone route")
    replacements = [
        *((old, f"{client.phone} ({client.name})") for old in old_displays),
        *((old, client.whatsapp) for old in old_whatsapp),
        *((old, client.telephone) for old in old_telephone),
    ]
    if client.address is not None:
        old_address = _one(ADDRESS_RE.findall(text), "address")
        replacements.append((old_address, client.address))

    result = text
    for old, new in replacements:
        if old != new:
            result = result.replace(old, new)
    return True, result


def _encode_like(raw: bytes, text: str) -> bytes:
    bom = raw.startswith(b"\xef\xbb\xbf")
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
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


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        raise ClientsError("path escaped repository root") from None


def _changed_clients(
    root: Path, current: list[Client], previous: list[Client]
) -> set[Client]:
    previous_by_contact: dict[Client, list[Client]] = {}
    for client in previous:
        previous_by_contact.setdefault(
            replace(client, row=0, filter=None), []
        ).append(client)
    html_paths = [
        _relative(path.resolve(), root.resolve()) for path in _html_paths(root.resolve())
    ]
    changed: set[Client] = set()
    for client in current:
        prior = previous_by_contact.get(replace(client, row=0, filter=None), [])
        if not prior:
            changed.add(client)
            continue
        if replace(client, row=0) in {replace(item, row=0) for item in prior}:
            continue
        if any(
            (client.filter is None or _filter_matches(client.filter, path))
            and not any(
                item.filter is None or _filter_matches(item.filter, path)
                for item in prior
            )
            for path in html_paths
        ):
            changed.add(client)
    return changed


def update(
    root: Path,
    clients_path: Path,
    dry_run: bool,
    only_clients: set[Client] | None = None,
) -> dict[str, object]:
    root = root.resolve()
    clients = parse_clients(clients_path)
    if only_clients is not None:
        clients = [client for client in clients if client in only_clients]
    unfiltered = [client for client in clients if client.filter is None]
    if len(unfiltered) > 1:
        raise ClientsError("multiple unfiltered clients are ambiguous")

    plans: list[tuple[Path, bytes, int]] = []
    scanned = matched = 0
    for path in _html_paths(root):
        scanned += 1
        relative = _relative(path.resolve(), root)
        selected = [
            client
            for client in clients
            if client.filter is not None and _filter_matches(client.filter, relative)
        ]
        if len(selected) > 1:
            raise ClientsError("HTML path matches multiple client filters")
        client = selected[0] if selected else (unfiltered[0] if unfiltered else None)
        if client is None:
            continue
        raw = path.read_bytes()
        try:
            text = raw[3:].decode("utf-8") if raw.startswith(b"\xef\xbb\xbf") else raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ClientsError("matched HTML is not strict UTF-8") from None
        recognized, transformed = _transform(text, client)
        if not recognized:
            continue
        matched += 1
        output = _encode_like(raw, transformed)
        if output != raw:
            plans.append((path, output, stat.S_IMODE(path.stat().st_mode)))

    if not dry_run:
        for path, output, mode in plans:
            _atomic_write(path, output, mode)
    changed_paths = sorted(_relative(path, root) for path, _, _ in plans)
    return {
        "mode": "dry-run" if dry_run else "update",
        "client_count": len(clients),
        "scanned_count": scanned,
        "matched_count": matched,
        "changed_count": len(changed_paths),
        "changed_paths": changed_paths,
    }


def _read_paths(path: Path) -> list[str]:
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise ClientsError("paths file is unreadable strict UTF-8") from None
    values = [value for value in text.split("\0") if value]
    if values != sorted(set(values)):
        raise ClientsError("paths file is not sorted and unique")
    for value in values:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in value:
            raise ClientsError("paths file contains unsafe path")
    return values


def verify_git(root: Path, paths_file: Path) -> None:
    expected = set(_read_paths(paths_file))
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode:
        raise ClientsError("git status failed")
    entries = result.stdout.decode("utf-8", "surrogateescape").split("\0")
    observed: set[str] = set()
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4:
            raise ClientsError("git status returned malformed data")
        status_code, path = entry[:2], entry[3:]
        observed.add(path.replace("\\", "/"))
        if "R" in status_code or "C" in status_code:
            index += 1
    if observed != expected:
        raise ClientsError("git changes are outside planned paths")


def _write_outputs(summary: dict[str, object], summary_path: Path, paths_path: Path) -> None:
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    paths = summary["changed_paths"]
    paths_path.write_bytes(("".join(f"{path}\0" for path in paths)).encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--clients", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--paths-file", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--previous-clients", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-git", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = args.repo_root.resolve()
        if args.verify_git:
            verify_git(root, args.paths_file)
            return 0
        if args.clients is None or args.summary is None:
            parser.error("--clients and --summary are required for update mode")
        clients = args.clients if args.clients.is_absolute() else root / args.clients
        only_clients = None
        if args.previous_clients is not None:
            current_clients = parse_clients(clients)
            previous_clients = parse_clients(args.previous_clients)
            only_clients = _changed_clients(root, current_clients, previous_clients)
        summary = update(root, clients, args.dry_run, only_clients)
        _write_outputs(summary, args.summary, args.paths_file)
        if args.github_output is not None:
            with args.github_output.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(f"changed={'true' if summary['changed_count'] else 'false'}\n")
        return 0
    except ClientsError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
