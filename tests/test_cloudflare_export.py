from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

try:  # unittest discover puts tests/ on sys.path; a direct module run does not
    from support import bash_command, posix_path
except ModuleNotFoundError:  # pragma: no cover - convenience for direct runs
    from tests.support import bash_command, posix_path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = {
    "_headers",
    "index.html",
    "about.html",
    "experience.html",
    "projects.html",
    "contact.html",
    "404.html",
    "style.css",
    "script.js",
    "apple-touch-icon.png",
    "contact-config.js",
    "cv.html",
    "favicon.ico",
    "icon.svg",
    "robots.txt",
    "sitemap.xml",
    "work/king-of-meal-prep.html",
    "work/recsbot.html",
    "work/taste-platform.html",
    "work/home-server.html",
    "assets/LUCIDE-LICENSE.txt",
    "assets/fonts/OFL-IBM-Plex.txt",
    "assets/fonts/plex-mono-400.woff2",
    "assets/fonts/plex-sans-400.woff2",
    "assets/fonts/plex-sans-600.woff2",
    "assets/king-meal-prep.webp",
    "assets/og-card.png",
    "assets/recsbot-interface.webp",
}


def relative_files(directory: Path) -> set[str]:
    return {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    }


class CloudflareExportTests(unittest.TestCase):
    def test_build_is_exact_and_static(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "site"
            subprocess.run(
                [
                    bash_command(),
                    posix_path(ROOT / "scripts/build-cloudflare-pages.sh"),
                    posix_path(output),
                ],
                check=True,
                cwd=ROOT,
            )

            self.assertEqual(relative_files(output), PUBLIC_FILES)
            self.assertFalse(any(path.is_symlink() for path in output.rglob("*")))
            private_cv_name = "-".join(("cv", "matteo", "mastore")) + ".pdf"
            self.assertFalse((output / private_cv_name).exists())
            self.assertIn(
                'window.PORTFOLIO_CONTACT_ENDPOINT = "/api/contact";',
                (output / "contact-config.js").read_text(encoding="utf-8"),
            )

            headers = (output / "_headers").read_text(encoding="utf-8")
            for required in (
                "Content-Security-Policy:",
                "connect-src 'self'",
                "frame-src https://challenges.cloudflare.com",
                "script-src 'self' 'sha256-",
                "https://challenges.cloudflare.com;",
                "Strict-Transport-Security:",
                "X-Content-Type-Options: nosniff",
                "X-Frame-Options: DENY",
                "Permissions-Policy:",
            ):
                self.assertIn(required, headers)


if __name__ == "__main__":
    unittest.main()
