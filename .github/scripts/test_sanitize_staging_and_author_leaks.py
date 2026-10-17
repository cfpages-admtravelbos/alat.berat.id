#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

# Add canonical scripts dir and sibling dir to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "canonical" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sanitize_staging_and_author_leaks import (
    TextStyle,
    decode_document,
    encode_document,
    sanitize_text_content,
)


class TestSanitizeStagingAndAuthorLeaks(unittest.TestCase):
    def setUp(self):
        self.domain = "toilet.portabel.id"
        self.brand = "Toilet Portabel"

    def test_sanitize_staging_urls_in_html(self):
        sample_html = (
            '<html>\n'
            '<head>\n'
            '<link rel="stylesheet" href="http://adisty.my.id/wp-content/themes/astra/style.css">\n'
            '<script src="https://adisty.my.id/wp-includes/js/jquery.js"></script>\n'
            '<meta http-equiv="refresh" content="0;url=httpsadisty.my.id/low-price-2">\n'
            '<script>window.location = "httpsadisty.my.id/low-price-2";</script>\n'
            '</head>\n'
            '<body>\n'
            '<p>Redirecting to <a href="httpsadisty.my.id/low-price-2">low price</a></p>\n'
            '</body>\n'
            '</html>'
        )
        sanitized, staging_c, author_c = sanitize_text_content(sample_html, self.domain, self.brand)
        self.assertGreater(staging_c, 0)
        self.assertNotIn("adisty.my.id", sanitized)
        self.assertNotIn("httpsadisty.my.id", sanitized)
        self.assertIn('href="/wp-content/themes/astra/style.css"', sanitized)
        self.assertIn('src="/wp-includes/js/jquery.js"', sanitized)
        self.assertIn('content="0;url=/low-price-2"', sanitized)
        self.assertIn('window.location = "/low-price-2"', sanitized)
        self.assertIn('href="/low-price-2"', sanitized)

    def test_sanitize_escaped_json_staging_urls(self):
        sample_json_html = (
            '<script>\n'
            'window._wpemojiSettings = {"concatemoji":"http:\\/\\/adisty.my.id\\/wp-includes\\/js\\/wp-emoji.min.js"};\n'
            'var localize = {"ajaxurl":"http:\\/\\/adisty.my.id\\/wp-admin\\/admin-ajax.php"};\n'
            '</script>'
        )
        sanitized, staging_c, author_c = sanitize_text_content(sample_json_html, self.domain, self.brand)
        self.assertGreater(staging_c, 0)
        self.assertNotIn("adisty.my.id", sanitized)
        self.assertIn('"concatemoji":"\\/wp-includes\\/js\\/wp-emoji.min.js"', sanitized)
        self.assertIn('"ajaxurl":"\\/wp-admin\\/admin-ajax.php"', sanitized)

    def test_sanitize_rank_math_author_schema(self):
        sample_schema_html = (
            '<script type="application/ld+json" class="rank-math-schema">'
            '{"@context":"https://schema.org","@graph":['
            '{"@type":["Person","Organization"],"@id":"httpsadisty.my.id/#person","name":"Portabel.id"},'
            '{"@type":"WebSite","@id":"httpsadisty.my.id/#website","name":"Portabel.id","publisher":{"@id":"/#person"}},'
            '{"@type":"Person","@id":"/author/admin","name":"admin","url":"/author/admin"},'
            '{"@type":"Article","headline":"Toilet Portabel","author":{"@id":"/author/admin","name":"Syamsul Alam"},"publisher":{"@id":"/#person"}}'
            ']}'
            '</script>'
        )
        sanitized, staging_c, author_c = sanitize_text_content(sample_schema_html, self.domain, self.brand)
        self.assertNotIn("Syamsul Alam", sanitized)
        self.assertNotIn("adisty.my.id", sanitized)
        self.assertIn('"name":"Toilet Portabel"', sanitized)
        self.assertIn('"@type":"Organization"', sanitized)
        self.assertIn(f'"@id":"https://{self.domain}/#organization"', sanitized)

    def test_sanitize_visible_author_elements(self):
        sample_body_html = (
            '<div class="elementor-icon-box-title">\n'
            '<span>\n'
            '\tSyamsul Alam\t\t\t\t\t\t</span>\n'
            '</div>\n'
            '<p class="elementor-icon-box-description">\n'
            'Founder Portabel.id\t\t\t\t\t</p>\n'
            '<a href="/author/syamsul-alam/">Artikel Author</a>\n'
            '<meta property="og:url" content="https://toilet.portabel.id/author/syamsul-alam/">'
        )
        sanitized, staging_c, author_c = sanitize_text_content(sample_body_html, self.domain, self.brand)
        self.assertNotIn("Syamsul Alam", sanitized)
        self.assertNotIn("/author/syamsul-alam", sanitized)
        self.assertIn(f"Tim {self.brand}", sanitized)
        self.assertIn(f"Tim Layanan {self.brand}", sanitized)
        self.assertIn('href="/"', sanitized)

    def test_idempotency(self):
        sample = (
            '<html><head>\n'
            '<link rel="stylesheet" href="http://adisty.my.id/wp-content/style.css">\n'
            '<script type="application/ld+json" class="rank-math-schema">{"@graph":[{"@type":"Article","author":{"@id":"/author/syamsul-alam","name":"Syamsul Alam"}}]}</script>\n'
            '</head><body>\n'
            '<div class="elementor-icon-box-title"><span>Syamsul Alam</span></div>\n'
            '</body></html>'
        )
        pass1, s1, a1 = sanitize_text_content(sample, self.domain, self.brand)
        self.assertGreater(s1 + a1, 0)

        pass2, s2, a2 = sanitize_text_content(pass1, self.domain, self.brand)
        self.assertEqual(s2, 0)
        self.assertEqual(a2, 0)
        self.assertEqual(pass1, pass2)

    def test_encoding_preservation(self):
        raw = b'\xef\xbb\xbf<html content="http://adisty.my.id/wp-content/">\r\n</html>\r\n'
        content, style = decode_document(raw, "test.html")
        self.assertTrue(style.bom)
        self.assertEqual(style.newline, "\r\n")
        self.assertTrue(style.final_newline)

        sanitized, _, _ = sanitize_text_content(content, self.domain, self.brand)
        re_encoded = encode_document(sanitized, style)
        self.assertTrue(re_encoded.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", re_encoded)
        self.assertNotIn(b"adisty.my.id", re_encoded)


if __name__ == "__main__":
    unittest.main()
