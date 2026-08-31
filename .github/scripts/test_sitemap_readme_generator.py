from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().with_name("sitemap_readme_generator.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).resolve().parents[1] / "canonical" / "scripts" / "sitemap_readme_generator.py"
SPEC = importlib.util.spec_from_file_location("sitemap_readme_generator", MODULE_PATH)
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)


def git(root: Path, *args: str, env: dict[str, str] | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return result.stdout


class SitemapReadmeGeneratorTests(unittest.TestCase):
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

    def args(
        self,
        *,
        base_url: str = "",
        minimum_urls: str = "1",
        url_list_mode: str = "auto",
        suffix: str = "one",
    ) -> Namespace:
        paths = self.root.parent / f"{self.root.name}-{suffix}-paths.nul"
        summary = self.root.parent / f"{self.root.name}-{suffix}-summary.json"
        output = self.root.parent / f"{self.root.name}-{suffix}-output.txt"
        self.controls.extend((paths, summary, output))
        return Namespace(
            root=str(self.root),
            repository="owner/Example.CO.ID",
            base_url=base_url,
            minimum_urls=minimum_urls,
            url_list_mode=url_list_mode,
            paths_file=str(paths),
            summary_file=str(summary),
            github_output=str(output),
        )

    def test_base_url_precedence_and_validation(self) -> None:
        self.write("index.html", b"home")
        self.commit()
        self.assertEqual(
            GENERATOR.resolve_base_url(self.root, "https://Explicit.ID", "owner/repo.id"),
            "https://explicit.id",
        )
        self.write("CNAME", b"Custom.Example.ID\n")
        git(self.root, "add", "CNAME")
        git(self.root, "commit", "-m", "cname")
        self.assertEqual(
            GENERATOR.resolve_base_url(self.root, "", "owner/repo.id"),
            "https://custom.example.id",
        )
        (self.root / "CNAME").unlink()
        git(self.root, "rm", "--cached", "CNAME")
        self.assertEqual(
            GENERATOR.resolve_base_url(self.root, "", "owner/Example.CO.ID"),
            "https://example.co.id",
        )
        for value in (
            "http://example.id",
            "https://user@example.id",
            "https://example.id:443",
            "https://example.id/path",
            "https://example.id?q=1",
            "https://example.id/#x",
        ):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                GENERATOR.normalize_origin(value, "fixture")

    def test_generates_encoded_sorted_routes_and_search_links(self) -> None:
        self.write("index.html", b"root")
        self.write("Folder Name/index.html", b"folder")
        self.write("produk/a & ñ.html", b"unicode")
        self.commit()
        args = self.args()
        GENERATOR.generate(args)
        sitemap = (self.root / "sitemap-complete.xml").read_text(encoding="utf-8")
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("<loc>https://example.co.id/</loc>", sitemap)
        self.assertIn("<loc>https://example.co.id/Folder%20Name/</loc>", sitemap)
        self.assertIn("<loc>https://example.co.id/produk/a%20%26%20%C3%B1</loc>", sitemap)
        self.assertIn("q=site%3Ahttps%3A%2F%2Fexample.co.id%2F", readme)
        self.assertEqual(sitemap.count("<url>"), 3)
        summary = json.loads(Path(args.summary_file).read_text(encoding="utf-8"))
        self.assertEqual(summary["url_count"], 3)
        self.assertEqual(summary["changed_files"], ["README.md", "sitemap-complete.xml"])

    def test_replaces_exact_legacy_readme_but_preserves_unrelated_content(self) -> None:
        self.write("index.html", b"root")
        self.write(
            "README.md",
            (
                "\n## Sitemap URLs\nNumber of URLs: 1\n"
                "- [https://old.id/](https://google.com/search?q=site%3Ahttps://old.id/)\n"
            ).encode(),
        )
        self.commit()
        GENERATOR.generate(self.args())
        upgraded = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertTrue(upgraded.startswith(GENERATOR.BEGIN_MARKER))
        self.assertNotIn("old.id", upgraded)

        git(self.root, "add", "README.md", "sitemap-complete.xml")
        git(self.root, "commit", "-m", "generated")
        (self.root / "README.md").write_text("# Project\n\nKeep this.\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "project readme")
        GENERATOR.generate(self.args(suffix="mixed"))
        mixed = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("# Project\n\nKeep this.", mixed)
        self.assertEqual(mixed.count(GENERATOR.BEGIN_MARKER), 1)
        self.assertEqual(mixed.count(GENERATOR.END_MARKER), 1)

    def test_auto_url_list_preserves_both_historical_classes_and_missing_output_exception(self) -> None:
        self.write("index.html", b"root")
        self.commit()
        args = self.args()
        GENERATOR.generate(args)
        self.assertFalse((self.root / "url-list.txt").exists())
        self.assertEqual(
            Path(args.paths_file).read_bytes(),
            b"README.md\0sitemap-complete.xml\0",
        )

        git(self.root, "add", "README.md", "sitemap-complete.xml")
        git(self.root, "commit", "-m", "first class")
        self.write("url-list.txt", b"legacy\n")
        git(self.root, "add", "url-list.txt")
        git(self.root, "commit", "-m", "track list only")
        (self.root / "README.md").unlink()
        (self.root / "sitemap-complete.xml").unlink()
        git(self.root, "rm", "README.md", "sitemap-complete.xml")
        git(self.root, "commit", "-m", "missing coupled outputs")
        exception = self.args(suffix="exception")
        GENERATOR.generate(exception)
        self.assertTrue((self.root / "README.md").is_file())
        self.assertTrue((self.root / "sitemap-complete.xml").is_file())
        self.assertIn("https://example.co.id/", (self.root / "url-list.txt").read_text(encoding="utf-8"))
        self.assertEqual(
            Path(exception.paths_file).read_bytes(),
            b"README.md\0sitemap-complete.xml\0url-list.txt\0",
        )

    def test_preserves_bom_crlf_and_final_newline_state(self) -> None:
        self.write("index.html", b"root")
        self.write("README.md", b"\xef\xbb\xbf# Project\r\nKeep\r\n")
        self.write(
            "sitemap-complete.xml",
            b"\xef\xbb\xbf<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n<urlset></urlset>",
        )
        self.write("url-list.txt", b"\xef\xbb\xbflegacy\r\n")
        self.commit()
        GENERATOR.generate(self.args())
        readme = (self.root / "README.md").read_bytes()
        sitemap = (self.root / "sitemap-complete.xml").read_bytes()
        url_list = (self.root / "url-list.txt").read_bytes()
        self.assertTrue(readme.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", readme.replace(b"\r\n", b""))
        self.assertTrue(readme.endswith(b"\r\n"))
        self.assertTrue(sitemap.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", sitemap.replace(b"\r\n", b""))
        self.assertFalse(sitemap.endswith(b"\r\n"))
        self.assertTrue(url_list.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(url_list.endswith(b"\r\n"))

    def test_second_run_is_idempotent_and_history_dates_remain_stable(self) -> None:
        self.write("index.html", b"root")
        self.write("nested/page.html", b"page")
        self.commit()
        first = self.args()
        GENERATOR.generate(first)
        original = (self.root / "sitemap-complete.xml").read_bytes()
        git(self.root, "add", "README.md", "sitemap-complete.xml")
        git(self.root, "commit", "-m", "generated outputs only")
        second = self.args(suffix="second")
        GENERATOR.generate(second)
        self.assertEqual(Path(second.paths_file).read_bytes(), b"")
        self.assertEqual((self.root / "sitemap-complete.xml").read_bytes(), original)
        self.assertEqual(git(self.root, "status", "--porcelain=v1"), b"")

    def test_invalid_utf8_and_bad_markers_fail_before_output_mutation(self) -> None:
        self.write("index.html", b"root")
        self.write("README.md", b"\xff")
        self.commit()
        with self.assertRaises(SystemExit):
            GENERATOR.generate(self.args())
        self.assertFalse((self.root / "sitemap-complete.xml").exists())

        self.write("README.md", f"{GENERATOR.BEGIN_MARKER}\nunterminated\n".encode())
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "bad marker")
        with self.assertRaises(SystemExit):
            GENERATOR.generate(self.args(suffix="marker"))
        self.assertFalse((self.root / "sitemap-complete.xml").exists())

        self.write(
            "README.md",
            f"{GENERATOR.BEGIN_MARKER} trailing-space \n{GENERATOR.END_MARKER}\n".encode(),
        )
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "non-standalone marker")
        with self.assertRaises(SystemExit):
            GENERATOR.generate(self.args(suffix="marker-text"))
        self.assertFalse((self.root / "sitemap-complete.xml").exists())

    def test_minimum_zero_html_and_duplicate_route_poisons(self) -> None:
        self.write("page.html", b"page")
        self.commit()
        with self.assertRaises(SystemExit):
            GENERATOR.generate(self.args(minimum_urls="2"))
        with mock.patch.object(GENERATOR, "tracked_html_paths", return_value=["index.html", "INDEX.HTML"]):
            with mock.patch.object(
                GENERATOR,
                "git_lastmod_map",
                return_value={"index.html": "2026-01-01T00:00:00+00:00", "INDEX.HTML": "2026-01-01T00:00:00+00:00"},
            ):
                with self.assertRaises(SystemExit):
                    GENERATOR.build_pages(self.root, "https://example.id", 1)

        empty = tempfile.TemporaryDirectory()
        try:
            other = Path(empty.name)
            git(other, "init")
            git(other, "config", "user.name", "Fixture")
            git(other, "config", "user.email", "fixture@example.invalid")
            (other / "file.txt").write_text("x", encoding="utf-8")
            git(other, "add", ".")
            git(other, "commit", "-m", "empty")
            with self.assertRaises(SystemExit):
                GENERATOR.build_pages(other, "https://example.id", 0)
        finally:
            empty.cleanup()

    def test_exact_git_boundary_before_and_after_staging(self) -> None:
        self.write("index.html", b"root")
        self.commit()
        args = self.args()
        GENERATOR.generate(args)
        GENERATOR.verify_git(Namespace(root=str(self.root), paths_file=args.paths_file, state="unstaged"))
        git(
            self.root,
            "add",
            "--pathspec-from-file=" + args.paths_file,
            "--pathspec-file-nul",
        )
        GENERATOR.verify_git(Namespace(root=str(self.root), paths_file=args.paths_file, state="staged"))

    def test_unexpected_dirty_path_and_output_symlink_poisons(self) -> None:
        self.write("index.html", b"root")
        self.write("other.txt", b"clean\n")
        self.commit()
        args = self.args()
        GENERATOR.generate(args)
        self.write("other.txt", b"dirty\n")
        with self.assertRaises(SystemExit):
            GENERATOR.verify_git(Namespace(root=str(self.root), paths_file=args.paths_file, state="unstaged"))

        linked = tempfile.TemporaryDirectory()
        try:
            other = Path(linked.name)
            git(other, "init")
            git(other, "config", "user.name", "Fixture")
            git(other, "config", "user.email", "fixture@example.invalid")
            (other / "index.html").write_text("root", encoding="utf-8")
            target = other / "target.md"
            target.write_text("target", encoding="utf-8")
            try:
                os.symlink(target, other / "README.md")
            except OSError:
                self.skipTest("symlink creation is unavailable on this Windows host")
            git(other, "add", ".")
            git(other, "commit", "-m", "symlink")
            poison = Namespace(
                root=str(other),
                repository="owner/example.id",
                base_url="",
                minimum_urls="1",
                url_list_mode="auto",
                paths_file=str(other.parent / f"{other.name}-paths.nul"),
                summary_file=str(other.parent / f"{other.name}-summary.json"),
                github_output=str(other.parent / f"{other.name}-output.txt"),
            )
            self.controls.extend((Path(poison.paths_file), Path(poison.summary_file), Path(poison.github_output)))
            with self.assertRaises(SystemExit):
                GENERATOR.generate(poison)
        finally:
            linked.cleanup()


if __name__ == "__main__":
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    unittest.main()
