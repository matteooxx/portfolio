#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUTPUT=${1:-"$ROOT/dist/cloudflare-pages-ready"}
SITE="$OUTPUT/site"
ARCHIVE="$OUTPUT/matteo-mastore-portfolio-pages.zip"

fail() {
    echo "FATAL: $*" >&2
    exit 1
}

[[ ! -e "$OUTPUT" ]] || fail "output already exists: $OUTPUT"
mkdir -p "$OUTPUT"

"$ROOT/scripts/build-cloudflare-pages.sh" "$SITE"

if commit=$(git -C "$ROOT" rev-parse --verify HEAD 2>/dev/null); then
    printf '%s\n' "$commit" > "$OUTPUT/SOURCE-COMMIT"
else
    printf '%s\n' "unknown (exported tree without Git metadata)" \
        > "$OUTPUT/SOURCE-COMMIT"
fi

python3 - "$OUTPUT" "$SITE" "$ARCHIVE" <<'PY'
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

output = Path(sys.argv[1]).resolve()
site = Path(sys.argv[2]).resolve()
archive = Path(sys.argv[3]).resolve()

site_files = sorted(path for path in site.rglob("*") if path.is_file())
with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
    for path in site_files:
        bundle.write(path, path.relative_to(site).as_posix())

manifest_files = [
    output / "SOURCE-COMMIT",
    archive,
    *site_files,
]
with (output / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as manifest:
    for path in manifest_files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write(f"{digest}  {path.relative_to(output).as_posix()}\n")
PY

echo "Cloudflare Pages handoff bundle ready: $OUTPUT"
echo "Dashboard upload: $ARCHIVE"
