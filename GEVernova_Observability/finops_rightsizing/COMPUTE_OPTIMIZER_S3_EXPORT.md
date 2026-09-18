# AWS Compute Optimizer export to S3 → Elastic

Use **Custom AWS Logs**, not the stock AWS integration. The AWS package has no Compute Optimizer input. Custom AWS Logs is the Fleet `aws-s3` integration that already matches this project’s S3 → SQS pattern.

Start with **EC2 in `us-west-2` / `985408759551`**. Other resource types are the same pattern with a different export API and prefix.

```text
Compute Optimizer (daily export job)
        │  CSV + metadata JSON
        ▼
S3  s3://<bucket>/ec2/compute-optimizer/<account>/...csv
        │  ObjectCreated, suffix .csv
        ▼
SQS  elastic-compute-optimizer-s3
        │  Fleet Custom AWS Logs (queue_url + role elastic-integration)
        ▼
pipeline  finops-co-csv  →  reroute  →  logs-finops.rightsizing-default
        ▼
transform  finops-rightsizing-latest  →  FinOps dashboards
```

Export jobs are **one-shot**. AWS does not stream recs. A daily EventBridge schedule is what makes this production.

---

## 0. Prerequisites

- Compute Optimizer enrollment `Active` in the account.
- Existing role `arn:aws:iam::985408759551:role/elastic-integration` (same one Cost Explorer / CloudWatch already use).
- Bucket **in `us-west-2`**, private, not Requester Pays. Do **not** reuse the WAF/ELB log bucket. AWS wants a dedicated CO export bucket.
- One in-flight export **per resource type per region**. Do not overlap daily jobs.

Placeholders used below:

| | |
|---|---|
| Account | `985408759551` |
| Region | `us-west-2` |
| Bucket | `gev-compute-optimizer-usw2-985408759551` |
| Prefix | `ec2` |
| Queue | `elastic-compute-optimizer-s3` |
| Role | `elastic-integration` |

---

## 1. AWS: bucket + Compute Optimizer write policy

```bash
export AWS_DEFAULT_REGION=us-west-2
ACCOUNT=985408759551
BUCKET=gev-compute-optimizer-usw2-${ACCOUNT}
PREFIX=ec2

aws s3api create-bucket \
  --bucket "${BUCKET}" \
  --create-bucket-configuration LocationConstraint=us-west-2 \
  --region us-west-2

aws s3api put-public-access-block --bucket "${BUCKET}" --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
```

Bucket policy (all three statements are required; prefix in `PutObject` must match the export `keyPrefix`):

```bash
aws s3api put-bucket-policy --bucket "${BUCKET}" --policy "$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "COGetBucketAcl",
      "Effect": "Allow",
      "Principal": { "Service": "compute-optimizer.amazonaws.com" },
      "Action": "s3:GetBucketAcl",
      "Resource": "arn:aws:s3:::${BUCKET}",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "${ACCOUNT}" },
        "ArnLike": { "aws:SourceArn": "arn:aws:compute-optimizer:us-west-2:${ACCOUNT}:*" }
      }
    },
    {
      "Sid": "COGetBucketPolicyStatus",
      "Effect": "Allow",
      "Principal": { "Service": "compute-optimizer.amazonaws.com" },
      "Action": "s3:GetBucketPolicyStatus",
      "Resource": "arn:aws:s3:::${BUCKET}",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "${ACCOUNT}" },
        "ArnLike": { "aws:SourceArn": "arn:aws:compute-optimizer:us-west-2:${ACCOUNT}:*" }
      }
    },
    {
      "Sid": "COPutObject",
      "Effect": "Allow",
      "Principal": { "Service": "compute-optimizer.amazonaws.com" },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${BUCKET}/${PREFIX}/compute-optimizer/${ACCOUNT}/*",
      "Condition": {
        "StringEquals": {
          "s3:x-amz-acl": "bucket-owner-full-control",
          "aws:SourceAccount": "${ACCOUNT}"
        },
        "ArnLike": { "aws:SourceArn": "arn:aws:compute-optimizer:us-west-2:${ACCOUNT}:*" }
      }
    }
  ]
}
EOF
)"
```

AWS always appends `/compute-optimizer/<accountId>/` after your prefix. Object keys look like:

`s3://<bucket>/ec2/compute-optimizer/985408759551/us-west-2-<timestamp>-<jobId>.csv`

plus a sibling `*-metadata.json`. Elastic should ingest **only the CSV**.

If the bucket is KMS-encrypted, also grant `compute-optimizer.amazonaws.com` `kms:GenerateDataKey` and `kms:Decrypt` on that key.

---

