#!/bin/bash
# Optional AWS deployment. Local/NAS operation uses local_server.py and does
# not require this script.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
INFRA="$ROOT/infra"
SRC_DIR="$ROOT"
STATE="$ROOT/.deploy-state.env"

[[ "${ALLOW_CLOUD_DEPLOY:-}" == "1" ]] || {
    echo "FATAL: set ALLOW_CLOUD_DEPLOY=1 after reviewing the cloud changes"
    exit 1
}

REGION="${AWS_REGION:-us-east-1}"
BUCKET="${PORTFOLIO_BUCKET:?set PORTFOLIO_BUCKET to a globally unique bucket name}"
EMAIL="${PORTFOLIO_EMAIL:?set PORTFOLIO_EMAIL to a verified sender/recipient}"
PREFIX="${PORTFOLIO_RESOURCE_PREFIX:-portfolio-site}"
TABLE="${PREFIX}-contact-submissions"
FN="${PREFIX}-contact-handler"
ROLE="${PREFIX}-contact-lambda-role"
API_NAME="${PREFIX}-contact-api"
OAC_NAME="${PREFIX}-oac"
WAF_NAME="${PREFIX}-waf"
DASHBOARD_NAME="${PREFIX}-dashboard"
ALARM_NAME="${PREFIX}-lambda-errors"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "===> account=$ACCOUNT region=$REGION"
[[ "$ACCOUNT" =~ ^[0-9]{12}$ ]] || { echo "FATAL: bad account"; exit 1; }

# State helper
write_state() { local k=$1 v=$2; if grep -q "^$k=" "$STATE" 2>/dev/null; then sed -i.bak "s|^$k=.*|$k=$v|" "$STATE" && rm -f "$STATE.bak"; else echo "$k=$v" >> "$STATE"; fi; }
> "$STATE.tmp"; touch "$STATE"

# 1. S3 bucket
echo "===> 1. S3 bucket"
if aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null; then
    echo "  bucket exists"
else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" --output text --query 'BucketArn'
    aws s3api put-public-access-block --bucket "$BUCKET" \
      --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
      --region "$REGION"
    aws s3api put-bucket-versioning --bucket "$BUCKET" \
      --versioning-configuration Status=Enabled --region "$REGION"
    echo "  bucket created"
fi
write_state BUCKET "$BUCKET"
write_state TABLE "$TABLE"
write_state FUNCTION_NAME "$FN"

# 2. Static asset upload
echo "===> 2. upload static assets"
for f in index.html about.html experience.html projects.html contact.html; do
    aws s3api put-object --bucket "$BUCKET" --key "$f" --body "$SRC_DIR/$f" \
      --content-type "text/html" --region "$REGION" --output text --query 'ETag' >/dev/null
done
aws s3api put-object --bucket "$BUCKET" --key style.css --body "$SRC_DIR/style.css" \
  --content-type "text/css" --region "$REGION" --output text --query 'ETag' >/dev/null
aws s3api put-object --bucket "$BUCKET" --key script.js --body "$SRC_DIR/script.js" \
  --content-type "application/javascript" --region "$REGION" --output text --query 'ETag' >/dev/null
aws s3api put-object --bucket "$BUCKET" --key contact-config.js --body "$SRC_DIR/contact-config.js" \
  --content-type "application/javascript" --region "$REGION" --output text --query 'ETag' >/dev/null
echo "  uploaded 5 html + css/js/config"

# 3. CloudFront OAC
echo "===> 3. CloudFront Origin Access Control"
OAC_ID=$(aws cloudfront list-origin-access-controls --output json \
  --query "OriginAccessControlList.Items[?Name==\`$OAC_NAME\`].Id | [0]" --output text 2>/dev/null || true)
if [[ -z "$OAC_ID" || "$OAC_ID" == "None" ]]; then
    python3 - "$INFRA/oac-config.json" /tmp/oac-config.json "$OAC_NAME" <<'PY'
import json
import sys

source, target, name = sys.argv[1:]
with open(source, encoding="utf-8") as handle:
    config = json.load(handle)
config["Name"] = name
with open(target, "w", encoding="utf-8") as handle:
    json.dump(config, handle)
PY
    OAC_ID=$(aws cloudfront create-origin-access-control \
      --origin-access-control-config file:///tmp/oac-config.json \
      --query 'OriginAccessControl.Id' --output text)
    rm -f /tmp/oac-config.json
    echo "  OAC created: $OAC_ID"
else
    echo "  OAC exists: $OAC_ID"
fi
write_state OAC_ID "$OAC_ID"

# 4. CloudFront distribution
echo "===> 4. CloudFront distribution"
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='Portfolio site'].Id | [0]" --output text 2>/dev/null || true)
if [[ -z "$DIST_ID" || "$DIST_ID" == "None" ]]; then
    # Patch distribution-config.json with the live OAC ID + a fresh CallerReference
    python3 -c "
