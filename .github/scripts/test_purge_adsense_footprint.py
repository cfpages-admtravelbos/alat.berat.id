from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


sys.dont_write_bytecode = True
MODULE_PATH = Path(__file__).resolve().with_name("purge_adsense_footprint.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).resolve().parents[1] / "canonical" / "scripts" / "purge_adsense_footprint.py"
SPEC = importlib.util.spec_from_file_location("purge_adsense_footprint", MODULE_PATH)
assert SPEC and SPEC.loader
PURGER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PURGER
SPEC.loader.exec_module(PURGER)


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


class PurgeAdSenseFootprintTests(unittest.TestCase):
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

    def args(self, suffix: str = "one") -> Namespace:
        paths = self.root.parent / f"{self.root.name}-{suffix}-paths.nul"
        summary = self.root.parent / f"{self.root.name}-{suffix}-summary.json"
        output = self.root.parent / f"{self.root.name}-{suffix}-output.txt"
        self.controls.extend((paths, summary, output))
        return Namespace(
            command="apply",
            root=str(self.root),
            paths_file=str(paths),
            summary_file=str(summary),
            github_output=str(output),
        )

    def test_purge_adsense_script_and_ads_txt(self) -> None:
        html_content = (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head>\n"
            "    <title>Sample Site</title>\n"
            '    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-3534718780470570" crossorigin="anonymous"></script>\n'
            "</head>\n"
            "<body>\n"
            "    <h1>Welcome</h1>\n"
            "</body>\n"
            "</html>\n"
        )
        self.write("index.html", html_content.encode("utf-8"))
        self.write("ads.txt", b"google.com, pub-3534718780470570, DIRECT, f08c47fec0942fa0\n")
        self.write(".github/workflows/adsense.yaml", b"name: old workflow\n")
        self.write(".github/scripts/adsense_normalizer.py", b"# old script\n")
        self.commit()

        args = self.args("first")
        self.assertEqual(PURGER.apply_purge(args), 0)

        cleaned_html = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("pagead2.googlesyndication.com", cleaned_html)
        self.assertNotIn("ca-pub-3534718780470570", cleaned_html)
        self.assertIn("<title>Sample Site</title>", cleaned_html)

        # ads.txt and legacy files must be deleted
        self.assertFalse((self.root / "ads.txt").exists())
        self.assertFalse((self.root / ".github/workflows/adsense.yaml").exists())
        self.assertFalse((self.root / ".github/scripts/adsense_normalizer.py").exists())

        # Second run must be idempotent
        args2 = self.args("second")
        self.assertEqual(PURGER.apply_purge(args2), 0)
        summary2 = json.loads(Path(args2.summary_file).read_text(encoding="utf-8"))
        self.assertEqual(summary2["changed_files"], [])

    def test_purge_ins_tag_and_push(self) -> None:
        html_content = (
            "<!DOCTYPE html>\n<html><head></head><body>\n"
            '<ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-1234567812345678" data-ad-slot="1234567890"></ins>\n'
            "<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>\n"
            "<p>Main Content</p>\n"
            "</body></html>\n"
        )
        self.write("page.html", html_content.encode("utf-8"))
        self.commit()

        args = self.args("ins")
        self.assertEqual(PURGER.apply_purge(args), 0)

        cleaned = (self.root / "page.html").read_text(encoding="utf-8")
        self.assertNotIn("adsbygoogle", cleaned)
        self.assertIn("<p>Main Content</p>", cleaned)


if __name__ == "__main__":
    unittest.main()
