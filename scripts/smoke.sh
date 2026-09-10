#!/bin/bash
# Smoke the deployed portfolio: HEAD all 5 pages + assets, POST a real contact form,
# verify the resulting DynamoDB row.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
. "$ROOT/.deploy-state.env"
REGION=us-east-1

echo "===> 1. CloudFront (CF_DOMAIN=$CF_DOMAIN)"
for path in / /about.html /experience.html /projects.html /contact.html /style.css /script.js; do
    code=$(curl -sI -o /dev/null -w '%{http_code}' "https://$CF_DOMAIN$path")
    printf '  %-30s %s\n' "$path" "$code"
done

echo
echo "===> 2. POST /contact (sends a real submission)"
RESP=$(curl -sS -X POST "$API_URL" \
  -H "Origin: https://$CF_DOMAIN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Smoke Test\",\"email\":\"smoke-test@example.com\",\"subject\":\"Portfolio rebuild smoke\",\"message\":\"Smoke from migration on $(date -u +%Y-%m-%dT%H:%M:%SZ)\"}")
echo "  response: $RESP"
SID=$(echo "$RESP" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("submissionId",""))')
if [[ -z "$SID" ]]; then
    echo "  ⚠ no submissionId in response"
    exit 1
fi
echo "  submissionId: $SID"

echo
echo "===> 3. DynamoDB lookup"
aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "submissionId = :sid" \
  --expression-attribute-values "{\":sid\":{\"S\":\"$SID\"}}" \
  --region "$REGION" --output json --query 'Items[0].{name:name.S,email:email.S,subject:subject.S,createdAt:createdAt.S,expiresAt:expiresAt.N}'

echo
echo "===> 4. SES status"
aws sesv2 get-email-identity --email-identity "$SES_EMAIL" --region "$REGION" \
  --query '{VerificationStatus:VerificationStatus,SendingEnabled:SendingEnabled}' --output json

echo
echo "smoke complete"