import json
c = json.load(open('$INFRA/distribution-config.json'))
c['CallerReference'] = '$PREFIX-' + '$(date +%Y%m%d-%H%M%S)'
c['Origins']['Items'][0]['OriginAccessControlId'] = '$OAC_ID'
c['Origins']['Items'][0]['DomainName'] = '$BUCKET.s3.$REGION.amazonaws.com'
json.dump(c, open('/tmp/distcfg.json','w'))
"
    DIST_ID=$(aws cloudfront create-distribution --distribution-config file:///tmp/distcfg.json \
      --query 'Distribution.Id' --output text)
    rm /tmp/distcfg.json
    echo "  distribution created: $DIST_ID"
else
    echo "  distribution exists: $DIST_ID"
fi
write_state DIST_ID "$DIST_ID"
DOMAIN=$(aws cloudfront get-distribution --id "$DIST_ID" --query 'Distribution.DomainName' --output text)
write_state CF_DOMAIN "$DOMAIN"
echo "  domain: $DOMAIN"

# 5. S3 bucket policy (depends on dist ID)
echo "===> 5. S3 bucket policy"
python3 -c "
import json
p = json.load(open('$INFRA/bucket-policy.json'))
p['Statement'][0]['Resource'] = 'arn:aws:s3:::$BUCKET/*'
p['Statement'][0]['Condition']['StringEquals']['AWS:SourceArn'] = 'arn:aws:cloudfront::$ACCOUNT:distribution/$DIST_ID'
json.dump(p, open('/tmp/bucket-policy.json','w'))
"
aws s3api put-bucket-policy --bucket "$BUCKET" --policy file:///tmp/bucket-policy.json --region "$REGION"
rm /tmp/bucket-policy.json
echo "  policy attached"

# 6. DynamoDB
echo "===> 6. DynamoDB table"
if aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" >/dev/null 2>&1; then
    echo "  table exists"
else
    aws dynamodb create-table \
      --table-name "$TABLE" \
      --attribute-definitions AttributeName=submissionId,AttributeType=S AttributeName=timestamp,AttributeType=S \
      --key-schema AttributeName=submissionId,KeyType=HASH AttributeName=timestamp,KeyType=RANGE \
      --billing-mode PAY_PER_REQUEST --region "$REGION" --output text --query 'TableDescription.TableArn'
    aws dynamodb wait table-exists --table-name "$TABLE" --region "$REGION"
    aws dynamodb update-continuous-backups --table-name "$TABLE" \
      --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true --region "$REGION" \
      --output text --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus'
    aws dynamodb update-time-to-live --table-name "$TABLE" \
      --time-to-live-specification "Enabled=true,AttributeName=expiresAt" --region "$REGION" \
      --output text --query 'TimeToLiveSpecification.AttributeName'
    echo "  table created (PITR + TTL on)"
fi

# 7. SES email identity
echo "===> 7. SES email identity ($EMAIL)"
SES_STATUS=$(aws sesv2 get-email-identity --email-identity "$EMAIL" --region "$REGION" \
  --query VerificationStatus --output text 2>/dev/null || echo "MISSING")
if [[ "$SES_STATUS" == "MISSING" ]]; then
    aws sesv2 create-email-identity --email-identity "$EMAIL" --region "$REGION" --output text --query IdentityType
    echo "  ⚠ SES verification email sent to $EMAIL — click the link, then re-run: make smoke"
else
    echo "  identity exists: $SES_STATUS"
fi
write_state SES_EMAIL "$EMAIL"

# 7b. SES template
if aws ses get-template --template-name ContactFormNotification --region "$REGION" >/dev/null 2>&1; then
    echo "  SES template exists"
else
    aws ses create-template --cli-input-json file://"$INFRA/ses-template.json" --region "$REGION"
    echo "  SES template created"
fi

# 8. Lambda role
echo "===> 8. Lambda execution role"
if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
    echo "  role exists"
else
    aws iam create-role --role-name "$ROLE" \
      --assume-role-policy-document file://"$INFRA/lambda-trust-policy.json" \
      --description "Execution role for the portfolio contact handler" --output text --query 'Role.Arn'
    aws iam attach-role-policy --role-name "$ROLE" \
      --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

    # Patch contact-form-permissions.json with current account
    python3 -c "
import json
p = json.load(open('$INFRA/contact-form-permissions.json'))
for s in p['Statement']:
    if 'Resource' in s and isinstance(s['Resource'], str) and ':dynamodb:' in s['Resource']:
        s['Resource'] = 'arn:aws:dynamodb:$REGION:$ACCOUNT:table/$TABLE'
