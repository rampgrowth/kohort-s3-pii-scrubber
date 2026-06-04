#!/usr/bin/env bash
# Example: create an S3 Batch Operations job that invokes the scrubber Lambda.
# Requires: AWS CLI, jq (optional). Adjust variables before running.
set -euo pipefail

AWS_REGION="${AWS_REGION:-eu-west-1}"
ACCOUNT_ID="${ACCOUNT_ID:?set ACCOUNT_ID}"
LAMBDA_ARN="${LAMBDA_ARN:?set LAMBDA_ARN}"
BATCH_ROLE_ARN="${BATCH_ROLE_ARN:?set BATCH_ROLE_ARN}"
OPS_BUCKET="${OPS_BUCKET:?set OPS_BUCKET}"
MANIFEST_KEY="${MANIFEST_KEY:?set MANIFEST_KEY}"   # e.g. manifests/my-backfill.csv
REPORT_PREFIX="${REPORT_PREFIX:-batch-reports/}"

ETAG=$(aws s3api head-object --bucket "$OPS_BUCKET" --key "$MANIFEST_KEY" --query ETag --output text | tr -d '"')

JOB_ID=$(aws s3control create-job \
  --region "$AWS_REGION" \
  --account-id "$ACCOUNT_ID" \
  --priority 10 \
  --role-arn "$BATCH_ROLE_ARN" \
  --operation "{\"LambdaInvoke\": {\"FunctionArn\": \"$LAMBDA_ARN\"}}" \
  --manifest "{\"Spec\": {\"Format\": \"S3BatchOperations_CSV_20180820\", \"Fields\": [\"Bucket\", \"Key\"]}, \"Location\": {\"ObjectArn\": \"arn:aws:s3:::$OPS_BUCKET/$MANIFEST_KEY\", \"ETag\": \"$ETAG\"}}" \
  --report "{\"Bucket\": \"arn:aws:s3:::$OPS_BUCKET\", \"Prefix\": \"$REPORT_PREFIX\", \"Format\": \"Report_CSV_20180820\", \"Enabled\": true, \"ReportScope\": \"AllTasks\"}" \
  --client-request-token "job-$(date +%s)" \
  --no-confirmation-required \
  --query JobId --output text)

echo "Created job: $JOB_ID"
aws s3control describe-job --region "$AWS_REGION" --account-id "$ACCOUNT_ID" --job-id "$JOB_ID"
