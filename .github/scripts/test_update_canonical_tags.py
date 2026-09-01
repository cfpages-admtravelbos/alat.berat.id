#!/usr/bin/env python3
"""Production-shaped regression tests for update_canonical_tags.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


THIS_FILE = Path(__file__).resolve()
SIBLING_SCRIPT = THIS_FILE.with_name("update_canonical_tags.py")
SCRIPT = (
    SIBLING_SCRIPT
    if SIBLING_SCRIPT.is_file()
    else THIS_FILE.parents[1] / "canonical" / "scripts" / "update_canonical_tags.py"
)


def run(
    arguments: list[str], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.run(
        arguments,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode != 0:
        raise AssertionError(
            f"command failed ({process.returncode}): {arguments!r}\n"
            f"stdout={process.stdout.decode('utf-8', errors='replace')}\n"
            f"stderr={process.stderr.decode('utf-8', errors='replace')}"
        )
    return process


def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return run(["git", "-C", str(root), *arguments], check=check)


def split_nul(data: bytes) -> list[str]:
    if not data:
        return []
    assert data.endswith(b"\0")
    return [item.decode("utf-8") for item in data[:-1].split(b"\0")]


class Fixture:
    def __init__(self, root: Path, files: dict[str, bytes], *, commit: bool = True):
        self.root = root
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.name", "Canonical Test")
        git(root, "config", "user.email", "canonical-test@example.invalid")
        git(root, "config", "core.autocrlf", "false")
        for relative_path, data in files.items():
            path = root.joinpath(*relative_path.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        git(root, "add", "--all")
        if commit:
            git(root, "commit", "-q", "-m", "fixture")

    def normalize(
        self,
        evidence_root: Path,
        name: str,
        *,
        repository: str = "owner/example.co.id",
        site_origin: str = "",
        check: bool = True,
    ) -> tuple[subprocess.CompletedProcess[bytes], Path, Path]:
        manifest = evidence_root / f"{name}.manifest.bin"
        summary = evidence_root / f"{name}.summary.json"
        process = run(
            [
                sys.executable,
                str(SCRIPT),
                "normalize",
                "--root",
                str(self.root),
                "--repository",
                repository,
                "--site-origin",
                site_origin,
                "--manifest",
                str(manifest),
                "--summary",
                str(summary),
            ],
            check=check,
        )
        return process, manifest, summary

    def stage(
        self, manifest: Path, *, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        return run(
            [
                sys.executable,
                str(SCRIPT),
                "stage",
                "--root",
                str(self.root),
                "--manifest",
                str(manifest),
            ],
            check=check,
        )


class CanonicalNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="canonical-normalizer-")
        self.base = Path(self.temporary.name)
        self.evidence = self.base / "evidence"
        self.evidence.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def fixture(self, files: dict[str, bytes], *, commit: bool = True) -> Fixture:
        return Fixture(self.base / f"repo-{len(list(self.base.glob('repo-*')))}", files, commit=commit)

    def assert_failed_without_mutation(
        self,
        fixture: Fixture,
        name: str,
        expected_error: str,
        *,
        repository: str = "owner/example.co.id",
        site_origin: str = "",
    ) -> None:
        before = {
            path.relative_to(fixture.root).as_posix(): path.read_bytes()
            for path in fixture.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        process, manifest, summary = fixture.normalize(
            self.evidence,
            name,
            repository=repository,
            site_origin=site_origin,
            check=False,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(expected_error, process.stderr.decode("utf-8"))
        self.assertFalse(manifest.exists())
        self.assertFalse(summary.exists())
        after = {
            path.relative_to(fixture.root).as_posix(): path.read_bytes()
            for path in fixture.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        self.assertEqual(before, after)
        self.assertEqual(git(fixture.root, "status", "--porcelain").stdout, b"")

    def test_mixed_paths_bytes_exact_staging_and_idempotence(self) -> None:
        files = {
            "index.html": b"\xef\xbb\xbf<html>\r\n<link href='/old' REL='Canonical'>\r\n</html>\r\n",
            "nested/path/index.html": b'<link\n rel = "canonical"\n href = "/old">\n',
            "artikel/flat.html": b'<LINK REL="canonical" HREF="/old">',
            "ruang nama/café.html": b'<link rel="canonical" href="/old">\r\n',
            "UPPER.HTML": b"<link href='/old' rel='alternate canonical'>",
            "no-tag.html": b"<html>\r\nno canonical\r\n</html>",
        }
        fixture = self.fixture(files)
        process, manifest, summary_path = fixture.normalize(
            self.evidence, "mixed", site_origin="https://Example.CO.ID/"
        )
        self.assertEqual(process.returncode, 0)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        expected_paths = [
            "UPPER.HTML",
            "artikel/flat.html",
            "index.html",
            "nested/path/index.html",
            "ruang nama/café.html",
        ]
        self.assertEqual(split_nul(manifest.read_bytes()), expected_paths)
        self.assertEqual(summary["changed_paths"], expected_paths)
        self.assertEqual(summary["changed"], 5)
        self.assertEqual(summary["skipped_no_tag"], 1)
        self.assertEqual(
            (fixture.root / "index.html").read_bytes(),
            b"\xef\xbb\xbf<html>\r\n<link href='https://example.co.id/' REL='Canonical'>\r\n</html>\r\n",
        )
        self.assertEqual(
            (fixture.root / "nested/path/index.html").read_bytes(),
            b'<link\n rel = "canonical"\n href = "https://example.co.id/nested/path/">\n',
        )
        self.assertEqual(
            (fixture.root / "artikel/flat.html").read_bytes(),
            b'<LINK REL="canonical" HREF="https://example.co.id/artikel/flat">',
        )
        self.assertEqual(
            (fixture.root / "ruang nama/café.html").read_bytes(),
            b'<link rel="canonical" href="https://example.co.id/ruang%20nama/caf%C3%A9">\r\n',
        )
        self.assertEqual((fixture.root / "no-tag.html").read_bytes(), files["no-tag.html"])

        fixture.stage(manifest)
        self.assertEqual(
            split_nul(git(fixture.root, "diff", "--cached", "--name-only", "-z").stdout),
            expected_paths,
        )
        git(fixture.root, "commit", "-q", "-m", "normalize")
        snapshot = {
            path.relative_to(fixture.root).as_posix(): path.read_bytes()
            for path in fixture.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        _, second_manifest, second_summary = fixture.normalize(
            self.evidence, "mixed-second", site_origin="https://example.co.id"
        )
        self.assertEqual(second_manifest.read_bytes(), b"")
        self.assertEqual(
            json.loads(second_summary.read_text(encoding="utf-8"))["changed"], 0
        )
        second_snapshot = {
            path.relative_to(fixture.root).as_posix(): path.read_bytes()
            for path in fixture.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        self.assertEqual(snapshot, second_snapshot)
        fixture.stage(second_manifest)

    def test_unanimous_existing_origin_is_inferred(self) -> None:
        fixture = self.fixture(
            {
                "index.html": b'<link rel="canonical" href="https://Site.Example/index">',
                "page.html": b'<link href="https://site.example/page.html" rel="canonical">',
            }
        )
        _, manifest, summary = fixture.normalize(self.evidence, "inferred")
        self.assertEqual(json.loads(summary.read_text(encoding="utf-8"))["origin"], "https://site.example")
        self.assertEqual(split_nul(manifest.read_bytes()), ["index.html", "page.html"])
        self.assertIn(b"https://site.example/", (fixture.root / "index.html").read_bytes())

    def test_repository_hostname_fallback(self) -> None:
        fixture = self.fixture(
            {"page.html": b'<link rel="canonical" href="/old">'}
        )
        _, _, summary = fixture.normalize(
            self.evidence, "fallback", repository="owner/Site.Example"
        )
        self.assertEqual(
            json.loads(summary.read_text(encoding="utf-8"))["origin"],
            "https://site.example",
        )

    def test_invalid_repository_hostname_is_transactional_poison(self) -> None:
        fixture = self.fixture(
            {"page.html": b'<link rel="canonical" href="/old">'}
        )
        self.assert_failed_without_mutation(
            fixture,
            "invalid-repository",
            "repository-derived hostname requires",
            repository="owner/toilet.tukang.co.id-gataukerjaansiapa",
        )

    def test_multiple_existing_origins_are_transactional_poison(self) -> None:
        fixture = self.fixture(
            {
                "one.html": b'<link rel="canonical" href="https://one.example/old">',
                "two.html": b'<link rel="canonical" href="https://two.example/old">',
            }
        )
        self.assert_failed_without_mutation(
            fixture, "multiple-origins", "multiple existing canonical origins"
        )

    def test_explicit_origin_conflict_is_transactional_poison(self) -> None:
        fixture = self.fixture(
            {
                "page.html": b'<link rel="canonical" href="https://one.example/old">'
            }
        )
        self.assert_failed_without_mutation(
            fixture,
            "explicit-conflict",
            "conflicts with existing origin",
            site_origin="https://two.example",
        )

    def test_duplicate_canonical_tags_are_transactional_poison(self) -> None:
        fixture = self.fixture(
            {
                "page.html": (
                    b'<link rel="canonical" href="/one">\n'
                    b'<link href="/two" rel="canonical">'
                )
            }
        )
        self.assert_failed_without_mutation(
            fixture, "duplicates", "multiple canonical link tags"
        )

    def test_unquoted_or_missing_href_is_transactional_poison(self) -> None:
        for index, body in enumerate(
            [
                b'<link rel="canonical" href=/old>',
                b'<link rel="canonical">',
                b'<link rel="canonical" href="">',
            ]
        ):
            fixture = self.fixture({"page.html": body})
            self.assert_failed_without_mutation(
                fixture,
                f"bad-href-{index}",
                "canonical href must" if index != 1 else "exactly one href",
            )

    def test_invalid_utf8_is_transactional_poison(self) -> None:
        fixture = self.fixture(
            {"page.html": b'<link rel="canonical" href="/old">\xff'}
        )
        self.assert_failed_without_mutation(
            fixture, "invalid-utf8", "file is not strict UTF-8"
        )

    def test_comment_link_is_ignored(self) -> None:
        original = (
            b'<!-- <link rel="canonical" href="/comment"> -->\n'
            b'<link rel="canonical" href="/real">\n'
        )
        fixture = self.fixture({"page.html": original})
        fixture.normalize(
            self.evidence, "comment", site_origin="https://example.co.id"
        )
        updated = (fixture.root / "page.html").read_bytes()
        self.assertIn(b'href="/comment"', updated)
        self.assertIn(b'href="https://example.co.id/page"', updated)

    def test_fresh_outputs_must_be_outside_worktree(self) -> None:
        fixture = self.fixture(
            {"page.html": b'<link rel="canonical" href="/old">'}
        )
        manifest = fixture.root / "manifest.bin"
        summary = self.evidence / "inside-summary.json"
        process = run(
            [
                sys.executable,
                str(SCRIPT),
                "normalize",
                "--root",
                str(fixture.root),
                "--repository",
                "owner/example.co.id",
                "--manifest",
                str(manifest),
                "--summary",
                str(summary),
            ],
            check=False,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("manifest must be outside", process.stderr.decode("utf-8"))
        self.assertEqual(git(fixture.root, "status", "--porcelain").stdout, b"")

    def test_stage_rejects_unrelated_change_without_staging(self) -> None:
        fixture = self.fixture(
            {
                "page.html": b'<link rel="canonical" href="/old">',
                "note.txt": b"before\n",
            }
        )
        _, manifest, _ = fixture.normalize(
            self.evidence, "stage-poison", site_origin="https://example.co.id"
        )
        (fixture.root / "note.txt").write_bytes(b"after\n")
        process = fixture.stage(manifest, check=False)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(
            "worktree changes do not equal manifest",
            process.stderr.decode("utf-8"),
        )
        self.assertEqual(
            git(fixture.root, "diff", "--cached", "--name-only").stdout, b""
        )

    def test_noop_stage_rejects_untracked_path(self) -> None:
        fixture = self.fixture({"page.html": b"<html>no tag</html>"})
        _, manifest, _ = fixture.normalize(self.evidence, "noop")
        (fixture.root / "untracked.txt").write_text("unexpected", encoding="utf-8")
        process = fixture.stage(manifest, check=False)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("untracked paths", process.stderr.decode("utf-8"))

    def test_malformed_comment_is_transactional_poison(self) -> None:
        fixture = self.fixture(
            {
                "page.html": (
                    b"<!-- unterminated\n"
                    b'<link rel="canonical" href="/old">'
                )
            }
        )
        self.assert_failed_without_mutation(
            fixture, "comment-poison", "unterminated HTML comment"
        )

    @unittest.skipUnless(
        os.environ.get("RUN_CANONICAL_PERFORMANCE_TEST") == "1",
        "set RUN_CANONICAL_PERFORMANCE_TEST=1 for the bounded stress fixture",
    )
    def test_large_7193_html_repository_shape(self) -> None:
        files: dict[str, bytes] = {}
        for index in range(7193):
            relative = f"page/{index:04d}/index.html"
            if index < 1000:
                files[relative] = b'<link rel="canonical" href="/old">'
            else:
                files[relative] = b"<html>no canonical</html>"
        fixture = self.fixture(files, commit=False)
        started = time.perf_counter()
        _, manifest, summary_path = fixture.normalize(
            self.evidence,
            "large",
            site_origin="https://large.example",
        )
        elapsed = time.perf_counter() - started
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["tracked_html"], 7193)
        self.assertEqual(summary["changed"], 1000)
        self.assertEqual(len(split_nul(manifest.read_bytes())), 1000)
        self.assertLess(elapsed, 20.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
