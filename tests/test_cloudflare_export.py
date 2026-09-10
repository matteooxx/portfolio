from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


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
    "contact-config.js",
    "assets/LUCIDE-LICENSE.txt",
    "assets/king-meal-prep.png",
    "assets/lucide.min.js",
    "assets/recsbot-interface.png",
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
                ["bash", str(ROOT / "scripts/build-cloudflare-pages.sh"), str(output)],
                check=True,
                cwd=ROOT,
            )

            self.assertEqual(relative_files(output), PUBLIC_FILES)
            self.assertFalse(any(path.is_symlink() for path in output.rglob("*")))
            private_cv_name = "-".join(("cv", "matteo", "mastore")) + ".pdf"
            self.assertFalse((output / private_cv_name).exists())
            self.assertIn(
                'window.PORTFOLIO_CONTACT_ENDPOINT = "";',
                (output / "contact-config.js").read_text(encoding="utf-8"),
            )

            headers = (output / "_headers").read_text(encoding="utf-8")
            for required in (
                "Content-Security-Policy:",
                "connect-src 'none'",
                "Strict-Transport-Security:",
                "X-Content-Type-Options: nosniff",
                "X-Frame-Options: DENY",
                "Permissions-Policy:",
            ):
                self.assertIn(required, headers)

    def test_dashboard_bundle_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "bundle"
            subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts/package-cloudflare-pages.sh"),
                    str(output),
                ],
                check=True,
                cwd=ROOT,
            )

            archive = output / "matteo-mastore-portfolio-pages.zip"
            with ZipFile(archive) as bundle:
                self.assertEqual(set(bundle.namelist()), PUBLIC_FILES)

            manifest = output / "SHA256SUMS"
            for line in manifest.read_text(encoding="ascii").splitlines():
                digest, relative = line.split("  ", 1)
                target = output / relative
                self.assertTrue(target.is_file(), relative)
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
