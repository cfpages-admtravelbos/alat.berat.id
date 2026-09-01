from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


sys.dont_write_bytecode = True
MODULE_PATH = Path(__file__).resolve().with_name("adsense_normalizer.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).resolve().parents[1] / "canonical" / "scripts" / "adsense_normalizer.py"
SPEC = importlib.util.spec_from_file_location("adsense_normalizer", MODULE_PATH)
assert SPEC and SPEC.loader
NORMALIZER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = NORMALIZER
SPEC.loader.exec_module(NORMALIZER)


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


class AdSenseNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        git(self.root, "init")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@example.invalid")
        self.controls: list[Path] = []

    def tearDown(self) -> None:
        for path in self.controls:
            if path.exists():
                path.unlink()
        self.temporary.cleanup()

    def write(self, relative: str, data: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def commit(self, message: str = "fixture") -> None:
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", message)

    def args(self, suffix: str = "one", publisher_id: str = "3534718780470570") -> Namespace:
        paths = self.root.parent / f"{self.root.name}-{suffix}-paths.nul"
        summary = self.root.parent / f"{self.root.name}-{suffix}-summary.json"
        output = self.root.parent / f"{self.root.name}-{suffix}-output.txt"
        self.controls.extend((paths, summary, output))
        return Namespace(
            root=str(self.root),
            publisher_id=publisher_id,
            paths_file=str(paths),
            summary_file=str(summary),
            github_output=str(output),
        )

    def test_first_insertion_ads_txt_unicode_and_idempotence(self) -> None:
        self.write("index.html", b"<html>\n<head>\n</head>\n<body></body>\n</html>\n")
        self.write("nested/ruang kaca.HTML", "<html><head></head></html>".encode("utf-8"))
        self.commit()
        first = self.args("first")
        self.assertEqual(NORMALIZER.apply_normalization(first), 0)
        canonical = NORMALIZER.canonical_script("3534718780470570")
        self.assertEqual((self.root / "index.html").read_text(encoding="utf-8").count(canonical), 1)
        self.assertEqual((self.root / "nested/ruang kaca.HTML").read_text(encoding="utf-8").count(canonical), 1)
        self.assertEqual(
            (self.root / "ads.txt").read_bytes(),
            b"google.com, pub-3534718780470570, DIRECT, f08c47fec0942fa0\n",
        )
        self.assertEqual(
            Path(first.paths_file).read_bytes(),
            b"ads.txt\0index.html\0nested/ruang kaca.HTML\0",
        )
        git(self.root, "add", "--all")
        git(self.root, "commit", "-m", "normalized")
        second = self.args("second")
        self.assertEqual(NORMALIZER.apply_normalization(second), 0)
        self.assertEqual(Path(second.paths_file).read_bytes(), b"")
        self.assertEqual(git(self.root, "status", "--porcelain=v1"), b"")

    def test_replaces_existing_and_removes_duplicate_targets(self) -> None:
        old = (
            '<script src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-0000000000000000"></script>'
        )
        html = f"<html><head>{old}\n{old}</head><body></body></html>"
        self.write("index.html", html.encode("utf-8"))
        self.commit()
        NORMALIZER.apply_normalization(self.args())
        result = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertEqual(result.count("pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"), 1)
        self.assertIn("ca-pub-3534718780470570", result)

    def test_preserves_bom_crlf_and_final_newline_state(self) -> None:
        html = b"\xef\xbb\xbf<html>\r\n<head>\r\n</head>\r\n</html>\r\n"
        self.write("index.html", html)
        self.commit()
        NORMALIZER.apply_normalization(self.args())
        result = (self.root / "index.html").read_bytes()
        self.assertTrue(result.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", result)
        self.assertNotIn(b"\n", result.replace(b"\r\n", b""))
        self.assertTrue(result.endswith(b"\r\n"))

    def test_preserves_absent_final_newline(self) -> None:
        self.write("index.html", b"<html><head></head></html>")
        self.commit()
        NORMALIZER.apply_normalization(self.args())
        self.assertFalse((self.root / "index.html").read_bytes().endswith(b"\n"))

    def test_mixed_newlines_and_invalid_utf8_fail_before_any_write(self) -> None:
        for payload in (b"<html>\r\n<head>\n</head></html>", b"<html><head>\xff</head></html>"):
            with self.subTest(payload=payload):
                self.write("index.html", payload)
                self.commit("bad")
                with self.assertRaises(SystemExit):
                    NORMALIZER.apply_normalization(self.args(str(len(payload))))
                self.assertEqual((self.root / "index.html").read_bytes(), payload)
                self.assertFalse((self.root / "ads.txt").exists())

    def test_missing_and_multiple_head_anchors_fail(self) -> None:
        for index, payload in enumerate((b"<html><body></body></html>", b"<head></head><head></head>")):
            with self.subTest(payload=payload):
                self.write("index.html", payload)
                self.commit(f"bad-{index}")
                with self.assertRaises(SystemExit):
                    NORMALIZER.apply_normalization(self.args(f"head-{index}"))
                self.assertFalse((self.root / "ads.txt").exists())

    def test_malformed_target_and_inline_target_body_fail(self) -> None:
        values = (
            b'<html><head><script src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"></head></html>',
            b'<html><head><script src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js">alert(1)</script></head></html>',
        )
        for index, payload in enumerate(values):
            with self.subTest(payload=payload):
                self.write("index.html", payload)
                self.commit(f"bad-{index}")
                with self.assertRaises(SystemExit):
                    NORMALIZER.apply_normalization(self.args(f"script-{index}"))
                self.assertFalse((self.root / "ads.txt").exists())

    def test_invalid_publisher_fails_before_mutation(self) -> None:
        self.write("index.html", b"<html><head></head></html>")
        self.commit()
        with self.assertRaises(SystemExit):
            NORMALIZER.apply_normalization(self.args(publisher_id="ca-pub-3534718780470570"))
        self.assertFalse((self.root / "ads.txt").exists())
        self.assertEqual(git(self.root, "status", "--porcelain=v1"), b"")

    def test_unsafe_and_case_colliding_paths_fail(self) -> None:
        cases = (
            b"bad\x01.html\0",
            b"A.html\0a.HTML\0",
        )
        for raw in cases:
            with self.subTest(raw=raw), mock.patch.object(NORMALIZER, "git_bytes", return_value=raw):
                with self.assertRaises(SystemExit):
                    NORMALIZER.tracked_html_paths(self.root)

    def test_symlinked_html_is_rejected(self) -> None:
        target = self.write("index.html", b"<html><head></head></html>")
        self.commit()
        with mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda path: path == target):
            with self.assertRaises(SystemExit):
                NORMALIZER.apply_normalization(self.args())

    def test_verify_git_accepts_exact_unstaged_and_staged_paths(self) -> None:
        self.write("index.html", b"<html><head></head></html>")
        self.commit()
        args = self.args()
        NORMALIZER.apply_normalization(args)
        verify = Namespace(root=str(self.root), paths_file=args.paths_file, state="unstaged")
        self.assertEqual(NORMALIZER.verify_git(verify), 0)
        git(self.root, "add", "--pathspec-from-file=" + args.paths_file, "--pathspec-file-nul")
        verify.state = "staged"
        self.assertEqual(NORMALIZER.verify_git(verify), 0)

    def test_verify_git_rejects_unexpected_dirt_and_unsafe_paths_file(self) -> None:
        self.write("index.html", b"<html><head></head></html>")
        self.write("other.txt", b"clean")
        self.commit()
        args = self.args()
        NORMALIZER.apply_normalization(args)
        (self.root / "other.txt").write_bytes(b"dirty")
        with self.assertRaises(SystemExit):
            NORMALIZER.verify_git(Namespace(root=str(self.root), paths_file=args.paths_file, state="unstaged"))
        bad = self.root.parent / f"{self.root.name}-bad-paths.nul"
        bad.write_bytes(b"../outside.html\0")
        self.controls.append(bad)
        with self.assertRaises(SystemExit):
            NORMALIZER.read_paths_file(bad)

    def test_summary_is_strict_json_and_matches_changed_paths(self) -> None:
        self.write("index.html", b"<html><head></head></html>")
        self.commit()
        args = self.args()
        NORMALIZER.apply_normalization(args)
        summary = json.loads(Path(args.summary_file).read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], "adsense-normalization-summary-v1")
        self.assertEqual(summary["html_files"], 1)
        self.assertEqual(summary["changed_files"], ["ads.txt", "index.html"])


if __name__ == "__main__":
    unittest.main()
