#!/usr/bin/env bash
# Delete everything this project created (Redshift Serverless bills while it is used, so do this when done).
set -euo pipefail
STACK="${STACK:-retail-dw}"
REGION="${AWS_REGION:-$(aws configure get region)}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export AWS_DEFAULT_REGION="$REGION"
DATA_BUCKET="${STACK}-data-${ACCOUNT}-${REGION}"
ART_BUCKET="${ARTIFACT_BUCKET:-${STACK}-artifacts-${ACCOUNT}-${REGION}}"

read -r -p "Delete stack $STACK and buckets $DATA_BUCKET, $ART_BUCKET? [y/N] " ok
[ "$ok" = "y" ] || exit 0
aws s3 rm "s3://$DATA_BUCKET" --recursive || true
aws cloudformation delete-stack --stack-name "$STACK"
aws cloudformation wait stack-delete-complete --stack-name "$STACK"
aws s3 rb "s3://$ART_BUCKET" --force || true
echo "Deleted."