json.dump(p, open('/tmp/contact-form-permissions.json','w'))
"
    aws iam put-role-policy --role-name "$ROLE" --policy-name contact-form-permissions \
      --policy-document file:///tmp/contact-form-permissions.json
    rm /tmp/contact-form-permissions.json
    sleep 12  # IAM eventual consistency
    echo "  role created"
fi
ROLE_ARN=$(aws iam get-role --role-name "$ROLE" --query 'Role.Arn' --output text)
write_state LAMBDA_ROLE_ARN "$ROLE_ARN"

# 9. Lambda function
echo "===> 9. Lambda function"
LAMBDA_DIR="$ROOT/lambda"
(cd "$LAMBDA_DIR" && npm install --omit=dev --no-audit --no-fund --silent 2>&1 | tail -3)
(cd "$LAMBDA_DIR" && rm -f lambda.zip && zip -qr lambda.zip . -x ".*" "node_modules/.cache/*")
if aws lambda get-function --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
    aws lambda update-function-code --function-name "$FN" \
      --zip-file fileb://"$LAMBDA_DIR/lambda.zip" --region "$REGION" \
      --output text --query 'LastUpdateStatus'
    aws lambda wait function-updated --function-name "$FN" --region "$REGION"
    aws lambda update-function-configuration --function-name "$FN" \
      --environment "Variables={TABLE_NAME=$TABLE,SES_TEMPLATE=ContactFormNotification,SES_SENDER=$EMAIL,SES_RECIPIENT=$EMAIL,TTL_DAYS=180,ALLOWED_ORIGINS=https://$DOMAIN}" \
      --region "$REGION" --output text --query 'LastUpdateStatus' >/dev/null
    aws lambda wait function-updated --function-name "$FN" --region "$REGION"
    echo "  lambda code updated"
else
    for i in 1 2 3 4 5 6; do
        if aws lambda create-function \
          --function-name "$FN" --runtime nodejs20.x --role "$ROLE_ARN" \
          --handler index.handler --zip-file fileb://"$LAMBDA_DIR/lambda.zip" \
          --timeout 10 --memory-size 256 \
          --environment "Variables={TABLE_NAME=$TABLE,SES_TEMPLATE=ContactFormNotification,SES_SENDER=$EMAIL,SES_RECIPIENT=$EMAIL,TTL_DAYS=180,ALLOWED_ORIGINS=https://$DOMAIN}" \
          --region "$REGION" --output text --query 'FunctionArn' 2>&1; then
            break
        else
            echo "  attempt $i failed (likely IAM eventual consistency); retrying in 10s..."
            sleep 10
        fi
    done
    aws lambda wait function-active --function-name "$FN" --region "$REGION"
    echo "  lambda created"
fi

# 10. API Gateway HTTP API
echo "===> 10. API Gateway HTTP API"
API_ID=$(aws apigatewayv2 get-apis --region "$REGION" \
  --query "Items[?Name==\`$API_NAME\`].ApiId | [0]" --output text 2>/dev/null || true)
