#!/usr/bin/env python3
"""Deterministic, idempotent repository text and contact-route transformer."""

from __future__ import annotations

import argparse
import codecs
import fnmatch
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any


class TransformError(RuntimeError):
    pass


MESSAGE_CLASSES = {"whatsapp-floating", "wa-floating", "message-floating", "chat-floating"}
PHONE_CLASSES = {"tlp-floating", "tel-floating", "telephone-floating", "phone-floating", "call-floating"}
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
PHONE_TEXT_RE = re.compile(r"(?<!\d)(?:\+?62|0)(?:[\s().-]*\d){8,14}(?!\d)")
ATTR_RE_TEMPLATE = r"(?is)(?P<prefix>\s{name}\s*=\s*)(?:(?P<quote>[\"'])(?P<quoted>.*?)\2|(?P<bare>[^\s>]+))"


def _json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TransformError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise TransformError(f"{label} must be a JSON object")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise TransformError(f"{label} must be a nonempty-string JSON array")
    return value


def _matches(rel: str, pattern: str) -> bool:
    path = PurePosixPath(rel)
    return path.match(pattern) or fnmatch.fnmatchcase(rel, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(rel, pattern[3:])
    )


def selected_files(root: Path, includes: list[str], excludes: list[str]) -> list[Path]:
    if not includes:
        raise TransformError("at least one include pattern is required")
    selected: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            rel = path.relative_to(root).as_posix()
            if any(_matches(rel, pattern) for pattern in includes):
                raise TransformError(f"selected symlink is prohibited: {rel}")
            continue
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        if any(_matches(rel, pattern) for pattern in excludes):
            continue
        if any(_matches(rel, pattern) for pattern in includes):
            selected.append(path)
    return sorted(selected, key=lambda item: item.relative_to(root).as_posix())


def read_utf8(path: Path) -> tuple[str, bool, bytes]:
    raw = path.read_bytes()
    bom = raw.startswith(codecs.BOM_UTF8)
    payload = raw[len(codecs.BOM_UTF8):] if bom else raw
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TransformError(f"selected file is not strict UTF-8: {path}") from exc
    return text, bom, raw


def encode_utf8(text: str, bom: bool) -> bytes:
    payload = text.encode("utf-8", errors="strict")
    return codecs.BOM_UTF8 + payload if bom else payload


def write_atomic(path: Path, payload: bytes) -> None:
    current_mode = stat.S_IMODE(path.stat().st_mode)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, current_mode)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _attribute_pattern(name: str) -> re.Pattern[str]:
    return re.compile(ATTR_RE_TEMPLATE.format(name=re.escape(name)))


def _attribute_value(raw_tag: str, name: str) -> str | None:
    matches = list(_attribute_pattern(name).finditer(raw_tag))
    if len(matches) > 1:
        raise TransformError(f"start tag has duplicate {name} attributes")
    if not matches:
        return None
    match = matches[0]
    return match.group("quoted") if match.group("quote") else match.group("bare")


def _set_attribute(raw_tag: str, name: str, value: str) -> str:
    escaped = html.escape(value, quote=True)
    pattern = _attribute_pattern(name)
    matches = list(pattern.finditer(raw_tag))
    if len(matches) > 1:
        raise TransformError(f"start tag has duplicate {name} attributes")
    if matches:
        match = matches[0]
        quote = match.group("quote") or '"'
        replacement = f"{match.group('prefix')}{quote}{escaped}{quote}"
        return raw_tag[:match.start()] + replacement + raw_tag[match.end():]
    closing = "/>" if raw_tag.rstrip().endswith("/>") else ">"
    index = raw_tag.rfind(closing)
    if index < 0:
        raise TransformError("malformed start tag")
    return raw_tag[:index] + f' {name}="{escaped}"' + raw_tag[index:]


def _remove_attribute(raw_tag: str, name: str) -> str:
    pattern = _attribute_pattern(name)
    matches = list(pattern.finditer(raw_tag))
    if len(matches) > 1:
        raise TransformError(f"start tag has duplicate {name} attributes")
    if not matches:
        return raw_tag
    match = matches[0]
    return raw_tag[:match.start()] + raw_tag[match.end():]