## 2. AWS: SQS + S3 notification (CSV only)

```bash
QUEUE=elastic-compute-optimizer-s3
QUEUE_URL=$(aws sqs create-queue --queue-name "${QUEUE}" \
  --attributes VisibilityTimeout=300,MessageRetentionPeriod=86400 \
  --query QueueUrl --output text)
QUEUE_ARN=$(aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)
echo "${QUEUE_URL}"
echo "${QUEUE_ARN}"
```

Allow S3 to send into the queue:

```bash
aws sqs set-queue-attributes --queue-url "${QUEUE_URL}" --attributes Policy="$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowS3Notify",
    "Effect": "Allow",
    "Principal": { "Service": "s3.amazonaws.com" },
    "Action": "sqs:SendMessage",
    "Resource": "${QUEUE_ARN}",
    "Condition": {
      "ArnEquals": { "aws:SourceArn": "arn:aws:s3:::${BUCKET}" },
      "StringEquals": { "aws:SourceAccount": "${ACCOUNT}" }
    }
  }]
}
EOF
)"
```

Notify on `.csv` only (skips metadata JSON):

```bash
aws s3api put-bucket-notification-configuration --bucket "${BUCKET}" --notification-configuration "$(cat <<EOF
{
  "QueueConfigurations": [{
    "Id": "compute-optimizer-csv",
    "QueueArn": "${QUEUE_ARN}",
    "Events": ["s3:ObjectCreated:*"],
    "Filter": {
      "Key": {
        "FilterRules": [
          { "Name": "prefix", "Value": "${PREFIX}/" },
          { "Name": "suffix", "Value": ".csv" }
        ]
      }
    }
  }]
}
EOF
)"
```

---

## 3. AWS: IAM on `elastic-integration`

Attach this **in addition to** the existing role. Do not replace Cost Explorer / CloudWatch permissions.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadComputeOptimizerExports",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::gev-compute-optimizer-usw2-985408759551",
        "arn:aws:s3:::gev-compute-optimizer-usw2-985408759551/*"
      ]
    },
    {
      "Sid": "ReadComputeOptimizerQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:us-west-2:985408759551:elastic-compute-optimizer-s3"
    }
  ]
}
```

```bash
aws iam put-role-policy \
  --role-name elastic-integration \
  --policy-name elastic-compute-optimizer-s3 \
  --policy-document file://elastic-compute-optimizer-s3.json
```

Agentless / identity federation **requires** `queue_url`. Do not use bucket polling (`bucket_arn`) on the managed agentless policy.

---

## 4. AWS: export job (once, then daily)

Lock `fieldsToExport` so CSV column order is stable. That is what the ingest pipeline depends on.

```bash
aws compute-optimizer export-ec2-instance-recommendations \
  --region us-west-2 \
  --file-format Csv \
  --s3-destination-config "bucket=${BUCKET},keyPrefix=${PREFIX}" \
  --fields-to-export \
    AccountId InstanceArn InstanceName Finding CurrentInstanceType \
    LookbackPeriodInDays RecommendationOptionsInstanceType \
    RecommendationOptionsPerformanceRisk \
    RecommendationOptionsEstimatedMonthlySavingsValue \
    RecommendationOptionsEstimatedMonthlySavingsCurrency
```

Wait until it finishes (can take minutes to hours):

```bash
aws compute-optimizer describe-recommendation-export-jobs \
  --query 'recommendationExportJobs[].[jobId,status,resourceType,creationTimestamp]' \
  --output table
```

Confirm objects:

```bash
aws s3 ls "s3://${BUCKET}/${PREFIX}/compute-optimizer/${ACCOUNT}/"
aws s3 cp "s3://${BUCKET}/${PREFIX}/compute-optimizer/${ACCOUNT}/<the.csv>" - | head -2
```

Save the header line. CSV names are camelCase / numbered, for example `accountId`, `instanceArn`, `finding`, `recommendationOptions_1_instanceType`. If the header does not match the pipeline below, fix the pipeline before turning on Fleet.

### Daily schedule

Export is not incremental. Use EventBridge Scheduler (universal AWS SDK target). One schedule per resource type.

Trust `scheduler.amazonaws.com`. Allow:

- `compute-optimizer:ExportEC2InstanceRecommendations`
- later: `ExportEBSVolumeRecommendations`, `ExportIdleRecommendations`, `ExportLambdaFunctionRecommendations`, `ExportAutoScalingGroupRecommendations`, `ExportECSServiceRecommendations`, `ExportRDSDatabaseRecommendations`

```bash
aws scheduler create-schedule \
  --name compute-optimizer-export-ec2-daily \
  --schedule-expression "cron(0 6 * * ? *)" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target '{
    "Arn": "arn:aws:scheduler:::aws-sdk:computeoptimizer:exportEC2InstanceRecommendations",
    "RoleArn": "arn:aws:iam::985408759551:role/compute-optimizer-export-scheduler",
    "Input": "{\"fileFormat\":\"Csv\",\"s3DestinationConfig\":{\"bucket\":\"gev-compute-optimizer-usw2-985408759551\",\"keyPrefix\":\"ec2\"},\"fieldsToExport\":[\"AccountId\",\"InstanceArn\",\"InstanceName\",\"Finding\",\"CurrentInstanceType\",\"LookbackPeriodInDays\",\"RecommendationOptionsInstanceType\",\"RecommendationOptionsPerformanceRisk\",\"RecommendationOptionsEstimatedMonthlySavingsValue\",\"RecommendationOptionsEstimatedMonthlySavingsCurrency\"]}"
  }'