if [[ -z "$API_ID" || "$API_ID" == "None" ]]; then
    API_ID=$(aws apigatewayv2 create-api \
      --name "$API_NAME" --protocol-type HTTP \
      --description "HTTP API for portfolio contact form" \
      --cors-configuration "AllowOrigins=https://$DOMAIN,AllowMethods=POST,OPTIONS,AllowHeaders=Content-Type,MaxAge=300" \
      --region "$REGION" --query ApiId --output text)
    INTEG_ID=$(aws apigatewayv2 create-integration --api-id "$API_ID" \
      --integration-type AWS_PROXY \
      --integration-uri "arn:aws:lambda:$REGION:$ACCOUNT:function:$FN" \
      --integration-method POST --payload-format-version 2.0 \
      --region "$REGION" --query IntegrationId --output text)
    aws apigatewayv2 create-route --api-id "$API_ID" --route-key "POST /contact" \
      --target "integrations/$INTEG_ID" --region "$REGION" --output text --query 'RouteKey'
    aws apigatewayv2 create-stage --api-id "$API_ID" --stage-name prod --auto-deploy \
      --default-route-settings "ThrottlingBurstLimit=10,ThrottlingRateLimit=5" \
      --region "$REGION" --output text --query StageName
    aws lambda add-permission --function-name "$FN" \
      --statement-id apigw-invoke-prod-contact --action lambda:InvokeFunction \
      --principal apigateway.amazonaws.com \
      --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT:$API_ID/*/POST/contact" \
      --region "$REGION" --output text --query Statement
    echo "  API created"
else
    echo "  API exists: $API_ID"
fi
write_state API_ID "$API_ID"
API_URL="https://$API_ID.execute-api.$REGION.amazonaws.com/prod/contact"
write_state API_URL "$API_URL"

# 11. Upload environment-specific contact configuration without mutating source.
echo "===> 11. upload contact endpoint configuration"
printf 'window.PORTFOLIO_CONTACT_ENDPOINT = "%s";\n' "$API_URL" > /tmp/contact-config.js
aws s3api put-object --bucket "$BUCKET" --key contact-config.js --body /tmp/contact-config.js \
  --content-type "application/javascript" --region "$REGION" --output text --query 'ETag' >/dev/null
rm -f /tmp/contact-config.js
echo "  contact-config.js → $API_URL"

# 12. WAF on CloudFront
echo "===> 12. WAF"
WAF_ID=$(aws wafv2 list-web-acls --scope CLOUDFRONT --region "$REGION" \
  --query "WebACLs[?Name==\`$WAF_NAME\`].Id | [0]" --output text 2>/dev/null || true)
if [[ -z "$WAF_ID" || "$WAF_ID" == "None" ]]; then
    WAF_OUT=$(aws wafv2 create-web-acl \
      --name "$WAF_NAME" --scope CLOUDFRONT --region "$REGION" \
      --default-action 'Allow={}' \
      --description "Rate limiting for the portfolio distribution" \
      --visibility-config "SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=$WAF_NAME" \
      --rules file://"$INFRA/waf-rules.json" \
      --output json)
    WAF_ID=$(echo "$WAF_OUT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["Summary"]["Id"])')
    WAF_ARN=$(echo "$WAF_OUT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["Summary"]["ARN"])')
    echo "  WAF created: $WAF_ID"

    # Attach to CloudFront
    aws cloudfront get-distribution-config --id "$DIST_ID" --output json > /tmp/dist-current.json
    ETAG=$(python3 -c "import json;print(json.load(open('/tmp/dist-current.json'))['ETag'])")
    python3 -c "
import json
d = json.load(open('/tmp/dist-current.json'))
d['DistributionConfig']['WebACLId'] = '$WAF_ARN'
json.dump(d['DistributionConfig'], open('/tmp/dist-update.json','w'))
"
    aws cloudfront update-distribution --id "$DIST_ID" --if-match "$ETAG" \
      --distribution-config file:///tmp/dist-update.json \
      --output text --query 'Distribution.Status' >/dev/null
    rm /tmp/dist-current.json /tmp/dist-update.json
    echo "  WAF attached to CloudFront"
else
    echo "  WAF exists: $WAF_ID"
fi
write_state WAF_ID "$WAF_ID"

# 13. CloudWatch alarm + dashboard
echo "===> 13. CloudWatch alarm + dashboard"
aws cloudwatch put-metric-alarm --alarm-name "$ALARM_NAME" \
  --alarm-description "Alarm when the portfolio contact Lambda emits an error" \
  --namespace AWS/Lambda --metric-name Errors --statistic Sum \
  --period 300 --evaluation-periods 1 --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --dimensions "Name=FunctionName,Value=$FN" --treat-missing-data notBreaching \
  --region "$REGION" >/dev/null
python3 - "$INFRA/dashboard-body.json" /tmp/dashboard-body.json "$FN" <<'PY'
import json
import sys

source, target, function_name = sys.argv[1:]
with open(source, encoding="utf-8") as handle:
    body = json.load(handle)
for widget in body.get("widgets", []):
    for metric in widget.get("properties", {}).get("metrics", []):
        metric[:] = [function_name if value == "${FUNCTION_NAME}" else value for value in metric]
with open(target, "w", encoding="utf-8") as handle:
    json.dump(body, handle)
PY
aws cloudwatch put-dashboard --dashboard-name "$DASHBOARD_NAME" \
  --dashboard-body file:///tmp/dashboard-body.json --region "$REGION" >/dev/null
rm -f /tmp/dashboard-body.json
echo "  alarm + dashboard configured"

# 14. CloudFront invalidation
echo "===> 14. CloudFront wait + invalidate"
aws cloudfront wait distribution-deployed --id "$DIST_ID"
INV=$(aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" \
  --query 'Invalidation.Id' --output text)
aws cloudfront wait invalidation-completed --distribution-id "$DIST_ID" --id "$INV"
echo "  invalidation complete"

echo
echo "============================================================"
echo " ✓ DEPLOY COMPLETE"
echo "============================================================"
echo "  bucket:         $BUCKET"
echo "  CloudFront:     https://$DOMAIN/"
echo "  API endpoint:   $API_URL"
echo "  Lambda:         $FN"
echo "  Distribution:   $DIST_ID"
echo "  WAF:            $WAF_ID"
echo "  Dashboard:      $DASHBOARD_NAME"
echo "------------------------------------------------------------"
echo "  IMPORTANT: SES is in sandbox until you click the verification"
echo "  link for $EMAIL — until then, the contact"
echo "  form's email send will fail (writes to DynamoDB still work)."
echo "============================================================"
