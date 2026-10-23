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


def served_file(reference: str) -> Path | None:
    """Map a served URL back to the file Cloudflare answers it with.

    wrangler.jsonc sets html_handling to auto-trailing-slash, so the live site
    serves /about from about.html and / from index.html. Looking for a file
    literally named "about" would let every typo in a clean URL through.
    """
    path = urlsplit(reference).path.lstrip("/")
    if not path:
        return ROOT / "index.html"
    direct = ROOT / path
    if direct.is_file():
        return direct
    extended = ROOT / f"{path}.html"
    if extended.is_file():
        return extended
    return None


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.ids: set[str] = set()
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
        element_id = values.get("id")
        if element_id:
            self.ids.add(element_id)
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
                if parsed.scheme:
                    continue
                if not parsed.path:
                    # A same-page anchor: the target id has to exist.
                    self.assertIn(
                        parsed.fragment,
                        parser.ids,
                        f"{page_name} links to missing anchor #{parsed.fragment}",
                    )
                    continue
                self.assertIsNotNone(
                    served_file(reference),
                    f"{page_name} references missing target {reference}",
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
            self.assertIsNotNone(
                served_file(reference),
                f"404.html references missing target {reference}",
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
            # The secondary-school diploma grade came off the site on
            # 23 October 2026, at the operator's request. The school, the
            # qualification and the dates stay; the mark does not.
            "90/100",
            "final grade",
            # He lives in Italy and targets the Irish market. The site may
            # say he is moving to Ireland, studied there and needs no work
            # permit there; it may never say he is based there. That is the
            # one claim here a recruiter disproves on the first call.
            "based in Ireland",
            "Based in Ireland",
            "based in Dublin",
            "Based in Dublin",
            # The operator's own estimate, never confirmed by the employer,
            # retired from the site on 20 October 2026.
            "30%",
            "Reduced downtime",
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

    def test_internal_links_use_the_clean_url(self) -> None:
        # html_handling is auto-trailing-slash, so Cloudflare redirects
        # /about.html to /about. A .html href therefore spends a round trip
        # before the next page starts loading, and hands a crawler a redirect
        # where the canonical URL was meant to be. 180 of them shipped once.
        for page_name in PAGES:
            parser = ReferenceParser()
            parser.feed((ROOT / page_name).read_text(encoding="utf-8"))
            for reference in parser.references:
                parsed = urlsplit(reference)
                if parsed.scheme:
                    continue
                self.assertFalse(
                    parsed.path.endswith(".html"),
                    f"{page_name} links to {reference}, not its clean URL",
                )

    def test_bundled_fonts_are_distinct_and_declared(self) -> None:
        # plex-sans-600.woff2 was once a byte-identical copy of the 400 file
        # declared at font-weight: 600. Declaring a weight promises the face
        # exists, so the browser switched off bold synthesis and every
        # heading, <strong> and button rendered at Regular on all 12 pages.
        # Two declared weights may never share one file again.
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        faces = re.findall(r"@font-face\s*\{(.*?)\}", css, re.DOTALL)
        self.assertTrue(faces, "no @font-face block found")

        declared: dict[tuple[str, str], Path] = {}
        for block in faces:
            source = re.search(r'src:\s*url\("([^"]+)"\)', block)
            weight = re.search(r"font-weight:\s*(\d+)", block)
            family = re.search(r'font-family:\s*"([^"]+)"', block)
            self.assertIsNotNone(source, f"@font-face with no src: {block[:60]}")
            self.assertIsNotNone(weight, f"@font-face with no weight: {block[:60]}")
            self.assertIsNotNone(family, f"@font-face with no family: {block[:60]}")
            target = ROOT / source.group(1)
            self.assertTrue(target.is_file(), f"missing font file {source.group(1)}")
            key = (family.group(1), weight.group(1))
            self.assertNotIn(key, declared, f"{key} declared twice")
            declared[key] = target

        seen: dict[str, str] = {}
        for path in sorted((ROOT / "assets/fonts").glob("*.woff2")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertNotIn(
                digest,
                seen,
                f"{path.name} is byte-identical to {seen.get(digest)}",
            )
            seen[digest] = path.name

        self.assertEqual(
            len({path.resolve() for path in declared.values()}),
            len(declared),
            "two declared weights resolve to the same file",
        )

    def test_the_project_count_and_filters_match_the_markup(self) -> None:
        # The page shipped "9 projects" over 10 cards, on the one page that
        # states no metric is invented, and script.js only corrects the label
        # after the first filter click. Four cards also carried an
        # "infrastructure" category that no button could select.
        html = (ROOT / "projects.html").read_text(encoding="utf-8")
        cards = re.findall(r'data-project-card[^>]*data-category="([^"]*)"', html)
        self.assertTrue(cards, "no project cards found")

        label = re.search(r'id="projectCount"[^>]*>([^<]+)<', html)
        self.assertIsNotNone(label, "no projectCount label")
        self.assertEqual(
            label.group(1).strip(),
            f"{len(cards)} projects",
            "the pre-script label disagrees with the number of cards",
        )

        buttons = set(re.findall(r'data-project-filter="([^"]+)"', html))
        tokens = {token for card in cards for token in card.split()}
        self.assertFalse(
            tokens - buttons,
            f"card categories no button can select: {sorted(tokens - buttons)}",
        )
        for button in buttons - {"all"}:
            self.assertTrue(
                any(button in card.split() for card in cards),
                f"filter {button} selects nothing",
            )

    def test_every_page_is_well_formed(self) -> None:
        # test_each_page_is_a_single_document counts elements with regexes and
        # html.parser never raises, so an unclosed <div> shipped silently.
        # This is nesting well-formedness, not W3C spec conformance: no
        # validator is available without Java or a new dependency.
        void = {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "source", "track", "wbr",
        }

        class NestingParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.stack: list[str] = []
                self.problems: list[str] = []

            def handle_starttag(self, tag, attrs) -> None:
                if tag not in void:
                    self.stack.append(tag)

            def handle_endtag(self, tag) -> None:
                if tag in void:
                    return
                if not self.stack:
                    self.problems.append(f"stray </{tag}>")
                elif self.stack[-1] != tag:
                    self.problems.append(f"</{tag}> closes <{self.stack[-1]}>")
                    if tag in self.stack:
                        while self.stack and self.stack.pop() != tag:
                            pass
                else:
                    self.stack.pop()

        for page_name in PAGES:
            parser = NestingParser()
            parser.feed((ROOT / page_name).read_text(encoding="utf-8"))
            self.assertEqual(parser.problems, [], page_name)
            self.assertEqual(
                parser.stack, [], f"{page_name} leaves {parser.stack} unclosed"
            )

    def test_structured_data_is_valid(self) -> None:
        # The JSON-LD went from one shared block to a distinct block per page,
        # so a typo in a type or a dangling @id now breaks one page only and
        # silently drops that page's entity. The CSP hash test proves the
        # bytes match the policy; this proves the data means something.
        allowed_types = {
            "AboutPage", "BreadcrumbList", "CollectionPage",
            "CollegeOrUniversity", "ContactPage", "Country", "CreativeWork",
            "EducationalOccupationalCredential", "ItemList", "Language",
            "ListItem", "Organization", "Person", "Place", "ProfilePage",
            "SoftwareSourceCode", "TechArticle", "WebPage", "WebSite",
        }
        block_pattern = re.compile(
            r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
        )

        def walk(node, types, refs, defined):
            if isinstance(node, dict):
                kind = node.get("@type")
                for value in kind if isinstance(kind, list) else [kind]:
                    if value is not None:
                        types.add(value)
                identifier = node.get("@id")
                if identifier and kind is not None:
                    defined.add(identifier)
                elif identifier:
                    refs.add(identifier)
                for key, value in node.items():
                    if key not in ("@type", "@id", "@context"):
                        self.assertNotIn(value, ("", []), f"empty value for {key}")
                    walk(value, types, refs, defined)
            elif isinstance(node, list):
                for value in node:
                    walk(value, types, refs, defined)

        for page_name in PAGES:
            html = (ROOT / page_name).read_text(encoding="utf-8")
            blocks = block_pattern.findall(html)
            if page_name == "404.html":
                self.assertEqual(blocks, [], "the 404 page carries no metadata")
                continue
            self.assertEqual(len(blocks), 1, page_name)

            data = json.loads(blocks[0])
            self.assertEqual(data["@context"], "https://schema.org")

            types, refs, defined = set(), set(), set()
            walk(data, types, refs, defined)

            self.assertFalse(
                types - allowed_types,
                f"{page_name} uses unknown types {sorted(types - allowed_types)}",
            )
            self.assertFalse(
                refs - defined,
                f"{page_name} has dangling @id {sorted(refs - defined)}",
            )

            for node in data.get("@graph", []):
                if node.get("@type") == "BreadcrumbList":
                    positions = [
                        item["position"] for item in node["itemListElement"]
                    ]
                    self.assertEqual(
                        positions,
                        list(range(1, len(positions) + 1)),
                        f"{page_name} breadcrumb positions are not 1..n",
                    )
                if node.get("@type") == "CollectionPage":
                    listing = node.get("mainEntity", {})
                    if listing.get("@type") == "ItemList":
                        self.assertEqual(
                            listing["numberOfItems"],
                            len(listing["itemListElement"]),
                            f"{page_name} numberOfItems disagrees with the list",
                        )

    def test_published_assets_stay_within_budget(self) -> None:
        # Nothing performance-related runs in CI: the browser skills are all
        # interactive and human-started. These ceilings are the October 2026
        # sizes with roughly a quarter of headroom, so an asset that balloons
        # fails the build. Raise a number here deliberately; do not delete it.
        budget = {
            "style.css": 36_000,
            "script.js": 14_000,
            "assets/og-card.png": 20_000,
            "assets/king-meal-prep.webp": 34_000,
            "assets/recsbot-interface.webp": 30_000,
            "assets/vedetta-interface.webp": 28_000,
            "assets/fonts/plex-sans-400.woff2": 36_000,
            "assets/fonts/plex-mono-400.woff2": 10_000,
        }
        for name, ceiling in budget.items():
            size = (ROOT / name).stat().st_size
            self.assertLessEqual(
                size, ceiling, f"{name} is {size} bytes, over its {ceiling} budget"
            )

    def test_the_page_lists_agree_with_each_other(self) -> None:
        # The publishable file list is written out four times: PUBLIC_FILES in
        # the build script, its mirror in test_cloudflare_export, PAGES here,
        # and sitemap.xml. A page added to three of the four fails silently -
        # missing from the deploy or from the sitemap, with green tests.
        try:
            from test_cloudflare_export import PUBLIC_FILES as mirrored
        except ModuleNotFoundError:  # pragma: no cover - direct runs
            from tests.test_cloudflare_export import PUBLIC_FILES as mirrored

        script = (ROOT / "scripts/build-cloudflare-pages.sh").read_text(
            encoding="utf-8"
        )
        block = re.search(r"PUBLIC_FILES=\((.*?)\n\)", script, re.DOTALL)
        self.assertIsNotNone(block, "no PUBLIC_FILES array in the build script")
        allowlisted = {
            line.strip()
            for line in block.group(1).splitlines()
            if line.strip() and not line.strip().startswith("#")
        }

        # _headers is not in the array: the script installs it from
        # cloudflare/_headers to the output root and appends the bare name to
        # the manifest it diffs the build against, so add it here too.
        self.assertEqual(
            allowlisted | {"_headers"},
            set(mirrored),
            "the build allowlist and its test mirror have drifted",
        )
        for page_name in PAGES:
            self.assertIn(
                page_name, allowlisted, f"{page_name} would not be deployed"
            )

        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        listed = {
            served_file(url.removeprefix("https://matteomastore.com"))
            for url in re.findall(r"<loc>([^<]+)</loc>", sitemap)
        }
        self.assertEqual(
            listed,
            {ROOT / page for page in PAGES if page != "404.html"},
            "sitemap.xml and the indexable page list have drifted",
        )


if __name__ == "__main__":
    unittest.main()
