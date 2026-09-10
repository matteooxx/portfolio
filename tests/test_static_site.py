from __future__ import annotations

import re
import struct
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    "index.html",
    "about.html",
    "experience.html",
    "projects.html",
    "contact.html",
    "404.html",
)


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        for key in ("href", "src"):
            value = values.get(key)
            if value:
                self.references.append(value)
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


class StaticSiteTests(unittest.TestCase):
    def test_local_references_exist(self) -> None:
        for page_name in PAGES:
            parser = ReferenceParser()
            parser.feed((ROOT / page_name).read_text(encoding="utf-8"))
            self.assertTrue("".join(parser.title_parts).strip(), page_name)

            for reference in parser.references:
                parsed = urlsplit(reference)
                if parsed.scheme or reference.startswith(("#", "/")):
                    continue
                target = ROOT / parsed.path
                self.assertTrue(
                    target.is_file(),
                    f"{page_name} references missing file {parsed.path}",
                )

    def test_stale_public_claims_are_absent(self) -> None:
        text = "\n".join(
            (ROOT / page).read_text(encoding="utf-8") for page in PAGES
        )
        stale = (
            "AWS Support Engineer Internship. Passionate",
            "tag-current",
            "CLF-C02 - Preparing",
            "AIF-C01 - Preparing",
            "fully serverless portfolio hosted on AWS",
            "working contact form with spam protection",
        )
        for phrase in stale:
            self.assertNotIn(phrase, text)

    def test_corrected_claims_stay_corrected(self) -> None:
        text = "\n".join(
            (ROOT / page).read_text(encoding="utf-8") for page in PAGES
        )
        corrected = (
            "OpenAI",
            "ArgoCD",
            "Led infrastructure and observability",
            "Final-year",
            "expected October 2026",
            "(Hons)",
            "Honours",
        )
        for phrase in corrected:
            self.assertNotIn(phrase, text)

    def test_unconfirmed_tools_and_untaken_modules_are_absent(self) -> None:
        text = "\n".join(
            (ROOT / page).read_text(encoding="utf-8") for page in PAGES
        )
        unconfirmed = (
            "Nmap",
            "Scrapy",
            "boto3",
            "Programmable Networks",
            "Data Centre Environment",
        )
        for phrase in unconfirmed:
            self.assertNotIn(phrase, text)

    def test_source_links_point_only_to_public_personal_repositories(
        self,
    ) -> None:
        allowed = {"king-of-meal-prep", "recsbot", "taste-platform", "portfolio"}
        for page_name in PAGES:
            parser = ReferenceParser()
            parser.feed((ROOT / page_name).read_text(encoding="utf-8"))
            for reference in parser.references:
                parsed = urlsplit(reference)
                if parsed.netloc != "github.com":
                    continue
                parts = [part for part in parsed.path.split("/") if part]
                self.assertEqual(parts[:1], ["matteooxx"], reference)
                if len(parts) > 1:
                    self.assertIn(parts[1], allowed, f"{page_name}: {reference}")

    def test_group_and_safezone_boundaries_are_visible(self) -> None:
        projects = (ROOT / "projects.html").read_text(encoding="utf-8")
        self.assertIn("Five-person internship project", projects)
        self.assertIn("Six-person group project", projects)
        self.assertIn("Group architecture concept", projects)
        self.assertIn("SafeZone is presented only through a high-level", projects)
        self.assertNotIn("safezone/", projects.casefold())

    def test_project_images_have_stable_dimensions(self) -> None:
        for relative in (
            "assets/king-meal-prep.png",
            "assets/recsbot-interface.png",
        ):
            with (ROOT / relative).open("rb") as handle:
                signature = handle.read(24)
            self.assertEqual(signature[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", signature[16:24])
            self.assertEqual((width, height), (1440, 900))

    def test_private_phone_and_cv_are_not_published(self) -> None:
        html = "\n".join(
            (ROOT / page).read_text(encoding="utf-8") for page in PAGES
        )
        public_cv_name = "-".join(("cv", "matteo", "mastore")) + ".pdf"

        self.assertNotIn("tel:", html.casefold())
        self.assertNotIn("download cv", html.casefold())
        self.assertNotIn(public_cv_name, html.casefold())
        self.assertFalse((ROOT / public_cv_name).exists())
        self.assertIsNone(re.search(r"\+\d[\d\s().-]{7,}\d", html))


if __name__ == "__main__":
    unittest.main()
