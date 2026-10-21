#!/usr/bin/env python3
"""Relist the CSP script hashes for the inline JSON-LD.

script-src carries no 'unsafe-inline', so each page's inline block is allowed
only by its own sha256. The structured data is per-page, so there is one hash
per indexable page and changing a single byte of any block invalidates that
page's hash: the browser then drops that page's structured data in silence.

tests/test_static_site.py::test_structured_data_matches_the_content_security_policy
fails when they fall out of step. Run this to put them back:

    python3 scripts/refresh-csp-hashes.py

It rewrites only the sha256 tokens inside script-src and leaves every other
directive, and the rest of the file, untouched.
"""

from __future__ import annotations

import base64
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADERS = ROOT / "cloudflare" / "_headers"
BLOCK = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def page_hashes() -> list[str]:
    """Digest every page's inline JSON-LD, in a stable order."""
    digests: list[str] = []
    for path in sorted(ROOT.glob("*.html")) + sorted(ROOT.glob("work/*.html")):
        blocks = BLOCK.findall(path.read_text(encoding="utf-8"))
        if not blocks:
            continue  # 404.html carries no metadata, by design.
        if len(blocks) > 1:
            sys.exit(f"{path.name}: {len(blocks)} blocks, the policy expects one")
        digest = base64.b64encode(
            hashlib.sha256(blocks[0].encode("utf-8")).digest()
        ).decode()
        digests.append(digest)
    return digests


def main() -> int:
    digests = page_hashes()
    if len(set(digests)) != len(digests):
        sys.exit("two pages ship an identical block; refusing to write")

    text = HEADERS.read_text(encoding="utf-8")
    found = re.search(r"script-src ([^;]*)", text)
    if not found:
        sys.exit("no script-src directive in cloudflare/_headers")

    directive = found.group(1)
    if "'unsafe-inline'" in directive:
        sys.exit("script-src has gained 'unsafe-inline'; refusing to write")

    # Keep the token order the policy has always used: 'self', then the
    # hashes, then any host source.
    rest = [
        token
        for token in re.sub(r"'sha256-[A-Za-z0-9+/=]+'", "", directive).split()
        if token != "'self'"
    ]
    rebuilt = " ".join(
        ["'self'"] + [f"'sha256-{digest}'" for digest in digests] + rest
    )
    if rebuilt == directive.strip():
        print(f"already in step: {len(digests)} hashes")
        return 0

    HEADERS.write_text(
        text.replace("script-src " + directive, "script-src " + rebuilt, 1),
        encoding="utf-8",
    )
    print(f"cloudflare/_headers: relisted {len(digests)} hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
