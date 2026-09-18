#!/usr/bin/env bash
# Phase 0: confirm Compute Optimizer enrollment + recs on apm-stage,
# then attach read IAM to elastic-integration.
#
# Run from a shell that can assume or is already in account 985408759551, us-west-2.
# Does not call Elastic. Does not enable Fleet inputs.
set -euo pipefail

ACCOUNT="${ACCOUNT:-985408759551}"
REGION="${REGION:-us-west-2}"
ROLE_ARN="${ROLE_ARN:-arn:aws:iam::${ACCOUNT}:role/elastic-integration}"
POLICY_NAME="${POLICY_NAME:-elastic-compute-optimizer-readonly}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICY_FILE="${SCRIPT_DIR}/compute-optimizer-readonly.json"

export AWS_DEFAULT_REGION="${REGION}"

need() { command -v "$1" >/dev/null || { echo "missing $1" >&2; exit 1; }; }
need aws
need jq

echo "== caller =="
CALLER="$(aws sts get-caller-identity --output json)"
echo "${CALLER}" | jq '{Account, Arn}'
CALLER_ACCOUNT="$(echo "${CALLER}" | jq -r .Account)"
if [[ "${CALLER_ACCOUNT}" != "${ACCOUNT}" ]]; then
  echo "assuming ${ROLE_ARN}"
  CREDS="$(aws sts assume-role --role-arn "${ROLE_ARN}" --role-session-name finops-phase0 --output json)"
  export AWS_ACCESS_KEY_ID="$(echo "${CREDS}" | jq -r .Credentials.AccessKeyId)"
  export AWS_SECRET_ACCESS_KEY="$(echo "${CREDS}" | jq -r .Credentials.SecretAccessKey)"
  export AWS_SESSION_TOKEN="$(echo "${CREDS}" | jq -r .Credentials.SessionToken)"
  aws sts get-caller-identity --output json | jq '{Account, Arn}'
fi

echo
echo "== enrollment (${REGION}) =="
ENROLL="$(aws compute-optimizer get-enrollment-status --output json)"
echo "${ENROLL}" | jq .
STATUS="$(echo "${ENROLL}" | jq -r .status)"
if [[ "${STATUS}" != "Active" ]]; then
  echo "FAIL: enrollment status is ${STATUS}, expected Active" >&2
  exit 2
fi

count_recs() {
  local api="$1"
  local key="$2"
  local out
  if ! out="$(aws compute-optimizer "${api}" --output json 2>/dev/null)"; then
    echo "${api}: ERROR (denied or unsupported)"
    return 0
  fi
  local n
  n="$(echo "${out}" | jq --arg k "${key}" '.[$k] | length')"
  local next
  next="$(echo "${out}" | jq -r '.nextToken // empty')"
  echo "${api}: ${n} (page 1)${next:+ nextToken present}"
  echo "${out}" | jq --arg k "${key}" '
    [.[$k][] | {
      finding: (.finding // .findingReasonCodes // null),
      arn: (.instanceArn // .volumeArn // .functionArn // .autoScalingGroupArn // .serviceArn // .resourceArn // null),
      current: (.currentInstanceType // .currentConfiguration.instanceType // .currentConfiguration.volumeType // null),
      savings: (.recommendationOptions[0].savingsOpportunity.estimatedMonthlySavings.value // null)
    }] | .[0:8]
  '
}

echo
echo "== recommendations (${REGION}) =="
count_recs get-ec2-instance-recommendations instanceRecommendations
count_recs get-ebs-volume-recommendations volumeRecommendations
count_recs get-idle-recommendations idleRecommendations
count_recs get-lambda-function-recommendations lambdaFunctions
count_recs get-auto-scaling-group-recommendations autoScalingGroupRecommendations
count_recs get-rds-database-recommendations rdsDBRecommendations
count_recs get-ecs-service-recommendations ecsServiceRecommendations

if [[ "${APPLY_IAM:-}" == "1" ]]; then
  echo
  echo "== attach IAM to elastic-integration =="
  POLICY_ARN="$(aws iam list-policies --scope Local --query "Policies[?PolicyName=='${POLICY_NAME}'].Arn" --output text)"
  if [[ -z "${POLICY_ARN}" || "${POLICY_ARN}" == "None" ]]; then
    POLICY_ARN="$(aws iam create-policy \
      --policy-name "${POLICY_NAME}" \
      --policy-document "file://${POLICY_FILE}" \
      --query Policy.Arn --output text)"
    echo "created ${POLICY_ARN}"
  else
    echo "exists ${POLICY_ARN}"
  fi
  aws iam attach-role-policy --role-name elastic-integration --policy-arn "${POLICY_ARN}"
  echo "attached ${POLICY_NAME} to elastic-integration"
else
  echo
  echo "IAM not applied. To attach read recs on elastic-integration:"
  echo "  APPLY_IAM=1 $0"
  echo "or:"
  echo "  aws iam create-policy --policy-name ${POLICY_NAME} --policy-document file://${POLICY_FILE}"
  echo "  aws iam attach-role-policy --role-name elastic-integration --policy-arn arn:aws:iam::${ACCOUNT}:policy/${POLICY_NAME}"
fi