class ContactParser(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.line_offsets = [0]
        for match in re.finditer(r"\n", text):
            self.line_offsets.append(match.end())
        self.stack: list[dict[str, Any]] = []
        self.containers: list[dict[str, Any]] = []
        self.anchors: list[dict[str, Any]] = []

    def absolute(self) -> int:
        line, column = self.getpos()
        return self.line_offsets[line - 1] + column

    def _intent(self, attrs: list[tuple[str, str | None]]) -> str | None:
        classes: set[str] = set()
        for key, value in attrs:
            if key.lower() == "class" and value:
                classes.update(part.lower() for part in value.split())
        message = bool(classes & MESSAGE_CLASSES)
        phone = bool(classes & PHONE_CLASSES)
        if message and phone:
            raise TransformError("one container declares both message and telephone intent")
        return "whatsapp" if message else "telephone" if phone else None

    def _active_container_ids(self) -> list[int]:
        return [frame["container_id"] for frame in self.stack if frame.get("container_id") is not None]

    def _active_anchor(self) -> dict[str, Any] | None:
        for frame in reversed(self.stack):
            if frame.get("anchor_id") is not None:
                return self.anchors[frame["anchor_id"]]
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        start = self.absolute()
        raw = self.get_starttag_text()
        end = start + len(raw)
        intent = self._intent(attrs)
        container_id = None
        if intent:
            container_id = len(self.containers)
            self.containers.append({"intent": intent, "anchors": []})
        anchor_id = None
        if lower == "a":
            containers = self._active_container_ids()
            if container_id is not None:
                containers.append(container_id)
            if len(containers) > 1:
                raise TransformError("an anchor is nested inside multiple contact-intent containers")
            if containers:
                anchor_id = len(self.anchors)
                self.anchors.append({
                    "intent": self.containers[containers[0]]["intent"],
                    "container_id": containers[0],
                    "tag_start": start,
                    "tag_end": end,
                    "raw_tag": raw,
                    "text_spans": [],
                    "icon_signals": set(),
                })
                self.containers[containers[0]]["anchors"].append(anchor_id)
        active_anchor = self._active_anchor()
        if lower == "img" and active_anchor is not None:
            values = {key.lower(): (value or "").lower() for key, value in attrs}
            strong = " ".join([values.get("src", ""), values.get("class", "")])
            fallback = values.get("alt", "")
            source = strong if re.search(r"whatsapp|message|chat|phone|telephone|call|telp", strong) else fallback
            if re.search(r"whatsapp|message|chat", source):
                active_anchor["icon_signals"].add("whatsapp")
            if re.search(r"phone|telephone|call|telp", source):
                active_anchor["icon_signals"].add("telephone")
        if lower not in VOID_ELEMENTS:
            self.stack.append({
                "tag": lower,
                "container_id": container_id,
                "anchor_id": anchor_id,
            })

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1]["tag"] == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == lower:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        anchor = self._active_anchor()
        if anchor is None:
            return
        start = self.absolute()
        for match in PHONE_TEXT_RE.finditer(data):
            anchor["text_spans"].append((start + match.start(), start + match.end()))


