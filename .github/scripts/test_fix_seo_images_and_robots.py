#!/usr/bin/env python3
"""Comprehensive test suite for fix_seo_images_and_robots.py."""

import shutil
import tempfile
import unittest
from pathlib import Path
import sys

# Add script directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "canonical" / "scripts"))
import fix_seo_images_and_robots as engine


class TestFixSeoImagesAndRobots(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tracker_domain_detection(self):
        self.assertTrue(engine.is_tracker_domain("track.kaca.co.id"))
        self.assertTrue(engine.is_tracker_domain("link.partisi.co.id"))
        self.assertTrue(engine.is_tracker_domain("klik.besi.co.id"))
        self.assertFalse(engine.is_tracker_domain("kaca.co.id"))
        self.assertFalse(engine.is_tracker_domain("cubicle.kaca.co.id"))
        self.assertFalse(engine.is_tracker_domain("partisi.co.id"))

    def test_robots_txt_generation_standard_site(self):
        changed, status = engine.ensure_robots_txt(self.root, "partisi.co.id")
        self.assertTrue(changed)
        self.assertEqual(status, "created")

        content = (self.root / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Allow: /", content)
        self.assertIn("Disallow: /cdn-cgi/", content)
        self.assertIn("Sitemap: https://partisi.co.id/sitemap.xml", content)

        # Idempotent second run
        changed2, status2 = engine.ensure_robots_txt(self.root, "partisi.co.id")
        self.assertFalse(changed2)
        self.assertEqual(status2, "already_has_cdn_cgi")

    def test_robots_txt_generation_tracker_site(self):
        changed, status = engine.ensure_robots_txt(self.root, "track.partisi.co.id")
        self.assertTrue(changed)
        self.assertEqual(status, "created")

        content = (self.root / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Disallow: /", content)
        self.assertNotIn("Allow: /", content)

    def test_common_prefix_detection(self):
        files = [
            "cubicle-toilet-jakarta.html",
            "cubicle-toilet-surabaya.html",
            "cubicle-toilet-bandung.html",
            "cubicle-toilet-semarang.html",
            "index.html",
        ]
        prefix = engine.detect_common_product_prefix(files)
        self.assertEqual(prefix, "cubicle-toilet")

    def test_image_processing_in_content_section(self):
        sample_html = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<header>
  <img src="/wp-content/logo.png" class="site-logo" alt="Logo">
</header>
<div class="entry-content">
  <p>Introductory paragraph</p>
  <img src="https://blogger.googleusercontent.com/img/cubicle-1.jpg" alt="">
  <a href="/existing-link.html"><img src="/wp-content/type-a.jpg" alt=""></a>
</div>
<footer>
  <img src="/footer-icon.png">
</footer>
</body>
</html>"""
        page = self.root / "cubicle-toilet-aceh-barat.html"
        page.write_text(sample_html, encoding="utf-8")

        # Create destination target pages
        (self.root / "cubicle-toilet-surabaya.html").write_text("<div class='entry-content'></div>", encoding="utf-8")
        (self.root / "cubicle-toilet-medan.html").write_text("<div class='entry-content'></div>", encoding="utf-8")
        (self.root / "cubicle-toilet-bima.html").write_text("<div class='entry-content'></div>", encoding="utf-8")

        res = engine.run(str(self.root), domain="toilet.cubicle.co.id")
        self.assertEqual(res["status"], "success")

        updated_html = page.read_text(encoding="utf-8")

        # 1. Header logo must NOT be wrapped in link
        self.assertIn('<img src="/wp-content/logo.png" class="site-logo" alt="Logo">', updated_html)

        # 2. Footer icon must NOT be wrapped in link
        self.assertIn('<footer>\n  <img src="/footer-icon.png">', updated_html)

        # 3. Content unlinked image must be wrapped in anchor to target city and have enriched alt
        self.assertRegex(updated_html, r'<a href="/cubicle-toilet-[^"]+\.html"[^>]*><img src="https://blogger\.googleusercontent\.com/img/cubicle-1\.jpg" alt="[^"]+"')

        # 4. Content image already in anchor must preserve /existing-link.html and enrich alt
        self.assertIn('<a href="/existing-link.html"><img src="/wp-content/type-a.jpg" alt="Cubicle Toilet Type Aceh Barat"></a>', updated_html)


if __name__ == "__main__":
    unittest.main()
