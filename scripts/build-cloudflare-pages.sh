#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUTPUT=${1:-"$ROOT/dist/cloudflare-pages"}

PUBLIC_FILES=(
    index.html
    about.html
    experience.html
    projects.html
    contact.html
    404.html
    style.css
    script.js
    contact-config.js
    assets/LUCIDE-LICENSE.txt
    assets/king-meal-prep.png
    assets/lucide.min.js
    assets/recsbot-interface.png
)

fail() {
    echo "FATAL: $*" >&2
    exit 1
}

[[ ! -e "$OUTPUT" ]] || fail "output already exists: $OUTPUT"
[[ -f "$ROOT/cloudflare/_headers" ]] || fail "missing cloudflare/_headers"
[[ ! -L "$ROOT/cloudflare/_headers" ]] || fail "cloudflare/_headers is a symlink"

grep -Fqx 'window.PORTFOLIO_CONTACT_ENDPOINT = "";' \
    "$ROOT/contact-config.js" ||
    fail "contact-config.js must retain the static mailto fallback"

for relative in "${PUBLIC_FILES[@]}"; do
    source_path="$ROOT/$relative"
    [[ -f "$source_path" ]] || fail "missing public file: $relative"
    [[ ! -L "$source_path" ]] || fail "public file is a symlink: $relative"
done

mkdir -p "$OUTPUT/assets"
for relative in "${PUBLIC_FILES[@]}"; do
    install -m 0644 "$ROOT/$relative" "$OUTPUT/$relative"
done
install -m 0644 "$ROOT/cloudflare/_headers" "$OUTPUT/_headers"

expected=$(mktemp)
actual=$(mktemp)
trap 'rm -f "$expected" "$actual"' EXIT

printf '%s\n' "${PUBLIC_FILES[@]}" _headers | LC_ALL=C sort > "$expected"
find "$OUTPUT" -type f | sed "s|^$OUTPUT/||" | LC_ALL=C sort > "$actual"
diff -u "$expected" "$actual" ||
    fail "Cloudflare output differs from the public allowlist"

if find "$OUTPUT" -type l -print -quit | grep -q .; then
    fail "Cloudflare output contains a symlink"
fi

echo "Cloudflare Pages export ready: $OUTPUT"
echo "Files: $(wc -l < "$actual" | tr -d ' ')"
