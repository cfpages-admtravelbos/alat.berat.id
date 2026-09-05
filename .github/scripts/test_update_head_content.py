from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INSTALLED_SCRIPT = Path(__file__).with_name("update_head_content.py")
LIBRARY_SCRIPT = Path(__file__).parents[1] / "canonical" / "scripts" / "update_head_content.py"
SCRIPT = INSTALLED_SCRIPT if INSTALLED_SCRIPT.is_file() else LIBRARY_SCRIPT


def run(args, *, check=True):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and p.returncode:
        raise AssertionError(p.stderr.decode("utf-8", "replace"))
    return p


class Repo:
    def __init__(self, root: Path, files: dict[str, bytes]):
        self.root = root
        root.mkdir(parents=True)
        run(["git", "-C", str(root), "init", "-q"])
        run(["git", "-C", str(root), "config", "user.name", "test"])
        run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"])
        for rel, data in files.items():
            p = root.joinpath(*rel.split("/")); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        run(["git", "-C", str(root), "add", "."]); run(["git", "-C", str(root), "commit", "-qm", "fixture"])

    def normalize(self, evidence: Path, name: str, check=True):
        m, s = evidence / (name + ".bin"), evidence / (name + ".json")
        p = run([sys.executable, str(SCRIPT), "normalize", "--root", str(self.root), "--manifest", str(m), "--summary", str(s)], check=check)
        return p, m, s

    def stage(self, m: Path, check=True):
        return run([sys.executable, str(SCRIPT), "stage", "--root", str(self.root), "--manifest", str(m)], check=check)


class HeadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="head-content-")
        self.base = Path(self.tmp.name); self.ev = self.base / "ev"; self.ev.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def repo(self, files):
        return Repo(self.base / f"r{len(list(self.base.glob('r*')))}", files)

    def assert_poison(self, files, needle):
        r = self.repo(files)
        before = {p.relative_to(r.root): p.read_bytes() for p in r.root.rglob("*") if p.is_file() and ".git" not in p.parts}
        p, m, s = r.normalize(self.ev, "bad", check=False)
        self.assertNotEqual(p.returncode, 0); self.assertIn(needle, p.stderr.decode())
        self.assertFalse(m.exists()); self.assertFalse(s.exists())
        after = {p.relative_to(r.root): p.read_bytes() for p in r.root.rglob("*") if p.is_file() and ".git" not in p.parts}
        self.assertEqual(before, after)

    def test_marker_free_insert_and_selector(self):
        r = self.repo({".head": b"<meta data='a&b'>\n<script>x</script>\n", "index.html": b"<head>\n</head>\n", "UPPER.HTML": b"<head></head>"})
        _, m, s = r.normalize(self.ev, "insert")
        self.assertEqual(m.read_bytes(), b"index.html\0")
        out = (r.root / "index.html").read_bytes()
        self.assertEqual(out, b"<head>\n<!-- START of .head content -->\n<meta data='a&b'>\n<script>x</script>\n<!-- END of .head content -->\n</head>\n")
        self.assertEqual(json.loads(s.read_text())["changed"], 1)

    def test_existing_markers_replace_without_closing_tag_and_local_newline(self):
        r = self.repo({".head": b"\xef\xbb\xbf<meta>\r\n<script>q</script>\n", "a.html": b"prefix<!-- START of .head content --><!-- END of .head content -->suffix"})
        _, m, _ = r.normalize(self.ev, "replace")
        self.assertEqual(m.read_bytes(), b"a.html\0")
        self.assertEqual((r.root / "a.html").read_bytes(), b"prefix<!-- START of .head content -->\n<meta>\n<script>q</script>\n<!-- END of .head content -->suffix")

    def test_mixed_newlines_preserve_unrelated_bytes_and_local_style(self):
        original = b"<head>\r\nA\n<!-- START of .head content -->\r\nold\n<!-- END of .head content -->\r\nB\n</head>\r\n"
        r = self.repo({".head": b"x\r\ny\n", "a.html": original}); r.normalize(self.ev, "mixed")
        out = (r.root / "a.html").read_bytes()
        self.assertIn(b"<head>\r\nA\n", out); self.assertIn(b"\r\nx\r\ny\r\n", out); self.assertIn(b"<!-- END of .head content -->\r\nB\n</head>\r\n", out)

    def test_crlf_target_bom_and_final_newline(self):
        r = self.repo({".head": b"x\n", "a.html": b"\xef\xbb\xbf<head>\r\n</head>\r\n", "b.html": b"<head>\r\n</head>"})
        _, m, _ = r.normalize(self.ev, "crlf")
        self.assertEqual(len(m.read_bytes().split(b"\0")) - 1, 2)
        self.assertTrue((r.root / "a.html").read_bytes().startswith(b"\xef\xbb\xbf")); self.assertTrue((r.root / "a.html").read_bytes().endswith(b"\r\n")); self.assertFalse((r.root / "b.html").read_bytes().endswith(b"\r\n"))

    def test_idempotence_and_empty_manifest(self):
        r = self.repo({".head": b"x", "a.html": b"<head></head>"}); r.normalize(self.ev, "one"); run(["git", "-C", str(r.root), "add", "."]); run(["git", "-C", str(r.root), "commit", "-qm", "update"])
        _, m, s = r.normalize(self.ev, "two"); self.assertEqual(m.read_bytes(), b""); self.assertEqual(json.loads(s.read_text())["changed"], 0)

    def test_poison_markers_closing_encoding_and_lone_cr(self):
        self.assert_poison({".head": b"x", "a.html": b"<head><!-- START of .head content --></head>"}, "markers")
        self.assert_poison({".head": b"x", "a.html": b"<head><!-- END of .head content --><!-- START of .head content --></head>"}, "markers")
        self.assert_poison({".head": b"x", "a.html": b"<head>\r</head>"}, "lone CR")
        self.assert_poison({".head": b"x", "a.html": b"<head>\xff</head>"}, "strict UTF-8")
        self.assert_poison({".head": b"x", "a.html": b"<head></head></head>"}, "exactly one")

    def test_marker_free_closing_count_only_marker_free(self):
        r = self.repo({".head": b"x", "a.html": b"<head><!-- START of .head content -->x<!-- END of .head content -->"}); r.normalize(self.ev, "no-close")

    def test_path_and_stage_safety(self):
        r = self.repo({".head": b"x", "a.html": b"<head></head>", "note.txt": b"a"}); _, m, _ = r.normalize(self.ev, "stage")
        (r.root / "note.txt").write_bytes(b"b"); self.assertNotEqual(r.stage(m, check=False).returncode, 0)
        for raw in (b"../a.html\0", b"a.html\0a.html\0", b"a.txt\0"):
            bad = self.ev / (raw.hex() + ".bin"); bad.write_bytes(raw); self.assertNotEqual(r.stage(bad, check=False).returncode, 0)

    def test_headless_ownership_fragment_and_unknown_are_skipped(self):
        files = {
            ".head": b"<meta name='x'>\n",
            "z-unknown.html": b"plain fragment without a head",
            "a-ownership.html": b"<!-- ownership-verification-token -->",
            "m-fragment.html": b"<div>fragment</div>",
        }
        r = self.repo(files)
        before = {p.name: p.read_bytes() for p in r.root.glob("*.html")}
        p, m, s = r.normalize(self.ev, "headless")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(m.read_bytes(), b"")
        summary = json.loads(s.read_text(encoding="utf-8"))
        self.assertEqual(summary, {
            "schema_version": "html-head-content-summary-v2",
            "discovered": 3,
            "changed": 0,
            "unchanged": 0,
            "skipped_headless": 3,
            "skipped_headless_paths": [
                "a-ownership.html", "m-fragment.html", "z-unknown.html"
            ],
        })
        self.assertEqual(before, {p.name: p.read_bytes() for p in r.root.glob("*.html")})

    def test_mixed_eligible_replacement_and_headless_manifest_summary(self):
        r = self.repo({
            ".head": b"<meta data='v'>\n",
            "insert.html": b"<head>\n</head>\n",
            "replace.html": b"<!-- START of .head content -->old<!-- END of .head content -->",
            "skip.html": b"<main>fragment</main>",
            "same.html": b"<!-- START of .head content -->\n<meta data='v'>\n<!-- END of .head content -->",
        })
        _, m, s = r.normalize(self.ev, "mixed-headless")
        summary = json.loads(s.read_text(encoding="utf-8"))
        self.assertEqual(summary["discovered"], 4)
        self.assertEqual(summary["changed"], 2)
        self.assertEqual(summary["unchanged"], 1)
        self.assertEqual(summary["skipped_headless"], 1)
        self.assertEqual(summary["skipped_headless_paths"], ["skip.html"])
        self.assertEqual(m.read_bytes(), b"insert.html\0replace.html\0")
        self.assertNotIn(b"skip.html", m.read_bytes())

    def test_headless_never_staged(self):
        r = self.repo({".head": b"x", "eligible.html": b"<head></head>", "skip.html": b"fragment"})
        _, m, _ = r.normalize(self.ev, "stage-headless")
        r.stage(m)
        names = run(["git", "-C", str(r.root), "diff", "--cached", "--name-only"], check=True).stdout.decode().splitlines()
        self.assertEqual(names, ["eligible.html"])

    def test_headless_idempotence_reports_same_set(self):
        r = self.repo({".head": b"x", "skip.html": b"fragment", "eligible.html": b"<head></head>"})
        _, _, first_summary = r.normalize(self.ev, "idem-first")
        run(["git", "-C", str(r.root), "add", "."]); run(["git", "-C", str(r.root), "commit", "-qm", "update"])
        _, second_manifest, second_summary = r.normalize(self.ev, "idem-second")
        first = json.loads(first_summary.read_text(encoding="utf-8")); second = json.loads(second_summary.read_text(encoding="utf-8"))
        self.assertEqual(first["skipped_headless_paths"], second["skipped_headless_paths"])
        self.assertEqual(second["changed"], 0)
        self.assertEqual(second_manifest.read_bytes(), b"")

    def test_later_poison_rolls_back_eligible_and_headless(self):
        r = self.repo({
            ".head": b"x",
            "eligible.html": b"<head></head>",
            "skip.html": b"fragment",
            "poison.html": b"<head></head></head>",
        })
        before = {p.relative_to(r.root): p.read_bytes() for p in r.root.rglob("*") if p.is_file() and ".git" not in p.parts}
        p, m, s = r.normalize(self.ev, "later-poison", check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("exactly one", p.stderr.decode())
        self.assertFalse(m.exists()); self.assertFalse(s.exists())
        after = {p.relative_to(r.root): p.read_bytes() for p in r.root.rglob("*") if p.is_file() and ".git" not in p.parts}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
