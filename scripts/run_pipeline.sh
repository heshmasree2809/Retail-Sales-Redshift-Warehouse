#!/usr/bin/env bash
# Generate synthetic data, upload it to the curated zone, run the state machine, wait for the result.
# Usage: ROWS=1000000 STACK=retail-dw ./scripts/run_pipeline.sh
set -euo pipefail
cd "$(dirname "$0")/.."

STACK="${STACK:-retail-dw}"
ROWS="${ROWS:-1000000}"
REGION="${AWS_REGION:-$(aws configure get region)}"
export AWS_DEFAULT_REGION="$REGION"
out() { aws cloudformation describe-stacks --stack-name "$STACK" \
          --query "Stacks[0].Outputs[?OutputKey=='$0'].OutputValue" --output text; }
BUCKET="$(out DataBucketName)"
SM_ARN="$(out StateMachineArn)"

echo "==> Generating $ROWS synthetic sales rows (Parquet)"
PYTHONPATH=src python3 -m rdw.generate --rows "$ROWS" --out build/data --format parquet

echo "==> Uploading to s3://$BUCKET/curated/"
aws s3 sync build/data/curated "s3://$BUCKET/curated" --delete --only-show-errors

# To run your own Glue job first: INPUT='{"glue_job_name":"your-job"}'
INPUT="${INPUT:-}"
[ -z "$INPUT" ] && INPUT='{}'
echo "==> Starting state machine"
EXEC_ARN="$(aws stepfunctions start-execution --state-machine-arn "$SM_ARN" --input "$INPUT" \
            --query executionArn --output text)"
echo "$EXEC_ARN"

while true; do
  STATUS="$(aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query status --output text)"
  [ "$STATUS" != "RUNNING" ] && break
  sleep 10
done
echo "==> Finished: $STATUS"
if [ "$STATUS" != "SUCCEEDED" ]; then
  aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query '{error:error,cause:cause}'
  exit 1
fi
aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query 'output' --output text