```

If `create-schedule` rejects the ARN, use a tiny Lambda that calls the same `export-*` APIs instead. Keep the 06:00 UTC cadence so jobs cannot overlap.

Org-wide later: add `--include-member-accounts` (management account, members opted in, Organizations trusted access). Still one CSV per resource type per region.

---

## 5. Elastic: Custom AWS Logs (not the AWS integration)

Do **not** edit the existing AWS integration and hunt for Compute Optimizer. Add a new integration:

**Kibana → Integrations → Custom AWS Logs → Add**

Put it on the Fleet policy that already assumes `elastic-integration` for account `985408759551` (the agentless AWS policy is fine **if** you set Queue URL).

| Setting | Value |
|---|---|
| Collect logs from S3 | On |
| Collect logs from CloudWatch | Off |
| Queue URL | `https://sqs.us-west-2.amazonaws.com/985408759551/elastic-compute-optimizer-s3` |
| Bucket ARN / Access Point | **Leave empty** (cannot set with Queue URL) |
| Number of workers | `1` |
| Default Region | `us-west-2` |
| Setup Access | Same as billing: Assume Role |
| Role ARN | `arn:aws:iam::985408759551:role/elastic-integration` |
| Ingest pipeline | `finops-co-csv` |
| File selectors (advanced) | see below |

File selectors (Go regex on the object key). Belt-and-suspenders with the S3 suffix filter:

```yaml
- regex: '\.csv$'
```

Save and deploy. Default data stream is `logs-aws_logs.generic-default`. The pipeline below reroutes into `logs-finops.rightsizing-default`, which the FinOps space already uses.

---

## 6. Elastic: parse CSV and land in FinOps

Create pipeline `finops-co-csv` **before** the first SQS message is processed. Column names must match the header from step 4. Adjust `recommendationOptions_1_*` if AWS numbered them differently.

This pipeline:

1. Drops the CSV header row.
2. Parses the controlled EC2 columns.
3. Maps into `finops.rightsizing.*`.
4. Drops `OPTIMIZED` / empty findings (same idea as `ingest_compute_optimizer.py`).
5. Reroutes to dataset `finops.rightsizing`, where index template `logs-finops.rightsizing` runs `finops-rightsizing` (fingerprint + `status=open`).

