#!/usr/bin/env bash
# Deploy the warehouse stack. Needs: AWS CLI v2 configured, Python 3.
# Usage: STACK=retail-dw AWS_REGION=ap-south-1 ./scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

STACK="${STACK:-retail-dw}"                       # must be lowercase (used in bucket and workgroup names)
REGION="${AWS_REGION:-$(aws configure get region)}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
ART_BUCKET="${ARTIFACT_BUCKET:-${STACK}-artifacts-${ACCOUNT}-${REGION}}"
BASE_CAPACITY="${BASE_CAPACITY:-8}"
export AWS_DEFAULT_REGION="$REGION"

echo "==> Artifact bucket: $ART_BUCKET"
if ! aws s3api head-bucket --bucket "$ART_BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$ART_BUCKET"
  else
    aws s3api create-bucket --bucket "$ART_BUCKET" --create-bucket-configuration "LocationConstraint=$REGION"
  fi
fi

echo "==> Building Lambda package"
rm -rf build/run_sql && mkdir -p build/run_sql/sql
cp lambda/run_sql/handler.py src/rdw/sqlfiles.py src/rdw/redshift_data.py build/run_sql/
cp sql/*.sql build/run_sql/sql/

echo "==> Packaging and deploying stack $STACK"
aws cloudformation package --template-file infra/template.yaml \
  --s3-bucket "$ART_BUCKET" --output-template-file build/packaged.yaml
aws cloudformation deploy --template-file build/packaged.yaml --stack-name "$STACK" \
  --capabilities CAPABILITY_IAM --parameter-overrides "BaseCapacity=$BASE_CAPACITY"

out() { aws cloudformation describe-stacks --stack-name "$STACK" \
          --query "Stacks[0].Outputs[?OutputKey=='$0'].OutputValue" --output text; }
WG_ARN="$(out WorkgroupArn)"

echo "==> Cost guard: daily usage limit on the workgroup (deactivates it if exceeded)"
aws redshift-serverless create-usage-limit --resource-arn "$WG_ARN" \
  --usage-type serverless-compute --amount "${DAILY_RPU_HOURS_LIMIT:-30}" \
  --period daily --breach-action deactivate >/dev/null \
  || echo "WARN: could not create the usage limit (it may already exist). Set one in the console."

echo
echo "Deployed. Next steps:"
echo "  bucket       : $(out DataBucketName)"
echo "  workgroup    : $(out WorkgroupName)"
echo "  run pipeline : ./scripts/run_pipeline.sh"
