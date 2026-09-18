#!/usr/bin/env bash
# Deploys Second Look's Lambda container to AWS. OWNER-RUN ONLY (#47) — deploying is a
# human-only action per CLAUDE.md; no goal, including the one that wrote this file, runs
# this script. Safe to re-run: every step checks before it creates.
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"
FUNCTION_NAME="${FUNCTION_NAME:-secondlook}"
ECR_REPOSITORY="${ECR_REPOSITORY:-secondlook-lambda}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d%H%M%S)}"
ROLE_NAME="${FUNCTION_NAME}-execution-role"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-30}"
MEMORY_MB="${MEMORY_MB:-2048}"

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AWS_REGION AWS_PROFILE

account_id="$(aws sts get-caller-identity --query Account --output text)"
ecr_uri="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

# --- ECR repository (create if missing) --------------------------------------------
aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$ECR_REPOSITORY" \
       --image-scanning-configuration scanOnPush=true

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"

IMAGE_TAG="${ecr_uri}:${IMAGE_TAG}" bash "${DEPLOY_DIR}/build.sh"
docker push "${ecr_uri}:${IMAGE_TAG}"

# --- Execution role (create or update; CloudWatch Logs only, no S3 yet) ------------
# S3 permissions are deferred until store.py lands (SPEC §9) — a documented decision,
# not an oversight: today's handler only ever touches /tmp.
trust_policy='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}'
logs_policy='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:'"${AWS_REGION}"':'"${account_id}"':log-group:/aws/lambda/'"${FUNCTION_NAME}"':*"
    }
  ]
}'

role_arn="arn:aws:iam::${account_id}:role/${ROLE_NAME}"
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "$trust_policy" >/dev/null
  # A freshly created role isn't always immediately assumable by Lambda; a short
  # settle delay avoids a create-function race on a brand-new role.
  sleep 8
fi
aws iam put-role-policy --role-name "$ROLE_NAME" \
  --policy-name "${ROLE_NAME}-logs" --policy-document "$logs_policy"

# --- Lambda function (create or update-code) ----------------------------------------
image_uri="${ecr_uri}:${IMAGE_TAG##*:}"
if aws lambda get-function --function-name "$FUNCTION_NAME" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FUNCTION_NAME" --image-uri "$image_uri" >/dev/null
  aws lambda wait function-updated --function-name "$FUNCTION_NAME"
else
  aws lambda create-function --function-name "$FUNCTION_NAME" \
    --package-type Image --code "ImageUri=${image_uri}" \
    --role "$role_arn" --architectures arm64 \
    --timeout "$TIMEOUT_SECONDS" --memory-size "$MEMORY_MB" >/dev/null
  aws lambda wait function-active --function-name "$FUNCTION_NAME"
fi

# --- Function URL (create if missing; public, unauthenticated — see docs/deploy.md) --
if ! aws lambda get-function-url-config --function-name "$FUNCTION_NAME" >/dev/null 2>&1; then
  aws lambda create-function-url-config --function-name "$FUNCTION_NAME" --auth-type NONE >/dev/null
  # Required once for a public Function URL to actually be reachable: without this
  # permission the URL returns 403 even though the function and URL both exist.
  # Flag names have drifted across AWS CLI versions before — reconfirm against
  # `aws lambda add-permission help` at execution time if this fails.
  aws lambda add-permission --function-name "$FUNCTION_NAME" \
    --statement-id FunctionURLAllowPublicAccess \
    --action lambda:InvokeFunctionUrl \
    --principal '*' \
    --function-url-auth-type NONE >/dev/null
fi

function_url="$(aws lambda get-function-url-config --function-name "$FUNCTION_NAME" \
  --query FunctionUrl --output text)"

echo "deployed ${FUNCTION_NAME}; image ${image_uri}"
echo "function url: ${function_url}"
