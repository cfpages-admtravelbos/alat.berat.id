#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "update_clients.py"
if not SCRIPT.exists():
    SCRIPT = HERE.parent / "canonical" / "scripts" / "update_clients.py"
INSTALLED_CLIENTS = HERE.parent / "workflows" / "clients.yaml"
CLIENTS_FIXTURE = INSTALLED_CLIENTS if INSTALLED_CLIENTS.exists() else HERE.parent / "canonical" / "clients.yaml"
SPEC = importlib.util.spec_from_file_location("update_clients", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

OLD_PHONE = "0800 0000 0000"
NEW_PHONE = "0899 9999 9999"
OLD_NAME = "Old Fixture"
NEW_NAME = "New Fixture"
OLD_WA = "https://example.test/old-wa💬"
NEW_WA = "https://wa.me/620000000099"
OLD_TEL = "https://contact.example.test/old📞"
NEW_TEL = "tel:+620000000099"
OLD_ADDRESS = "Jl. Fixture Lama 1"
NEW_ADDRESS = "Jalan Fixture Baru 2"


def html(newline="\n", final=True):
    text = newline.join(
        [
            '<div class="whatsapp-floating">',
            f'  <a href="{OLD_WA}"><span>{OLD_PHONE} ({OLD_NAME})</span></a>',
            "</div>",
            '<div class="tlp-floating">',
            f'  <a href="{OLD_TEL}"><span>{OLD_PHONE} ({OLD_NAME})</span></a>',
            "</div>",
            f"<address>{OLD_ADDRESS}</address>",
        ]
    )
    return text + (newline if final else "")


def client(extra=()):
    values = [NEW_NAME, NEW_PHONE, NEW_WA, NEW_TEL, *extra]
    return "|".join(values) + "\n"


def contact_nav(multiple=True, nav_class="menu-info-kontak-container"):
    second = (
        '<li id="manager-2" class="menu-item"><a href="https://old.example/umar">✆ 0821 1447 7255 (Umar)</a></li>'
        if multiple
        else ""
    )
    return (
        f'<nav class="{nav_class}" aria-label="Info Kontak"><ul>'
        '<li id="address" class="menu-item"><a href="#">Jl. Kyai Tambak Deres 105 Surabaya</a></li>'
        '<li id="manager-1" data-keep="yes"><a href="https://old.example/anthock">✆ 0821 1447 7155 (Anthock)</a></li>'
        f"{second}</ul></nav>"
    )


class ClientsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write_fixture(self, relative="index.html", content=None, bom=False):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (html() if content is None else content).encode("utf-8")
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
        return path

    def run_cli(self, clients=".clients", dry_run=False, previous=None):
        command = [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--repo-root",
            str(self.root),
            "--clients",
            clients,
            "--summary",
            str(self.root / "summary.json"),
            "--paths-file",
            str(self.root / "paths.bin"),
            "--github-output",
            str(self.root / "output.txt"),
        ]
        if previous is not None:
            command.extend(["--previous-clients", str(previous)])
        if dry_run:
            command.append("--dry-run")
        return subprocess.run(command, text=True, capture_output=True)

    def test_empty_clients_is_noop_and_missing_fails_without_writes(self):
        target = self.write_fixture()
        original = target.read_bytes()
        (self.root / ".clients").write_bytes(b"")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(json.loads((self.root / "summary.json").read_text())["changed_count"], 0)
        self.assertEqual((self.root / "paths.bin").read_bytes(), b"")
        self.assertEqual((self.root / "output.txt").read_text(), "changed=false\n")
        (self.root / ".clients").unlink()
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(target.read_bytes(), original)

    def test_four_field_order_variants(self):
        fields = [NEW_NAME, NEW_PHONE, NEW_WA, NEW_TEL]
        for offset in range(4):
            path = self.root / f"c{offset}"
            path.write_text("|".join(fields[offset:] + fields[:offset]), encoding="utf-8")
            parsed = MODULE.parse_clients(path)
            self.assertEqual((parsed[0].name, parsed[0].phone), (NEW_NAME, NEW_PHONE))

    def test_percent_encoded_whatsapp_marker(self):
        tracked = "https://klik.kubikel.id/%F0%9F%92%AC-anthock-toiletkubikelcoid"
        path = self.root / ".clients"
        path.write_text(client().replace(NEW_WA, tracked), encoding="utf-8")
        self.assertEqual(MODULE.parse_clients(path)[0].whatsapp, tracked)

    def test_derive_routes_preserves_each_displayed_contact(self):
        whatsapp_display = "0812 3456 7890 (Ketut WhatsApp)"
        telephone_display = "62813 7654 3210 (Ketut Telepon)"
        content = (
            f'<a href="https://what.sapp.my.id/legacy-2"><span>{telephone_display}</span></a>'
            f'<a href="https://con.tact.my.id/legacy-2"><span>{whatsapp_display}</span></a>'
            '<div class="whatsapp-floating">'
            f'<a href="https://what.sapp.my.id/legacy"><span>{whatsapp_display}</span></a>'
            "</div>"
            '<div class="tlp-floating">'
            f'<a href="https://con.tact.my.id/legacy"><span>{telephone_display}</span></a>'
            "</div>"
        )
        target = self.write_fixture(content=content)
        (self.root / ".clients").write_text("Ketut | derive-routes\n", encoding="utf-8")

        summary = MODULE.update(self.root, self.root / ".clients", False)
        changed = target.read_text(encoding="utf-8")
        self.assertEqual(summary["changed_count"], 1)
        self.assertIn('href="https://wa.me/6281234567890"', changed)
        self.assertIn('href="tel:+6281376543210"', changed)
        self.assertIn('href="https://wa.me/6281376543210"', changed)
        self.assertIn('href="tel:+6281234567890"', changed)
        self.assertNotIn("what.sapp.my.id", changed)
        self.assertNotIn("con.tact.my.id", changed)
        self.assertIn(whatsapp_display, changed)
        self.assertIn(telephone_display, changed)
        self.assertEqual(MODULE.update(self.root, self.root / ".clients", False)["changed_count"], 0)

    def test_derive_routes_rejects_ambiguous_block_before_write(self):
        target = self.write_fixture(
            content=(
                html()
                .replace(OLD_WA, "https://what.sapp.my.id/legacy")
                .replace(OLD_TEL, "https://con.tact.my.id/legacy")
                .replace(
                    f"<span>{OLD_PHONE} ({OLD_NAME})</span>",
                    f"<span>{OLD_PHONE} ({OLD_NAME})</span><span>0812 3456 7890 (Ketut)</span>",
                    1,
                )
            )
        )
        original = target.read_bytes()
        (self.root / ".clients").write_text("Ketut | derive-routes\n", encoding="utf-8")

        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("one displayed phone/name", result.stderr)
        self.assertEqual(target.read_bytes(), original)

    def test_derive_routes_rejects_explicit_contact_values(self):
        path = self.root / ".clients"
        path.write_text(client(["derive-routes"]), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ClientsError, "cannot include contact values"):
            MODULE.parse_clients(path)

    def test_nested_contact_blocks_are_recognized(self):
        alternate = "0811 1111 1111 (Other Fixture)"
        target = self.write_fixture(
            content=f'<div class="wrapper">{html().replace(f"{OLD_PHONE} ({OLD_NAME})", alternate, 1)}</div>'
        )
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        self.assertEqual(MODULE.update(self.root, self.root / ".clients", False)["changed_count"], 1)
        changed = target.read_text(encoding="utf-8")
        self.assertIn(NEW_WA, changed)
        self.assertNotIn(alternate, changed)

    def test_floating_anchor_text_without_span_is_recognized(self):
        target = self.write_fixture(
            content=(
                f'<div class="sms-floating"><a href="{OLD_WA}">'
                f"{OLD_PHONE} ({OLD_NAME})</a></div>"
                f'<div class="tlp-floating"><a href="{OLD_TEL}">'
                f"{OLD_PHONE} ({OLD_NAME})</a></div>"
            )
        )
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        summary = MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(summary["changed_count"], 1)
        changed = target.read_text(encoding="utf-8")
        self.assertIn(f"{NEW_PHONE} ({NEW_NAME})", changed)
        self.assertIn(NEW_WA, changed)
        self.assertIn(NEW_TEL, changed)

    def test_empty_image_floating_blocks_gain_contact_links(self):
        target = self.write_fixture(
            content=(
                '<div class="sms-floating"><img src="wa.png" alt=""></div>'
                '<div class="tlp-floating"><img src="tel.png" alt=""></div>'
            )
        )
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        self.assertEqual(
            MODULE.update(self.root, self.root / ".clients", False)["changed_count"], 1
        )
        changed = target.read_text(encoding="utf-8")
        self.assertIn(f'href="{NEW_WA}"', changed)
        self.assertIn(f'href="{NEW_TEL}"', changed)
        self.assertEqual(changed.count(f"{NEW_PHONE} ({NEW_NAME})"), 2)

    def test_duplicate_floating_blocks_with_displays_are_all_rewritten(self):
        other_phone = "0811 1111 1111"
        other_name = "Other Fixture"
        other_wa = "https://example.test/other-wa"
        other_tel = "tel:+621111111111"
        target = self.write_fixture(
            content=(
                html()
                + html()
                .replace(OLD_PHONE, other_phone)
                .replace(OLD_NAME, other_name)
                .replace(OLD_WA, other_wa)
                .replace(OLD_TEL, other_tel)
            )
        )
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        summary = MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(summary["changed_count"], 1)
        changed = target.read_text(encoding="utf-8")
        for old in (
            OLD_PHONE,
            OLD_NAME,
            OLD_WA,
            OLD_TEL,
            other_phone,
            other_name,
            other_wa,
            other_tel,
        ):
            self.assertNotIn(old, changed)
        self.assertEqual(changed.count(NEW_WA), 2)
        self.assertEqual(changed.count(NEW_TEL), 2)

    def test_navigation_contact_fallback_rewrites_first_and_removes_duplicates(self):
        target = self.write_fixture(content=contact_nav())
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        before = target.read_bytes()
        summary = MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(summary["changed_count"], 1)
        changed = target.read_text(encoding="utf-8")
        self.assertIn('href="https://wa.me/620000000099"', changed)
        self.assertIn(f"{NEW_PHONE} ({NEW_NAME})", changed)
        self.assertIn("Jl. Kyai Tambak Deres 105 Surabaya", changed)
        self.assertNotIn("0821 1447 7255", changed)
        self.assertIn('data-keep="yes"', changed)
        after_first = target.read_bytes()
        MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(target.read_bytes(), after_first)
        self.assertNotEqual(before, target.read_bytes())

    def test_navigation_fallback_rejects_ambiguity_before_write(self):
        cases = [
            contact_nav().replace(
                'href="https://old.example/anthock">',
                'href="https://old.example/anthock"><a href="https://other.example">',
            ),
            contact_nav() + contact_nav(),
        ]
        for index, content in enumerate(cases):
            target = self.write_fixture(f"ambiguous-{index}.html", content)
            original = target.read_bytes()
            (self.root / ".clients").write_text(client(), encoding="utf-8")
            with self.assertRaises(MODULE.ClientsError):
                MODULE.update(self.root, self.root / ".clients", False)
            self.assertEqual(target.read_bytes(), original)

    def test_navigation_fallback_address_client_is_rejected_and_unmatched_nav_is_noop(self):
        target = self.write_fixture(content=contact_nav(nav_class="other-menu"))
        original = target.read_bytes()
        (self.root / ".clients").write_text(client([OLD_ADDRESS]), encoding="utf-8")
        self.assertEqual(MODULE.update(self.root, self.root / ".clients", False)["changed_count"], 0)
        self.assertEqual(target.read_bytes(), original)

        target = self.write_fixture("address.html", contact_nav())
        original = target.read_bytes()
        with self.assertRaises(MODULE.ClientsError):
            MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(target.read_bytes(), original)

    def test_five_and_six_field_records_and_category_filter(self):
        cases = [
            (OLD_ADDRESS, False, True),
            ("roof,-draft", True, False),
            ("roof:jakarta,-bogor;wall:depok", True, True),
        ]
        for index, (extra, has_filter, has_address) in enumerate(cases):
            path = self.root / f"p{index}"
            suffix = [extra]
            if has_address and has_filter:
                suffix.append(NEW_ADDRESS)
            path.write_text(client(suffix), encoding="utf-8")
            parsed = MODULE.parse_clients(path)[0]
            self.assertEqual(parsed.filter is not None, has_filter)
            self.assertEqual(parsed.address is not None, has_address)

    def test_malformed_and_ambiguous_records_are_sanitized(self):
        secret = "Private Fixture"
        path = self.root / ".clients"
        path.write_text(
            "|".join([secret, NEW_PHONE, NEW_WA, NEW_TEL, "roof:"]) + "\n",
            encoding="utf-8",
        )
        self.write_fixture()
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertIn("row 1", result.stderr)

    def test_markup_update_address_and_absent_address(self):
        first = self.write_fixture("first.html")
        (self.root / ".clients").write_text(client([NEW_ADDRESS]), encoding="utf-8")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = first.read_text(encoding="utf-8")
        for value in (NEW_PHONE, NEW_NAME, NEW_WA, NEW_TEL, NEW_ADDRESS):
            self.assertIn(value, changed)
        self.assertNotIn(OLD_ADDRESS, changed)

        second_root = self.root / "without-address"
        second_root.mkdir()
        second = second_root / "index.html"
        second.write_text(html(), encoding="utf-8")
        (second_root / ".clients").write_text(client(), encoding="utf-8")
        summary = MODULE.update(second_root, second_root / ".clients", False)
        self.assertEqual(summary["changed_count"], 1)
        self.assertIn(OLD_ADDRESS, second.read_text(encoding="utf-8"))

    def test_filter_selects_category_city_and_default_remainder(self):
        selected = self.write_fixture("roof/jakarta/index.html")
        default = self.write_fixture("wall/surabaya/index.html")
        selected_values = "|".join(
            ["Filtered Fixture", "0877 7777 7777", "https://wa.me/620000000077", "tel:+620000000077", "roof:jakarta"]
        )
        (self.root / ".clients").write_text(selected_values + "\n" + client(), encoding="utf-8")
        summary = MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(summary["changed_count"], 2)
        self.assertIn("Filtered Fixture", selected.read_text(encoding="utf-8"))
        self.assertIn(NEW_NAME, default.read_text(encoding="utf-8"))

    def test_filter_matches_complete_relative_filename_case_insensitively(self):
        selected = self.write_fixture("pages/PORTABLE.HTML")
        other = self.write_fixture("pages/not-a-match.html")
        values = "|".join(
            ["Filename Fixture", NEW_PHONE, NEW_WA, NEW_TEL, "portable.html"]
        )
        (self.root / ".clients").write_text(values + "\n", encoding="utf-8")
        summary = MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(summary["changed_count"], 1)
        self.assertIn("Filename Fixture", selected.read_text(encoding="utf-8"))
        self.assertIn(OLD_NAME, other.read_text(encoding="utf-8"))

    def test_basename_filter_ignores_directory_only_match(self):
        selected = self.write_fixture("pages/toilet-PORTABEL-jakarta.html")
        directory_only = self.write_fixture("portable/category/index.html")
        values = "|".join(
            ["Filename Fixture", NEW_PHONE, NEW_WA, NEW_TEL, "basename:portable,portabel"]
        )
        (self.root / ".clients").write_text(values + "\n", encoding="utf-8")
        summary = MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(summary["changed_count"], 1)
        self.assertIn("Filename Fixture", selected.read_text(encoding="utf-8"))
        self.assertIn(OLD_NAME, directory_only.read_text(encoding="utf-8"))

    def test_page_filter_includes_matching_basename_and_directory_index(self):
        basename = self.write_fixture("pages/toilet-PORTABEL-jakarta.html")
        directory_index = self.write_fixture("products/portable/index.html")
        nested_index = self.write_fixture("products/portable/cities/index.html")
        directory_non_index = self.write_fixture("products/portable/about.html")
        unrelated = self.write_fixture("products/cubicle/index.html")
        values = "|".join(
            ["Filename Fixture", NEW_PHONE, NEW_WA, NEW_TEL, "page:portable,portabel"]
        )
        (self.root / ".clients").write_text(values + "\n", encoding="utf-8")
        summary = MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(summary["changed_count"], 3)
        for selected in (basename, directory_index, nested_index):
            self.assertIn("Filename Fixture", selected.read_text(encoding="utf-8"))
        for protected in (directory_non_index, unrelated):
            self.assertIn(OLD_NAME, protected.read_text(encoding="utf-8"))

    def test_filter_only_expansion_processes_directory_index(self):
        basename = self.write_fixture("pages/toilet-portable-kupang.html")
        directory_index = self.write_fixture("portable/index.html")
        directory_non_index = self.write_fixture("portable/about.html")
        unrelated = self.write_fixture("cubicle/index.html")
        previous = self.root / "previous.clients"
        previous.write_text(
            "|".join(
                [
                    "Filename Fixture",
                    NEW_PHONE,
                    NEW_WA,
                    NEW_TEL,
                    "basename:portable,portabel",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / ".clients").write_text(
            "|".join(
                [
                    "Filename Fixture",
                    NEW_PHONE,
                    NEW_WA,
                    NEW_TEL,
                    "page:portable,portabel",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = self.run_cli(previous=previous)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Filename Fixture", basename.read_text(encoding="utf-8"))
        self.assertIn("Filename Fixture", directory_index.read_text(encoding="utf-8"))
        self.assertIn(OLD_NAME, directory_non_index.read_text(encoding="utf-8"))
        self.assertIn(OLD_NAME, unrelated.read_text(encoding="utf-8"))
        self.assertEqual(
            json.loads((self.root / "summary.json").read_text())["changed_count"],
            2,
        )

    def test_overlapping_filename_filters_reject_without_writes(self):
        target = self.write_fixture("portable-portabel.html")
        first = "|".join(["Portable", NEW_PHONE, NEW_WA, NEW_TEL, "portable"])
        second = "|".join(["Portabel", NEW_PHONE, NEW_WA, NEW_TEL, "portabel"])
        (self.root / ".clients").write_text(first + "\n" + second + "\n", encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaises(MODULE.ClientsError):
            MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(target.read_bytes(), before)

    def test_plans_all_files_before_any_write(self):
        first = self.write_fixture("a.html")
        second = self.write_fixture(
            "b.html",
            html().replace(f'<a href="{OLD_TEL}"', '<a href="https://contact.example.test/other📞"')
            + '<div class="tlp-floating"><a href="tel:+621111111111"></a></div>',
        )
        original = first.read_bytes()
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        with self.assertRaises(MODULE.ClientsError):
            MODULE.update(self.root, self.root / ".clients", False)
        self.assertEqual(first.read_bytes(), original)
        self.assertIn(OLD_PHONE, second.read_text(encoding="utf-8"))

    def test_bom_newlines_final_newline_and_mode_are_preserved(self):
        modes = {}
        for index, (bom, newline, final) in enumerate(
            [(False, "\n", True), (True, "\n", False), (False, "\r\n", True)]
        ):
            path = self.write_fixture(f"shape{index}.html", html(newline, final), bom)
            os.chmod(path, 0o640)
            modes[index] = stat.S_IMODE(path.stat().st_mode)
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        MODULE.update(self.root, self.root / ".clients", False)
        for index, (bom, newline, final) in enumerate(
            [(False, "\n", True), (True, "\n", False), (False, "\r\n", True)]
        ):
            path = self.root / f"shape{index}.html"
            raw = path.read_bytes()
            self.assertEqual(raw.startswith(b"\xef\xbb\xbf"), bom)
            body = raw[3:] if bom else raw
            self.assertEqual(b"\r\n" in body, newline == "\r\n")
            self.assertEqual(body.endswith(newline.encode()), final)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), modes[index])

    def test_second_run_is_noop_and_outputs_do_not_leak_values(self):
        self.write_fixture()
        (self.root / ".clients").write_text(client([NEW_ADDRESS]), encoding="utf-8")
        first = self.run_cli()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_cli()
        self.assertEqual(second.returncode, 0, second.stderr)
        summary = json.loads((self.root / "summary.json").read_text())
        self.assertEqual(summary["changed_count"], 0)
        captured = first.stdout + first.stderr + second.stdout + second.stderr + json.dumps(summary)
        for value in (NEW_NAME, NEW_PHONE, NEW_ADDRESS, NEW_WA, NEW_TEL):
            self.assertNotIn(value, captured)

    def test_dry_run_reports_plan_without_write(self):
        target = self.write_fixture()
        before = target.read_bytes()
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        result = self.run_cli(dry_run=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(json.loads((self.root / "summary.json").read_text())["mode"], "dry-run")
        self.assertEqual((self.root / "paths.bin").read_bytes(), b"index.html\0")

    def test_previous_clients_limits_update_to_changed_row(self):
        portable = self.write_fixture("portable.html")
        ordinary = self.write_fixture("ordinary.html")
        previous = self.root / "clients-before"
        previous.write_text(client(), encoding="utf-8")
        (self.root / ".clients").write_text(
            "|".join(
                ["Anthock", NEW_PHONE, NEW_WA, NEW_TEL, "page:portable,portabel"]
            )
            + "\n"
            + client(["-portable,-portabel"]),
            encoding="utf-8",
        )
        result = self.run_cli(previous=previous)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Anthock", portable.read_text(encoding="utf-8"))
        self.assertIn(OLD_NAME, ordinary.read_text(encoding="utf-8"))

    def test_verify_git_exact_scope_and_outside_dirty_poison(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        target = self.write_fixture()
        (self.root / ".clients").write_text(client(), encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.test",
                "commit",
                "-qm",
                "fixture",
            ],
            check=True,
        )
        MODULE.update(self.root, self.root / ".clients", False)
        paths = Path(self.temporary.name + ".paths")
        self.addCleanup(paths.unlink, missing_ok=True)
        paths.write_bytes(b"index.html\0")
        MODULE.verify_git(self.root, paths)
        before = target.read_bytes()
        (self.root / "outside.txt").write_text("dirty", encoding="utf-8")
        with self.assertRaises(MODULE.ClientsError):
            MODULE.verify_git(self.root, paths)
        self.assertEqual(target.read_bytes(), before)

    @unittest.skipIf(
 INSTALLED_CLIENTS.exists(),
        "already executing installed-layout check",
    )
    def test_installed_layout_execution_without_source_search_path(self):
        installed = self.root / "installed" / ".github" / "scripts"
        installed.mkdir(parents=True)
        shutil.copy2(SCRIPT, installed / "update_clients.py")
        shutil.copy2(Path(__file__), installed / "test_update_clients.py")
        workflows = installed.parent / "workflows"
        workflows.mkdir()
        shutil.copy2(
            Path(__file__).parents[1] / "canonical" / "clients.yaml",
            workflows / "clients.yaml",
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = ""
        environment["PYTHONNOUSERSITE"] = "1"
        result = subprocess.run(
            [sys.executable, "-B", str(installed / "test_update_clients.py")],
            cwd=self.root / "installed",
            env=environment,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_workflow_four_case_event_matrix(self):
        base = Path(__file__).parents[1]
        workflow = CLIENTS_FIXTURE.read_text(encoding="utf-8")
        for expression in (
            'INPUT_DRY_RUN: ${{ inputs.dry_run }}',
            '"$GITHUB_EVENT_NAME" == "workflow_dispatch"',
            'git show "${{ github.event.before }}:.clients"',
            '--previous-clients "$RUNNER_TEMP/clients-before"',
            '"$GITHUB_REF_TYPE" != "branch"',
            '"$INPUT_DRY_RUN" == "true"',
            '"$RUNNER_TEMP/clients-summary.json"',
            '"$RUNNER_TEMP/clients-changed-paths"',
        ):
            self.assertIn(expression, workflow)
        self.assertNotIn("env.DRY_RUN", workflow)
        self.assertNotIn("runner.temp", workflow)
        self.assertIn("git --literal-pathspecs add", workflow)
        self.assertNotIn("git add --literal-pathspecs", workflow)
        cases = (
            ("push", "branch", True, False),
            ("workflow_dispatch", "branch", True, True),
            ("workflow_dispatch", "branch", False, False),
            ("workflow_dispatch", "tag", False, True),
        )
        for event, ref_type, dry_run, expected in cases:
            actual = event == "workflow_dispatch" and (ref_type != "branch" or dry_run is not False)
            self.assertEqual(actual, expected, (event, ref_type, dry_run))


if __name__ == "__main__":
    unittest.main()
