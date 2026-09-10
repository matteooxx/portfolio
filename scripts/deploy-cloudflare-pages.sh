#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PROJECT_NAME=${CLOUDFLARE_PAGES_PROJECT:-matteo-mastore-portfolio}
BRANCH=${CLOUDFLARE_PAGES_BRANCH:-main}
WRANGLER_VERSION=4.123.0

fail() {
    echo "FATAL: $*" >&2
    exit 1
}

[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]$ ]] ||
    fail "invalid Cloudflare Pages project name: $PROJECT_NAME"
command -v node >/dev/null || fail "Node.js is required"
command -v npm >/dev/null || fail "npm is required"
command -v npx >/dev/null || fail "npx is required"
command -v python3 >/dev/null || fail "Python 3 is required"

export WRANGLER_SEND_METRICS=false
WRANGLER=(npx --yes "wrangler@$WRANGLER_VERSION")

if ! "${WRANGLER[@]}" whoami --json >/dev/null 2>&1; then
    fail "Wrangler is not authenticated. The operator must run: npx --yes wrangler@$WRANGLER_VERSION login --use-keyring"
fi

projects=$("${WRANGLER[@]}" pages project list --json)
if ! PROJECT_NAME="$PROJECT_NAME" python3 -c '
import json
import os
import sys

payload = json.load(sys.stdin)
if isinstance(payload, dict):
    payload = payload.get("result", payload.get("projects", []))
names = {
    item.get("name")
    for item in payload
    if isinstance(item, dict) and isinstance(item.get("name"), str)
}
raise SystemExit(0 if os.environ["PROJECT_NAME"] in names else 1)
' <<< "$projects"; then
    fail "Pages project '$PROJECT_NAME' does not exist. Create it first in the Cloudflare dashboard or with 'wrangler pages project create'"
fi

make -C "$ROOT" check

work=$(mktemp -d "${TMPDIR:-/tmp}/portfolio-cloudflare-pages.XXXXXX")
trap 'rm -rf "$work"' EXIT
"$ROOT/scripts/build-cloudflare-pages.sh" "$work/site"

deploy_args=(
    pages deploy "$work/site"
    "--project-name=$PROJECT_NAME"
    "--branch=$BRANCH"
    "--commit-message=Verified static portfolio deployment"
)
if commit=$(git -C "$ROOT" rev-parse --verify HEAD 2>/dev/null); then
    deploy_args+=("--commit-hash=$commit")
fi

"${WRANGLER[@]}" "${deploy_args[@]}"