def analyze_contacts(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parser = ContactParser(text)
    try:
        parser.feed(text)
        parser.close()
    except TransformError:
        raise
    except Exception as exc:
        raise TransformError(f"HTML parsing failed: {exc}") from exc
    for container in parser.containers:
        if len(container["anchors"]) != 1:
            raise TransformError(
                f"{container['intent']} contact container must contain exactly one anchor; "
                f"found {len(container['anchors'])}"
            )
    for anchor in parser.anchors:
        signals = anchor["icon_signals"]
        if len(signals) > 1:
            raise TransformError("contact anchor has conflicting icon intent signals")
        if signals and anchor["intent"] not in signals:
            raise TransformError(
                f"{anchor['intent']} contact container conflicts with its icon signal"
            )
    return parser.containers, parser.anchors


def _apply_edits(text: str, edits: list[tuple[int, int, str]]) -> str:
    ordered = sorted(edits, key=lambda item: (item[0], item[1]))
    for previous, current in zip(ordered, ordered[1:]):
        if previous[1] > current[0]:
            raise TransformError("planned source edits overlap")
    result = text
    for start, end, replacement in reversed(ordered):
        result = result[:start] + replacement + result[end:]
    return result


def transform_contact_text(text: str, spec: dict[str, Any]) -> tuple[str, dict[str, int]]:
    whatsapp_url = spec.get("whatsapp_url")
    telephone_url = spec.get("telephone_url")
    visible_number = spec.get("visible_number")
    if not all(isinstance(value, str) and value for value in (whatsapp_url, telephone_url, visible_number)):
        raise TransformError("contact-routes requires nonempty whatsapp_url, telephone_url, and visible_number")
    if not whatsapp_url.startswith("https://"):
        raise TransformError("whatsapp_url must use https")
    if not telephone_url.startswith("tel:"):
        raise TransformError("telephone_url must use tel:")
    message_new_tab = spec.get("message_new_tab", True)
    require_visible = spec.get("require_visible_number_per_anchor", False)
    if not isinstance(message_new_tab, bool) or not isinstance(require_visible, bool):
        raise TransformError("contact-route boolean options must be JSON booleans")

    containers, anchors = analyze_contacts(text)
    edits: list[tuple[int, int, str]] = []
    counts = {"whatsapp_anchors": 0, "telephone_anchors": 0, "visible_numbers": 0}
    for anchor in anchors:
        intent = anchor["intent"]
        counts[f"{intent}_anchors"] += 1
        raw_tag = anchor["raw_tag"]
        desired = whatsapp_url if intent == "whatsapp" else telephone_url
        updated_tag = _set_attribute(raw_tag, "href", desired)
        if intent == "whatsapp" and message_new_tab:
            updated_tag = _set_attribute(updated_tag, "target", "_blank")
            current_rel = _attribute_value(updated_tag, "rel") or ""
            rel_tokens = [token for token in current_rel.split() if token]
            for token in ("noopener", "noreferrer"):
                if token not in rel_tokens:
                    rel_tokens.append(token)
            updated_tag = _set_attribute(updated_tag, "rel", " ".join(rel_tokens))
        elif intent == "telephone":
            updated_tag = _remove_attribute(updated_tag, "target")
            current_rel = _attribute_value(updated_tag, "rel")
            if current_rel is not None:
                remaining = [token for token in current_rel.split() if token not in {"noopener", "noreferrer"}]
                updated_tag = _set_attribute(updated_tag, "rel", " ".join(remaining)) if remaining else _remove_attribute(updated_tag, "rel")
        if updated_tag != raw_tag:
            edits.append((anchor["tag_start"], anchor["tag_end"], updated_tag))
        if require_visible and not anchor["text_spans"]:
            raise TransformError(f"{intent} contact anchor has no visible phone number")
        for start, end in anchor["text_spans"]:
            counts["visible_numbers"] += 1
            if text[start:end] != visible_number:
                edits.append((start, end, visible_number))

    transformed = _apply_edits(text, edits)
    post_containers, post_anchors = analyze_contacts(transformed)
    if len(post_containers) != len(containers) or len(post_anchors) != len(anchors):
        raise TransformError("contact structure changed during attribute replacement")
    for anchor in post_anchors:
        href = _attribute_value(anchor["raw_tag"], "href")
        expected_href = whatsapp_url if anchor["intent"] == "whatsapp" else telephone_url
        if href != expected_href:
            raise TransformError(f"{anchor['intent']} postcondition href mismatch")
        target = _attribute_value(anchor["raw_tag"], "target")
        rel = set((_attribute_value(anchor["raw_tag"], "rel") or "").split())
        if anchor["intent"] == "whatsapp" and message_new_tab:
            if target != "_blank" or not {"noopener", "noreferrer"}.issubset(rel):
                raise TransformError("WhatsApp new-tab postcondition failed")
        if anchor["intent"] == "telephone" and target == "_blank":
            raise TransformError("telephone anchor must not open a blank browser tab")
        if require_visible and len(anchor["text_spans"]) == 0:
            raise TransformError("visible-number postcondition failed")
        for start, end in anchor["text_spans"]:
            if transformed[start:end] != visible_number:
                raise TransformError("visible-number postcondition mismatch")
    return transformed, counts


def _expected_exact(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TransformError(f"{label} must be a nonnegative integer")
    return value


def transform_contact_repository(root: Path, spec: dict[str, Any]) -> tuple[list[tuple[Path, bytes]], dict[str, Any]]:
    includes = _string_list(spec.get("include", ["**/*.html"]), "include")
    excludes = _string_list(
        spec.get("exclude", [".git/**", ".github/**", "node_modules/**"]),
        "exclude",
    )
    expected = spec.get("expected")
    if not isinstance(expected, dict):
        raise TransformError("contact-routes requires an expected object")
    required_expected = {
        key: _expected_exact(expected.get(key), f"expected.{key}")
        for key in ("matched_files", "whatsapp_anchors", "telephone_anchors", "visible_numbers")
    }
    totals = {"matched_files": 0, "whatsapp_anchors": 0, "telephone_anchors": 0, "visible_numbers": 0}
    changes: list[tuple[Path, bytes]] = []
    for path in selected_files(root, includes, excludes):
        text, bom, raw = read_utf8(path)
        transformed, counts = transform_contact_text(text, spec)
        if counts["whatsapp_anchors"] or counts["telephone_anchors"]:
            totals["matched_files"] += 1
        for key in ("whatsapp_anchors", "telephone_anchors", "visible_numbers"):
            totals[key] += counts[key]
        second, _ = transform_contact_text(transformed, spec)
        if second != transformed:
            raise TransformError(f"contact transformation is not idempotent: {path.relative_to(root)}")
        payload = encode_utf8(transformed, bom)
        if payload != raw:
            changes.append((path, payload))
    for key, value in required_expected.items():
        if totals[key] != value:
            raise TransformError(f"{key} mismatch: expected {value}, observed {totals[key]}")
    summary = {"mode": "contact-routes", **totals}
    return changes, summary


def transform_exact_repository(root: Path, spec: dict[str, Any]) -> tuple[list[tuple[Path, bytes]], dict[str, Any]]:
    includes = _string_list(spec.get("include"), "include")
    excludes = _string_list(spec.get("exclude", [".git/**", ".github/**", "node_modules/**"]), "exclude")
    replacements = spec.get("replacements")
    if not isinstance(replacements, list) or not replacements:
        raise TransformError("exact mode requires a nonempty replacements array")
    pairs: list[tuple[str, str, int]] = []
    searches: list[str] = []
    for index, item in enumerate(replacements):
        if not isinstance(item, dict):
            raise TransformError(f"replacements[{index}] must be an object")
        search, replace = item.get("search"), item.get("replace")
        if not isinstance(search, str) or not search or not isinstance(replace, str):
            raise TransformError(f"replacements[{index}] requires nonempty search and string replace")
        expected = _expected_exact(item.get("expected"), f"replacements[{index}].expected")
        pairs.append((search, replace, expected))
        searches.append(search)
    if len(set(searches)) != len(searches):
        raise TransformError("exact search tokens must be unique")
    for first in searches:
        for second in searches:
            if first != second and (first in second or second in first):
                raise TransformError("overlapping exact search tokens are prohibited")
    for search, replace, _ in pairs:
        if search in replace:
            raise TransformError("a replacement may not contain its own search token")

    files: list[tuple[Path, str, bool, bytes]] = []
    totals = [0] * len(pairs)
    for path in selected_files(root, includes, excludes):
        text, bom, raw = read_utf8(path)
        files.append((path, text, bom, raw))
        for index, (search, _, _) in enumerate(pairs):
            totals[index] += text.count(search)
    for index, (_, _, expected) in enumerate(pairs):
        if totals[index] != expected:
            raise TransformError(
                f"replacement {index} count mismatch: expected {expected}, observed {totals[index]}"
            )

    changes: list[tuple[Path, bytes]] = []
    for path, text, bom, raw in files:
        transformed = text
        for search, replace, _ in pairs:
            transformed = transformed.replace(search, replace)
        for search, _, _ in pairs:
            if search in transformed:
                raise TransformError(f"exact replacement postcondition failed: {path.relative_to(root)}")
        payload = encode_utf8(transformed, bom)
        if payload != raw:
            changes.append((path, payload))
    return changes, {
        "mode": "exact",
        "selected_files": len(files),
        "replacement_counts": totals,
    }


def write_paths(path: Path, root: Path, changed: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(
        item.relative_to(root).as_posix().encode("utf-8") + b"\0"
        for item in sorted(changed, key=lambda value: value.relative_to(root).as_posix())
    )
    path.write_bytes(payload)


def read_paths(path: Path) -> list[str]:
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\0"):
        raise TransformError("paths file must be NUL terminated")
    values = raw[:-1].split(b"\0") if raw else []
    try:
        decoded = [value.decode("utf-8", errors="strict") for value in values]
    except UnicodeDecodeError as exc:
        raise TransformError("paths file is not strict UTF-8") from exc
    if len(decoded) != len(set(decoded)) or decoded != sorted(decoded):
        raise TransformError("paths file must be unique and sorted")
    return decoded


def verify_git(root: Path, paths_file: Path, state: str) -> dict[str, Any]:
    expected = read_paths(paths_file)
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    entries = result.stdout.split(b"\0")
    if entries and entries[-1] == b"":
        entries.pop()
    observed: list[str] = []
    expected_status = b" M" if state == "unstaged" else b"M "
    for entry in entries:
        if len(entry) < 4 or entry[2:3] != b" ":
            raise TransformError("unsupported Git porcelain entry")
        status_code = entry[:2]
        if status_code != expected_status:
            raise TransformError(
                f"unexpected Git status {status_code.decode('ascii', errors='replace')!r}"
            )
        try:
            observed.append(entry[3:].decode("utf-8", errors="strict"))
        except UnicodeDecodeError as exc:
            raise TransformError("Git status path is not strict UTF-8") from exc
    if observed != expected:
        raise TransformError(f"Git path boundary mismatch: expected {expected}, observed {observed}")
    return {"state": state, "paths": len(observed)}


def command_transform(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve(strict=True)
    if not (root / ".git").exists():
        raise TransformError("root must be a Git worktree")
    spec = _json_object(args.spec_json, "spec_json")
    if args.mode == "contact-routes":
        changes, summary = transform_contact_repository(root, spec)
    else:
        changes, summary = transform_exact_repository(root, spec)
    for path, payload in changes:
        write_atomic(path, payload)
    changed_paths = [path for path, _ in changes]
    paths_file = Path(args.paths_file)
    write_paths(paths_file, root, changed_paths)
    summary = {**summary, "changed": bool(changes), "changed_files": len(changes)}
    if args.summary_file:
        Path(args.summary_file).write_text(
            json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"changed={'true' if changes else 'false'}\n")
            stream.write(f"changed_files={len(changes)}\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve(strict=True)
    summary = verify_git(root, Path(args.paths_file), args.state)
    print(json.dumps(summary, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    transform = subparsers.add_parser("transform")
    transform.add_argument("--root", required=True)
    transform.add_argument("--mode", choices=("contact-routes", "exact"), required=True)
    transform.add_argument("--spec-json", required=True)
    transform.add_argument("--paths-file", required=True)
    transform.add_argument("--summary-file")
    transform.add_argument("--github-output")
    transform.set_defaults(func=command_transform)
    verify = subparsers.add_parser("verify-git")
    verify.add_argument("--root", required=True)
    verify.add_argument("--paths-file", required=True)
    verify.add_argument("--state", choices=("unstaged", "staged"), required=True)
    verify.set_defaults(func=command_verify)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return args.func(args)
    except TransformError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