```json
PUT _ingest/pipeline/finops-co-csv
{
  "description": "Compute Optimizer EC2 CSV from Custom AWS Logs → finops.rightsizing",
  "processors": [
    { "drop": { "if": "ctx.message == null || ctx.message.startsWith('accountId') || ctx.message.startsWith('AccountId')" } },
    {
      "csv": {
        "field": "message",
        "target_fields": [
          "co.account_id",
          "co.instance_arn",
          "co.instance_name",
          "co.finding",
          "co.current_type",
          "co.lookback_days",
          "co.recommended_type",
          "co.performance_risk",
          "co.estimated_monthly_savings",
          "co.currency"
        ],
        "ignore_missing": false,
        "trim": true
      }
    },
    { "uppercase": { "field": "co.finding" } },
    {
      "gsub": {
        "field": "co.finding",
        "pattern": "[- ]",
        "replacement": "_"
      }
    },
    {
      "drop": {
        "if": "['OPTIMIZED','UNAVAILABLE','INSUFFICIENT_DATA','INSUFFICIENTDATA',''].contains(ctx.co?.finding)"
      }
    },
    { "set": { "field": "cloud.provider", "value": "aws" } },
    { "set": { "field": "cloud.account.id", "copy_from": "co.account_id" } },
    { "set": { "field": "cloud.region", "value": "us-west-2" } },
    { "set": { "field": "finops.rightsizing.resource_arn", "copy_from": "co.instance_arn" } },
    { "set": { "field": "finops.rightsizing.resource_name", "copy_from": "co.instance_name", "ignore_empty_value": true } },
    { "set": { "field": "finops.rightsizing.resource_type", "value": "Ec2Instance" } },
    { "set": { "field": "finops.rightsizing.finding", "copy_from": "co.finding" } },
    { "set": { "field": "finops.rightsizing.current_type", "copy_from": "co.current_type" } },
    { "set": { "field": "finops.rightsizing.recommended_type", "copy_from": "co.recommended_type" } },
    { "set": { "field": "finops.rightsizing.performance_risk", "copy_from": "co.performance_risk" } },
    { "set": { "field": "finops.rightsizing.lookback_days", "copy_from": "co.lookback_days" } },
    { "convert": { "field": "finops.rightsizing.lookback_days", "type": "integer", "ignore_missing": true } },
    { "set": { "field": "finops.rightsizing.estimated_monthly_savings", "copy_from": "co.estimated_monthly_savings" } },
    { "convert": { "field": "finops.rightsizing.estimated_monthly_savings", "type": "float", "ignore_missing": true } },
    { "set": { "field": "finops.rightsizing.currency", "copy_from": "co.currency" } },
    { "set": { "field": "finops.rightsizing.source", "value": "compute_optimizer" } },
    {
      "set": {
        "field": "finops.rightsizing.action",
        "value": "downsize",
        "if": "ctx.finops?.rightsizing?.finding == 'OVER_PROVISIONED' || ctx.finops?.rightsizing?.finding == 'NOT_OPTIMIZED'"
      }
    },
    {
      "set": {
        "field": "finops.rightsizing.action",
        "value": "upsize",
        "if": "ctx.finops?.rightsizing?.finding == 'UNDER_PROVISIONED'"
      }
    },
    {
      "set": {
        "field": "finops.rightsizing.action",
        "value": "stop_idle",
        "if": "ctx.finops?.rightsizing?.finding == 'IDLE'"
      }
    },
    {
      "drop": { "if": "ctx.finops?.rightsizing?.action == null" }
    },
    {
      "reroute": {
        "dataset": "finops.rightsizing",
        "namespace": "default"
      }
    }
  ]
}
```

After reroute, `finops-rightsizing` still fingerprints `finops.rightsizing.id` and defaults `status` to `open`.

**Status merge is gone.** The Python job copied `owner` / `case_id` / `hidden` from `finops-rightsizing-latest`. Custom AWS Logs cannot do that. Next recs will look new unless you add an enrich processor against `finops-rightsizing-latest` or keep a small updater. Dashboards still work for Identified; parked/in-progress cases will reset on each daily file until that enrich exists.

---

## 7. Verify

```bash
# SQS should go to 0 after Agent drains
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
```

Elastic:

```json
GET logs-aws_logs.generic-default/_count
GET logs-finops.rightsizing-default/_count
GET logs-finops.rightsizing-default/_search
{
  "size": 3,
  "sort": [{ "@timestamp": "desc" }],
  "_source": ["finops.rightsizing", "cloud.account.id", "aws.s3"]
}
```

Then confirm **Spend vs savings** Identified is no longer $0 (hidden samples stay parked).

If `logs-aws_logs.generic-default` fills and FinOps does not: pipeline name mismatch, header row not dropped, CSV column order off, or reroute failed. Simulate with `_ingest/pipeline/finops-co-csv/_simulate` using one real `message` line from the CSV.

---

## 8. Other resource types (after EC2 works)

Same bucket, **new prefix** (`ebs`, `idle`, `lambda`, …), extra `PutObject` ARN in the bucket policy, extra S3 notification (or one prefix parent `''` and file_selectors per type), extra daily export:

```text
export-ebs-volume-recommendations
export-idle-recommendations
export-lambda-function-recommendations
export-auto-scaling-group-recommendations
export-ecs-service-recommendations
export-rds-database-recommendations
```

CSV headers differ (EBS uses `volumeArn`; idle uses `resourceArn` / `resourceType`; RDS splits instance vs storage). Do not reuse the EC2 `target_fields` list. Either a second Custom AWS Logs stream + pipeline, or one pipeline that branches on `aws.s3.object.key`.

---

## What the customer must send back

1. Bucket name + `aws s3 ls` of the first `.csv`
2. First line (header) of that CSV
3. Queue URL
4. Confirmation `elastic-compute-optimizer-s3` is on `elastic-integration`
5. Export job `status=Complete`

You then add Custom AWS Logs + `finops-co-csv` in Kibana. They do not need Elastic console access for the AWS half.
