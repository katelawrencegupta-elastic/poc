#!/usr/bin/env python3
"""Pull AWS Compute Optimizer Get* APIs into logs-finops.rightsizing-default.

Does not invent recs from Cost Explorer. Drops OPTIMIZED and recs with no
savings option. Preserves status/owner/case_id/realized_savings/hidden_reason
from finops-rightsizing-latest (fallback: the data stream).

Requires boto3 and AWS credentials that can call compute-optimizer:Get* in
account 985408759551 / us-west-2. Elastic AWS integration does not ingest this.

  uv run --with boto3 python ingest_compute_optimizer.py --check
  uv run --with boto3 python ingest_compute_optimizer.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply import API_KEY, ES, req

ACCOUNT = os.environ.get("ACCOUNT", "985408759551")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
ACCOUNT_NAME = os.environ.get("ACCOUNT_NAME", "ged-pgog-apm-usw02-stage")
DATA_STREAM = "logs-finops.rightsizing-default"
LATEST_INDEX = "finops-rightsizing-latest"

DROP_FINDINGS = {
    "OPTIMIZED",
    "UNAVAILABLE",
    "INSUFFICIENT_DATA",
    "INSUFFICIENTDATA",
}
FINDING_ALIASES = {
    "NOTOPTIMIZED": "OVER_PROVISIONED",
    "NOT_OPTIMIZED": "OVER_PROVISIONED",
    "OVERPROVISIONED": "OVER_PROVISIONED",
    "UNDERPROVISIONED": "UNDER_PROVISIONED",
    "UNATTACHED": "IDLE",
}
ACTION_FOR_FINDING = {
    "OVER_PROVISIONED": "downsize",
    "IDLE": "stop_idle",
    "UNDER_PROVISIONED": "upsize",
}
APIS = [
    (
        "get_ec2_instance_recommendations",
        "instanceRecommendations",
        "Ec2Instance",
    ),
    ("get_ebs_volume_recommendations", "volumeRecommendations", "EbsVolume"),
    ("get_idle_recommendations", "idleRecommendations", "Idle"),
    (
        "get_lambda_function_recommendations",
        "lambdaFunctions",
        "LambdaFunction",
    ),
    (
        "get_auto_scaling_group_recommendations",
        "autoScalingGroupRecommendations",
        "AutoScalingGroup",
    ),
    (
        "get_rds_database_recommendations",
        "rdsDBRecommendations",
        "RdsDBInstance",
    ),
    (
        "get_ecs_service_recommendations",
        "ecsServiceRecommendations",
        "EcsService",
    ),
]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def aws_session(account: str, role_arn: str):
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    session = boto3.Session()
    sts = session.client("sts")
    try:
        ident = sts.get_caller_identity()
    except NoCredentialsError:
        print("FAIL: no AWS credentials (export keys/profile, then retry)", file=sys.stderr)
        sys.exit(2)
    print(f"caller account={ident.get('Account')} arn={ident.get('Arn')}")
    if ident.get("Account") == account:
        return session
    print(f"assuming {role_arn}")
    try:
        creds = sts.assume_role(
            RoleArn=role_arn, RoleSessionName="finops-co-ingest"
        )["Credentials"]
    except ClientError as e:
        print(f"FAIL: cannot assume {role_arn}: {e}", file=sys.stderr)
        sys.exit(2)
    import boto3 as _boto3

    assumed = _boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )
    ident2 = assumed.client("sts").get_caller_identity()
    print(f"assumed account={ident2.get('Account')} arn={ident2.get('Arn')}")
    return assumed


def paginate(client, method: str, result_key: str) -> Iterator[dict]:
    from botocore.exceptions import BotoCoreError, ClientError

    if not hasattr(client, method):
        print(f"{method}: skip (not in this botocore)")
        return
    token = None
    pages = 0
    while True:
        kwargs = {}
        if token:
            kwargs["nextToken"] = token
        try:
            resp = getattr(client, method)(**kwargs)
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code") or type(e).__name__
            print(f"{method}: skip ({code})")
            return
        except (BotoCoreError, TypeError) as e:
            print(f"{method}: skip ({type(e).__name__})")
            return
        items = resp.get(result_key) or []
        pages += 1
        for item in items:
            yield item
        token = resp.get("nextToken")
        if not token:
            print(f"{method}: pages={pages}")
            return


def arn_parts(arn: str | None) -> tuple[str | None, str | None, str | None]:
    if not arn:
        return None, None, None
    parts = arn.split(":")
    region = parts[3] if len(parts) > 3 else None
    account = parts[4] if len(parts) > 4 else None
    resource = parts[-1].split("/", 1)[-1] if parts else None
    return region, account, resource


def first_option(rec: dict) -> dict:
    for key in (
        "recommendationOptions",
        "volumeRecommendationOptions",
        "memorySizeRecommendationOptions",
        "instanceRecommendationOptions",
        "storageRecommendationOptions",
    ):
        opts = rec.get(key) or []
        if opts:
            return opts[0]
    return {}


def savings_value(obj: dict | None) -> float | None:
    if not obj:
        return None
    so = obj.get("savingsOpportunity") or obj.get("savingsOpportunityAfterDiscounts") or {}
    ems = so.get("estimatedMonthlySavings") or {}
    val = ems.get("value")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def risk_label(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return str(raw)
    if v >= 3:
        return "High"
    if v >= 2:
        return "Medium"
    if v >= 1:
        return "Low"
    return "VeryLow"


def norm_finding(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper().replace(" ", "_").replace("-", "_")
    s = FINDING_ALIASES.get(s, s)
    return s or None


def cfg_type(cfg: Any) -> str | None:
    if not isinstance(cfg, dict):
        return str(cfg) if cfg is not None else None
    for key in (
        "instanceType",
        "volumeType",
        "dbInstanceClass",
        "memorySize",
        "instanceClass",
    ):
        if cfg.get(key) is not None:
            return str(cfg[key])
    cpu, mem = cfg.get("cpu"), cfg.get("memory")
    if cpu is not None or mem is not None:
        return f"{cpu or '-'}cpu/{mem or '-'}mb"
    return None


def recommended_type(opt: dict, rec: dict, resource_type: str) -> str | None:
    for key in (
        "instanceType",
        "dbInstanceClass",
        "memorySize",
        "recommendedInstanceType",
    ):
        if opt.get(key) is not None:
            val = opt[key]
            return f"{val}MB" if key == "memorySize" else str(val)
    nested = cfg_type(opt.get("configuration") or opt.get("currentConfiguration"))
    if nested:
        return nested
    cpu, mem = opt.get("cpu"), opt.get("memory")
    if cpu is not None or mem is not None:
        return f"{cpu or '-'}cpu/{mem or '-'}mb"
    if resource_type == "Idle":
        rtype = str(rec.get("resourceType") or "")
        if "EBS" in rtype.upper() or "VOLUME" in rtype.upper():
            return "delete"
        return "stop"
    return None


def current_type(rec: dict, resource_type: str) -> str | None:
    if rec.get("currentInstanceType"):
        return str(rec["currentInstanceType"])
    if rec.get("currentMemorySize") is not None:
        return f"{rec['currentMemorySize']}MB"
    if rec.get("currentInstanceClass"):
        return str(rec["currentInstanceClass"])
    cfg = (
        rec.get("currentConfiguration")
        or rec.get("currentServiceConfiguration")
        or rec.get("currentStorageConfiguration")
        or {}
    )
    nested = cfg_type(cfg)
    if nested:
        return nested
    if resource_type == "Idle":
        return rec.get("resourceType")
    return None


def resource_arn(rec: dict) -> str | None:
    for key in (
        "instanceArn",
        "volumeArn",
        "functionArn",
        "autoScalingGroupArn",
        "serviceArn",
        "resourceArn",
    ):
        if rec.get(key):
            return rec[key]
    return None


def resource_name(rec: dict) -> str | None:
    for key in (
        "instanceName",
        "autoScalingGroupName",
        "functionArn",
        "resourceId",
    ):
        if rec.get(key):
            val = rec[key]
            if key == "functionArn":
                return str(val).rsplit("function:", 1)[-1]
            return str(val)
    arn = resource_arn(rec)
    if arn:
        return arn.rsplit("/", 1)[-1]
    return None


def lookback(rec: dict) -> int | None:
    for key in ("lookBackPeriodInDays", "lookbackPeriodInDays"):
        if rec.get(key) is not None:
            try:
                return int(rec[key])
            except (TypeError, ValueError):
                return None
    return None


def merge_key(arn: str, finding: str, recommended: str) -> tuple[str, str, str]:
    return (arn, finding, recommended)


def existing_by_key() -> dict[tuple[str, str, str], dict]:
    query = {
        "size": 10000,
        "sort": [{"@timestamp": "desc"}],
        "_source": [
            "finops.rightsizing.resource_arn",
            "finops.rightsizing.finding",
            "finops.rightsizing.recommended_type",
            "finops.rightsizing.status",
            "finops.rightsizing.owner",
            "finops.rightsizing.case_id",
            "finops.rightsizing.realized_savings",
            "finops.rightsizing.hidden_reason",
        ],
        "query": {"term": {"cloud.account.id": ACCOUNT}},
    }
    out: dict[tuple[str, str, str], dict] = {}
    for index in (LATEST_INDEX, DATA_STREAM):
        st, body = req(ES + f"/{index}/_search", "POST", query)
        if st >= 400:
            err = body.get("error", {}) if isinstance(body, dict) else body
            etype = err.get("type") if isinstance(err, dict) else err
            print(f"status lookup {index}", st, etype)
            continue
        hits = ((body.get("hits") or {}).get("hits")) or []
        print(f"status lookup {index} hits={len(hits)}")
        for hit in hits:
            rs = ((hit.get("_source") or {}).get("finops") or {}).get("rightsizing") or {}
            arn = rs.get("resource_arn")
            finding = rs.get("finding")
            rec_type = rs.get("recommended_type")
            if arn and finding and rec_type:
                key = merge_key(str(arn), str(finding), str(rec_type))
                if key not in out:
                    out[key] = rs
        if out:
            return out
    return out


def map_rec(rec: dict, default_type: str) -> dict | None:
    finding = norm_finding(
        rec.get("finding")
        or rec.get("instanceFinding")
        or rec.get("storageFinding")
    )
    if finding in DROP_FINDINGS:
        return None
    arn = resource_arn(rec)
    if not arn:
        return None
    region, account, resource = arn_parts(arn)
    account = rec.get("accountId") or account
    if account and str(account) != ACCOUNT:
        return None
    opt = first_option(rec)
    rtype = default_type
    if default_type == "Idle":
        aws_rt = str(rec.get("resourceType") or "")
        if "EBS" in aws_rt.upper() or "VOLUME" in aws_rt.upper():
            rtype = "EbsVolume"
        elif "LAMBDA" in aws_rt.upper():
            rtype = "LambdaFunction"
        elif "RDS" in aws_rt.upper():
            rtype = "RdsDBInstance"
        elif "ECS" in aws_rt.upper():
            rtype = "EcsService"
        elif "AUTO" in aws_rt.upper():
            rtype = "AutoScalingGroup"
        else:
            rtype = "Ec2Instance"
        finding = finding or "IDLE"
    recommended = recommended_type(opt, rec, default_type)
    savings = savings_value(opt) if opt else None
    if savings is None:
        savings = savings_value(rec)
    if finding in DROP_FINDINGS:
        return None
    if savings is None and not recommended:
        return None
    if not finding:
        return None
    action = ACTION_FOR_FINDING.get(finding)
    if not action:
        return None
    risk = risk_label(opt.get("performanceRisk") if opt else rec.get("performanceRisk"))
    rs: dict[str, Any] = {
        "status": "open",
        "action": action,
        "finding": finding,
        "resource_type": rtype,
        "resource_arn": arn,
        "resource_name": resource_name(rec),
        "current_type": current_type(rec, default_type),
        "recommended_type": recommended,
        "performance_risk": risk,
        "lookback_days": lookback(rec),
        "estimated_monthly_savings": savings,
        "currency": "USD",
        "source": "compute_optimizer",
    }
    if risk and str(risk).lower() == "high":
        rs["status"] = "hidden"
        rs["hidden_reason"] = "high_performance_risk"
    if rs["resource_name"] is None:
        rs.pop("resource_name")
    doc: dict[str, Any] = {
        "@timestamp": utcnow(),
        "cloud": {
            "provider": "aws",
            "account": {"id": str(account or ACCOUNT), "name": ACCOUNT_NAME},
            "region": region or REGION,
        },
        "finops": {"rightsizing": {k: v for k, v in rs.items() if v is not None}},
    }
    if rtype == "Ec2Instance" and resource and resource.startswith("i-"):
        doc["cloud"]["instance"] = {"id": resource}
        if rs.get("resource_name"):
            doc["cloud"]["instance"]["name"] = rs["resource_name"]
        if rs.get("current_type"):
            doc["cloud"]["machine"] = {"type": rs["current_type"]}
    return doc


def rds_docs(rec: dict) -> list[dict]:
    docs = []
    instance_finding = norm_finding(rec.get("instanceFinding") or rec.get("finding"))
    storage_finding = norm_finding(rec.get("storageFinding"))
    if instance_finding and instance_finding not in DROP_FINDINGS:
        one = dict(rec)
        one["finding"] = instance_finding
        one.pop("storageRecommendationOptions", None)
        mapped = map_rec(one, "RdsDBInstance")
        if mapped:
            docs.append(mapped)
    if storage_finding and storage_finding not in DROP_FINDINGS:
        one = dict(rec)
        one["finding"] = storage_finding
        one["recommendationOptions"] = rec.get("storageRecommendationOptions") or []
        one.pop("instanceRecommendationOptions", None)
        mapped = map_rec(one, "RdsDBInstance")
        if mapped:
            mapped["finops"]["rightsizing"]["resource_type"] = "RdsDBStorage"
            docs.append(mapped)
    if not docs:
        mapped = map_rec(rec, "RdsDBInstance")
        if mapped:
            docs.append(mapped)
    return docs


def apply_status_merge(doc: dict, existing: dict) -> None:
    rs = doc["finops"]["rightsizing"]
    key = merge_key(
        str(rs.get("resource_arn") or ""),
        str(rs.get("finding") or ""),
        str(rs.get("recommended_type") or ""),
    )
    prev = existing.get(key)
    if not prev:
        return
    for field in ("status", "owner", "case_id", "realized_savings", "hidden_reason"):
        if prev.get(field) not in (None, ""):
            rs[field] = prev[field]


def bulk_index(docs: list[dict]) -> None:
    if not docs:
        print("bulk skipped: 0 docs")
        return
    lines = []
    for doc in docs:
        lines.append('{"create":{}}')
        lines.append(json.dumps(doc, separators=(",", ":")))
    st, body = req(
        ES + f"/{DATA_STREAM}/_bulk?refresh=true",
        "POST",
        ("\n".join(lines) + "\n").encode(),
        content_type="application/x-ndjson",
    )
    errors = (body or {}).get("errors")
    failed = 0
    if errors:
        for item in body.get("items") or []:
            err = (item.get("create") or {}).get("error")
            if err:
                failed += 1
                if failed <= 5:
                    print("bulk error", err.get("type"), err.get("reason"))
    print("bulk", st, "docs", len(docs), "errors", failed or False)


def refresh_latest_transform() -> None:
    st, body = req(
        ES + "/_transform/finops-rightsizing-latest/_schedule_now", "POST"
    )
    if st >= 400:
        st, body = req(ES + "/_transform/finops-rightsizing-latest/_start", "POST")
    print("transform refresh", st, body if st >= 400 else "ok")


def check_enrollment(client) -> str:
    enroll = client.get_enrollment_status()
    status = enroll.get("status")
    print("enrollment", json.dumps({k: enroll[k] for k in enroll if k != "ResponseMetadata"}, default=str))
    if status != "Active":
        print(f"FAIL: enrollment status is {status}, expected Active", file=sys.stderr)
        sys.exit(2)
    return status


def collect(client) -> list[dict]:
    docs: list[dict] = []
    skipped = 0
    for method, key, rtype in APIS:
        n = 0
        kept = 0
        for rec in paginate(client, method, key):
            n += 1
            mapped_list = rds_docs(rec) if rtype == "RdsDBInstance" else [map_rec(rec, rtype)]
            for mapped in mapped_list:
                if mapped:
                    docs.append(mapped)
                    kept += 1
                else:
                    skipped += 1
        if n:
            print(f"mapped {method}: raw={n} kept={kept}")
    print(f"collect total={len(docs)} skipped={skipped}")
    return docs


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="enrollment + API counts only")
    p.add_argument("--dry-run", action="store_true", help="map recs, do not bulk")
    p.add_argument("--account", default=ACCOUNT)
    p.add_argument("--region", default=REGION)
    p.add_argument("--account-name", default=ACCOUNT_NAME)
    return p.parse_args()


def main() -> None:
    global ACCOUNT, REGION, ACCOUNT_NAME
    args = parse_args()
    ACCOUNT = args.account
    REGION = args.region
    ACCOUNT_NAME = args.account_name
    role_arn = os.environ.get("ROLE_ARN") or (
        f"arn:aws:iam::{ACCOUNT}:role/elastic-integration"
    )
    session = aws_session(ACCOUNT, role_arn)
    client = session.client("compute-optimizer", region_name=REGION)
    check_enrollment(client)
    if args.check:
        for method, key, _rtype in APIS:
            n = sum(1 for _ in paginate(client, method, key))
            print(f"check {method}: {n}")
        return
    docs = collect(client)
    existing = existing_by_key()
    for doc in docs:
        apply_status_merge(doc, existing)
    identified = sum(
        1
        for d in docs
        if d["finops"]["rightsizing"].get("status") in ("open", "in_progress")
    )
    print(f"identified_status_docs={identified} merged_keys={len(existing)}")
    if args.dry_run:
        for doc in docs[:8]:
            rs = doc["finops"]["rightsizing"]
            print(
                json.dumps(
                    {
                        "arn": rs.get("resource_arn"),
                        "finding": rs.get("finding"),
                        "action": rs.get("action"),
                        "savings": rs.get("estimated_monthly_savings"),
                        "status": rs.get("status"),
                    }
                )
            )
        print("dry-run, not bulked")
        return
    bulk_index(docs)
    refresh_latest_transform()


if __name__ == "__main__":
    # API_KEY imported to fail fast if apply.py changes the auth pattern
    if not API_KEY:
        sys.exit("ELASTIC_API_KEY missing")
    main()
