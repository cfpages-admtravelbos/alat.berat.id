from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().with_name("sitemap_url_normalizer.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).resolve().parents[1] / "canonical" / "scripts" / "sitemap_url_normalizer.py"
SPEC = importlib.util.spec_from_file_location("sitemap_url_normalizer", MODULE_PATH)
assert SPEC and SPEC.loader
NORMALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NORMALIZER)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class SitemapUrlNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        git(self.root, "init")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@example.invalid")

    def tearDown(self) -> None:
        for suffix in ("paths.nul", "summary.json", "output.txt"):
            path = self.root.parent / f"{self.root.name}-{suffix}"
            if path.exists():
                path.unlink()
        self.temporary.cleanup()

    def write(self, relative: str, data: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def commit(self) -> None:
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "fixture")

    def args(self, *, minimum: str = "1", allow_noop: bool = False) -> Namespace:
        return Namespace(
            root=str(self.root),
            repository="owner/Example.CO.ID",
            base_url="",
            minimum_replacements=minimum,
            allow_noop=allow_noop,
            paths_file=str(self.root.parent / f"{self.root.name}-paths.nul"),
            summary_file=str(self.root.parent / f"{self.root.name}-summary.json"),
            github_output=str(self.root.parent / f"{self.root.name}-output.txt"),
        )

    def test_derives_https_origin_from_repository_name(self) -> None:
        self.assertEqual(NORMALIZER.normalize_base_url("", "owner/Example.CO.ID"), "https://example.co.id")

    def test_rejects_credentials_path_query_fragment_and_port(self) -> None:
        for value in (
            "http://example.id",
            "https://user@example.id",
            "https://example.id:443",
            "https://example.id/path",
            "https://example.id?q=1",
            "https://example.id/#x",
        ):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                NORMALIZER.normalize_base_url(value, "owner/repo")

    def test_preserves_bom_crlf_and_final_newline_state(self) -> None:
        original = b"\xef\xbb\xbf<urlset>\r\n<loc>/a</loc>\r\n<loc>/b</loc></urlset>"
        self.write("SITEMAP.XML", original)
        self.commit()
        NORMALIZER.normalize(self.args())
        expected = original.replace(b"loc>/", b"loc>https://example.co.id/")
        self.assertEqual((self.root / "SITEMAP.XML").read_bytes(), expected)

    def test_changes_only_tracked_xml_files(self) -> None:
        self.write("sitemap.xml", b"<loc>/tracked</loc>\n")
        self.write("page.html", b"<loc>/html</loc>\n")
        self.commit()
        self.write("untracked.xml", b"<loc>/untracked</loc>\n")
        NORMALIZER.normalize(self.args())
        self.assertEqual((self.root / "sitemap.xml").read_bytes(), b"<loc>https://example.co.id/tracked</loc>\n")
        self.assertEqual((self.root / "page.html").read_bytes(), b"<loc>/html</loc>\n")
        self.assertEqual((self.root / "untracked.xml").read_bytes(), b"<loc>/untracked</loc>\n")

    def test_rejects_zero_match_without_explicit_noop(self) -> None:
        self.write("sitemap.xml", b"<loc>https://example.co.id/a</loc>\n")
        self.commit()
        with self.assertRaises(SystemExit):
            NORMALIZER.normalize(self.args())

    def test_allows_reviewed_idempotent_noop(self) -> None:
        self.write("sitemap.xml", b"<loc>https://example.co.id/a</loc>\n")
        self.commit()
        NORMALIZER.normalize(self.args(minimum="0", allow_noop=True))
        self.assertEqual((self.root.parent / f"{self.root.name}-paths.nul").read_bytes(), b"")

    def test_exact_git_boundary_before_and_after_staging(self) -> None:
        self.write("a.xml", b"<loc>/a</loc>\n")
        self.write("nested/b.xml", b"<loc>/b</loc>\n")
        self.commit()
        args = self.args()
        NORMALIZER.normalize(args)
        NORMALIZER.verify_git(Namespace(root=str(self.root), paths_file=args.paths_file, state="unstaged"))
        git(self.root, "add", "--", "a.xml", "nested/b.xml")
        NORMALIZER.verify_git(Namespace(root=str(self.root), paths_file=args.paths_file, state="staged"))

    def test_unexpected_dirty_path_poison_fails_boundary(self) -> None:
        self.write("sitemap.xml", b"<loc>/a</loc>\n")
        self.write("other.txt", b"clean\n")
        self.commit()
        args = self.args()
        NORMALIZER.normalize(args)
        self.write("other.txt", b"dirty\n")
        with self.assertRaises(SystemExit):
            NORMALIZER.verify_git(Namespace(root=str(self.root), paths_file=args.paths_file, state="unstaged"))


if __name__ == "__main__":
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    unittest.main()
