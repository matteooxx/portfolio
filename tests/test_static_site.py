from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
import unittest
from datetime import date
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
    "cv.html",
    "work/king-of-meal-prep.html",
    "work/recsbot.html",
    "work/taste-platform.html",
    "work/home-server.html",
    "work/vedetta.html",
    "404.html",
)


def webp_size(path: Path) -> tuple[int, int]:
    """Read the pixel size of a WebP file without Pillow.

    Both encodings are published: photographic previews compress smaller as
    lossy VP8, while a flat interface screenshot is both smaller and sharper
    as lossless VP8L, so the header layout has to be chosen per file.
    """
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise AssertionError(f"{path.name} is not a WebP file")
    fourcc = data[12:16]
    if fourcc == b"VP8 ":
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height
    if fourcc == b"VP8L":
        # One signature byte, then width-1 and height-1 as 14 bits each.
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise AssertionError(f"{path.name} is not a VP8 or VP8L WebP file")


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

    def test_the_not_found_page_is_depth_independent(self) -> None:
        # wrangler.jsonc returns 404.html for every unmatched path, so a
        # relative reference in that one page resolves against the request
        # URL and not the site root: at /work/missing, "style.css" means
        # /work/style.css. A miss at the root hides this, so keep every
        # local reference in 404.html root-relative.
        parser = ReferenceParser()
        parser.feed((ROOT / "404.html").read_text(encoding="utf-8"))
        for reference in parser.references:
            if urlsplit(reference).scheme or reference.startswith("#"):
                continue
            self.assertTrue(
                reference.startswith("/"),
                f"404.html reference {reference} breaks below the site root",
            )
            self.assertTrue(
                (ROOT / reference.lstrip("/")).is_file(),
                f"404.html references missing file {reference}",
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
            # The internship was written as training in sandboxes until the
            # operator confirmed its real scope on 12 October 2026.
            "sandboxed environments",
            "simulated deployment scenarios",
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
            "conferred",
            "conferring",
            "coursework complete",
            "(Hons)",
            "Honours",
            # Named in the programme's public posting, never confirmed here.
            "OpsWorks",
            "QuickSight",
            # The leadership attestation is for a peer team lead, and covers
            # SafeZone alone.
            "managed a five-person",
            "sole architect",
            # The mentor's phrase about ARIA refers to the hosted browser
            # simulation, not to a kiosk that ran.
            "deployed on live infrastructure",
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
        allowed = {
            "king-of-meal-prep",
            "recsbot",
            "taste-platform",
            "portfolio",
            "vedetta",
        }
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
        # The leadership claim is attested, but only as a lead among peers:
        # the caveat travels with it.
        self.assertIn("team lead among peers", projects)

    def test_project_images_have_stable_dimensions(self) -> None:
        for relative in (
            "assets/king-meal-prep.webp",
            "assets/recsbot-interface.webp",
            "assets/vedetta-interface.webp",
        ):
            self.assertEqual(webp_size(ROOT / relative), (1440, 900), relative)

    def test_each_page_is_a_single_document(self) -> None:
        for page_name in PAGES:
            html = (ROOT / page_name).read_text(encoding="utf-8")
            for pattern in (
                r"<!DOCTYPE html>",
                r"<html[\s>]",
                r"<head>",
                r"<body[\s>]",
                r"<main[\s>]",
                r"<h1[\s>]",
                r"<title>",
            ):
                self.assertEqual(
                    len(re.findall(pattern, html, re.IGNORECASE)),
                    1,
                    f"{page_name}: expected exactly one {pattern}",
                )
            ids = re.findall(r'\sid="([^"]+)"', html)
            duplicate_ids = {name for name in ids if ids.count(name) > 1}
            self.assertFalse(duplicate_ids, f"{page_name}: {duplicate_ids}")
            metas = re.findall(r'<meta\s+(?:name|property)="([^"]+)"', html)
            duplicate_metas = {name for name in metas if metas.count(name) > 1}
            self.assertFalse(duplicate_metas, f"{page_name}: {duplicate_metas}")

    def test_canonical_and_open_graph_urls_do_not_redirect(self) -> None:
        # Cloudflare redirects /page.html to /page, so canonical and og:url
        # must use the final clean URL.
        for page_name in PAGES:
            html = (ROOT / page_name).read_text(encoding="utf-8")
            urls = re.findall(
                r'<link rel="canonical" href="([^"]+)"', html
            ) + re.findall(r'<meta property="og:url" content="([^"]+)"', html)
            if page_name == "404.html":
                self.assertEqual(urls, [], "the 404 page has no own URL")
                continue
            slug = "" if page_name == "index.html" else page_name[:-5]
            expected = f"https://matteomastore.com/{slug}"
            self.assertEqual(urls, [expected, expected], page_name)

    def test_open_graph_card_has_the_declared_dimensions(self) -> None:
        with (ROOT / "assets/og-card.png").open("rb") as handle:
            signature = handle.read(24)
        self.assertEqual(signature[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", signature[16:24]), (1200, 630))

    def test_structured_data_matches_the_content_security_policy(self) -> None:
        # script-src has no 'unsafe-inline', so the JSON-LD block is allowed by
        # its hash: the two must stay in step.
        headers = (ROOT / "cloudflare/_headers").read_text(encoding="utf-8")
        allowed = set(re.findall(r"'sha256-([A-Za-z0-9+/=]+)'", headers))
        self.assertTrue(allowed, "no script hash in the policy")

        for page_name in PAGES:
            html = (ROOT / page_name).read_text(encoding="utf-8")
            blocks = re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                html,
                re.DOTALL,
            )
            if page_name == "404.html":
                self.assertEqual(blocks, [], "the 404 page carries no metadata")
                continue
            self.assertEqual(len(blocks), 1, page_name)
            digest = base64.b64encode(
                hashlib.sha256(blocks[0].encode("utf-8")).digest()
            ).decode()
            self.assertIn(digest, allowed, f"{page_name}: unlisted script hash")
            data = json.loads(blocks[0])
            self.assertEqual(data["@context"], "https://schema.org")

    def test_every_page_points_at_real_icon_files(self) -> None:
        # Search engines ignore a data: URI icon, which is why the site showed
        # the generic placeholder in results; the files must exist and be
        # referenced by URL.
        for relative in ("favicon.ico", "icon.svg", "apple-touch-icon.png"):
            self.assertTrue((ROOT / relative).is_file(), relative)

        for page_name in PAGES:
            html = (ROOT / page_name).read_text(encoding="utf-8")
            self.assertNotIn('rel="icon" href="data:', html, page_name)
            for declaration in (
                '<link rel="icon" href="/favicon.ico"',
                '<link rel="icon" href="/icon.svg"',
                '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
            ):
                self.assertIn(declaration, html, f"{page_name}: {declaration}")

        with (ROOT / "favicon.ico").open("rb") as handle:
            header = handle.read(6)
        self.assertEqual(header[:4], bytes((0, 0, 1, 0)), "not an ICO file")
        self.assertGreaterEqual(
            int.from_bytes(header[4:6], "little"), 3, "needs 16, 32 and 48px"
        )

    def test_sitemap_and_robots_cover_the_public_pages(self) -> None:
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        listed = set(re.findall(r"<loc>(.*?)</loc>", sitemap))
        expected = {
            "https://matteomastore.com/"
            + ("" if page == "index.html" else page[:-5])
            for page in PAGES
            if page != "404.html"
        }
        self.assertEqual(listed, expected)

        robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Sitemap: https://matteomastore.com/sitemap.xml", robots)
        self.assertIn("Disallow: /api/", robots)

    def test_every_sitemap_entry_carries_a_plausible_lastmod(self) -> None:
        """A page added without a date tells a crawler nothing has changed.

        Two entries were published with no `lastmod` at all, and five kept a
        date from before their last edit, which is worse than none: it asserts
        the page is older than it is. Equality with the commit date is not
        asserted, because a page and this file change in the same commit.
        """
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        entries = re.findall(r"<url>(.*?)</url>", sitemap, re.S)
        self.assertTrue(entries)
        today = date.today()
        for entry in entries:
            loc = re.search(r"<loc>(.*?)</loc>", entry).group(1)
            stamps = re.findall(r"<lastmod>(.*?)</lastmod>", entry)
            self.assertEqual(len(stamps), 1, f"{loc}: expected one lastmod")
            try:
                stamped = date.fromisoformat(stamps[0])
            except ValueError:  # pragma: no cover - the assertion reports it
                self.fail(f"{loc}: lastmod {stamps[0]!r} is not a date")
            self.assertLessEqual(stamped, today, f"{loc}: lastmod is in the future")

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
