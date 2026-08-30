#!/usr/bin/env python3

from __future__ import annotations

import codecs
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ADJACENT_SCRIPT = Path(__file__).resolve().with_name("repository_transform.py")
SCRIPT = (
    ADJACENT_SCRIPT
    if ADJACENT_SCRIPT.exists()
    else Path(__file__).resolve().parents[1] / "canonical" / "scripts" / "repository_transform.py"
)
SPEC = importlib.util.spec_from_file_location("repository_transform", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def contact_spec(**overrides):
    value = {
        "whatsapp_url": "https://wa.me/628111542354",
        "telephone_url": "tel:+628111542354",
        "visible_number": "081 1154 2354",
        "message_new_tab": True,
        "require_visible_number_per_anchor": True,
    }
    value.update(overrides)
    return value


SAMPLE = (
    '<div class="whatsapp-floating"><a href="https://klik.example/💬-lead">'
    '<img src="/whatsapp-icon.png" alt="whatsapp"><span>0813 7045 7401 (Riky)</span></a></div>\n'
    '<div class="tlp-floating"><a href="https://klik.example/📞-lead">'
    '<img src="/phone-icon.png" alt="whatsapp"><span>0813 7045 7401 (Riky)</span></a></div>\n'
    '<a href="https://wa.me/620000000000">unrelated WhatsApp link</a>\n'
)


class ContactTests(unittest.TestCase):
    def test_contact_routes_are_structural_and_idempotent(self):
        transformed, counts = MODULE.transform_contact_text(SAMPLE, contact_spec())
        self.assertEqual(
            counts,
            {"whatsapp_anchors": 1, "telephone_anchors": 1, "visible_numbers": 2},
        )
        self.assertIn('href="https://wa.me/628111542354"', transformed)
        self.assertIn('target="_blank"', transformed)
        self.assertIn('rel="noopener noreferrer"', transformed)
        self.assertIn('href="tel:+628111542354"', transformed)
        self.assertIn('href="https://wa.me/620000000000"', transformed)
        self.assertEqual(transformed.count("081 1154 2354 (Riky)"), 2)
        second, _ = MODULE.transform_contact_text(transformed, contact_spec())
        self.assertEqual(second, transformed)

    def test_crlf_bom_and_final_newline_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            html_path = root / "index.html"
            original = codecs.BOM_UTF8 + SAMPLE.replace("\n", "\r\n").encode("utf-8")
            html_path.write_bytes(original)
            spec = contact_spec(
                include=["**/*.html"],
                exclude=[".git/**"],
                expected={
                    "matched_files": 1,
                    "whatsapp_anchors": 1,
                    "telephone_anchors": 1,
                    "visible_numbers": 2,
                },
            )
            changes, summary = MODULE.transform_contact_repository(root, spec)
            self.assertEqual(summary["matched_files"], 1)
            self.assertEqual(len(changes), 1)
            payload = changes[0][1]
            self.assertTrue(payload.startswith(codecs.BOM_UTF8))
            self.assertNotIn(b"\n", payload.replace(b"\r\n", b""))
            self.assertTrue(payload.endswith(b"\r\n"))

    def test_ambiguous_container_fails_closed(self):
        poisoned = SAMPLE.replace(
            'class="whatsapp-floating"',
            'class="whatsapp-floating tlp-floating"',
            1,
        )
        with self.assertRaisesRegex(MODULE.TransformError, "both message and telephone"):
            MODULE.transform_contact_text(poisoned, contact_spec())

    def test_multiple_anchors_fail_closed(self):
        poisoned = '<div class="tlp-floating"><a href="tel:1">1</a><a href="tel:2">2</a></div>'
        with self.assertRaisesRegex(MODULE.TransformError, "exactly one anchor"):
            MODULE.transform_contact_text(poisoned, contact_spec(require_visible_number_per_anchor=False))

    def test_icon_conflict_fails_closed(self):
        poisoned = SAMPLE.replace("/phone-icon.png", "/whatsapp-icon.png", 1)
        with self.assertRaisesRegex(MODULE.TransformError, "conflicts with its icon"):
            MODULE.transform_contact_text(poisoned, contact_spec())


class ExactTests(unittest.TestCase):
    def _root(self):
        context = tempfile.TemporaryDirectory()
        root = Path(context.name)
        (root / ".git").mkdir()
        return context, root

    def test_exact_mode_uses_counts_and_preserves_unselected_file(self):
        context, root = self._root()
        with context:
            (root / "a.html").write_text("old old\n", encoding="utf-8", newline="\n")
            (root / "keep.txt").write_text("old\n", encoding="utf-8", newline="\n")
            changes, summary = MODULE.transform_exact_repository(root, {
                "include": ["**/*.html"],
                "exclude": [".git/**"],
                "replacements": [{"search": "old", "replace": "new", "expected": 2}],
            })
            self.assertEqual(summary["replacement_counts"], [2])
            self.assertEqual([path.name for path, _ in changes], ["a.html"])
            self.assertEqual(changes[0][1], b"new new\n")
            self.assertEqual((root / "keep.txt").read_text(encoding="utf-8"), "old\n")

    def test_exact_count_mismatch_fails_before_write(self):
        context, root = self._root()
        with context:
            path = root / "a.html"
            path.write_text("old\n", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.TransformError, "count mismatch"):
                MODULE.transform_exact_repository(root, {
                    "include": ["**/*.html"],
                    "replacements": [{"search": "old", "replace": "new", "expected": 2}],
                })
            self.assertEqual(path.read_text(encoding="utf-8"), "old\n")

    def test_overlapping_tokens_are_rejected(self):
        context, root = self._root()
        with context:
            (root / "a.html").write_text("abc\n", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.TransformError, "overlapping"):
                MODULE.transform_exact_repository(root, {
                    "include": ["**/*.html"],
                    "replacements": [
                        {"search": "ab", "replace": "x", "expected": 1},
                        {"search": "abc", "replace": "y", "expected": 1},
                    ],
                })

    def test_invalid_utf8_is_rejected(self):
        context, root = self._root()
        with context:
            (root / "a.html").write_bytes(b"\xff")
            with self.assertRaisesRegex(MODULE.TransformError, "not strict UTF-8"):
                MODULE.transform_exact_repository(root, {
                    "include": ["**/*.html"],
                    "replacements": [{"search": "x", "replace": "y", "expected": 0}],
                })


if __name__ == "__main__":
    unittest.main(verbosity=2)
