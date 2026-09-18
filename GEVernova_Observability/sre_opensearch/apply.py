#!/usr/bin/env python3
"""Apply SRE OpenSearch Domain/Node dashboards and paging rules.

Does not run FinOps apply. Enables AWS/ES on existing managed AWS policies
only when the custom CloudWatch YAML is missing the namespace.
"""
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from dashboards import build_domain_dashboard, build_fleet_dashboard, build_node_dashboard

ROOT = Path(__file__).resolve().parent
ES = "https://my-observability-project-f2e495.es.us-west-2.aws.elastic.cloud:443"
KB = "https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud"
API_KEY = os.environ.get(
    "ELASTIC_API_KEY",
    "UnBSVGJhQUJKcXNqWTh1Yzc0TEk6Vm13c2dsYUlleC1hU1U3dnBYUndvZw==",
)
SPACE = "sre"
DATA_VIEW_TITLE = "metrics-aws.cloudwatch_metrics-*"
CONNECTOR_ID = "gev-sre-server-log"
WORKFLOW_CONNECTOR_ID = "system-connector-.workflows"
WORKFLOW_ID = "gev-sre-os-rejected-search-case"
REJECTED_SEARCH_RULE_ID = "gev-sre-os-rejected-search"
WORKFLOW_TOOL_ID = "gev-sre-os-rejected-search-run"
AGENT_ID = "gev-sre-os-search-reject"


def dash_url(so_id):
    return (
        KB
        + f"/s/sre/app/dashboards#/view/{so_id}"
        + "?_g=(time:(from:now-1h,to:now))"
    )


DOMAIN_DASH_URL = dash_url("sre-opensearch-domain")
NODE_DASH_URL = dash_url("sre-opensearch-node")
FLEET_DASH_URL = dash_url("sre-opensearch-fleet")
DASH_URL = DOMAIN_DASH_URL
AWS_POLICY_IDS = [
    "9ce8892d-4166-4151-872e-583f452a396f",
    "efc7088e-9752-4420-845c-31563d193442",
    "9477478c-13e4-4c6b-909a-d8de4b3aa179",
    "e947d8c4-97ab-4f58-9921-5c3797391b1f",
    "d85991aa-4bdf-4a2d-a9b4-21eea65f2348",
]
AWS_ES_YAML = (
    "- namespace: AWS/ES\n"
    "  statistic:\n"
    "    - Average\n"
    "    - Maximum\n"
    "    - Sum"
)
ctx = ssl.create_default_context()

RUNTIME_RED = """
double v = 0.0;
if (params._source != null && params._source.containsKey('aws')) {
  def aws = params._source.aws;
  if (aws != null && aws.containsKey('es')) {
    def es = aws.es;
    if (es != null && es.containsKey('metrics')) {
      def mets = es.metrics;
      if (mets != null && mets.containsKey('ClusterStatus_red')) {
        def m = mets.ClusterStatus_red;
        if (m != null && m.containsKey('max') && m.max != null) {
          v = ((Number)m.max).doubleValue();
        }
      }
    }
  }
}
emit(v);
""".strip()

RUNTIME_INDEX = """
double v = 0.0;
if (params._source != null && params._source.containsKey('aws')) {
  def aws = params._source.aws;
  if (aws != null && aws.containsKey('es')) {
    def es = aws.es;
    if (es != null && es.containsKey('metrics')) {
      def mets = es.metrics;
      if (mets != null && mets.containsKey('IndexingRate')) {
        def m = mets.IndexingRate;
        if (m != null && m.containsKey('avg') && m.avg != null) {
          v = ((Number)m.avg).doubleValue();
        }
      }
    }
  }
}
emit(v);
""".strip()

RUNTIME_NODES = """
double v = 0.0;
if (params._source != null && params._source.containsKey('aws')) {
  def aws = params._source.aws;
  if (aws != null && aws.containsKey('es')) {
    def es = aws.es;
    if (es != null && es.containsKey('metrics')) {
      def mets = es.metrics;
      if (mets != null && mets.containsKey('Nodes')) {
        def m = mets.Nodes;
        if (m != null && m.containsKey('max') && m.max != null) {
          v = ((Number)m.max).doubleValue();
        }
      }
    }
  }
}
emit(v);
""".strip()

RUNTIME_USED = """
double used = 0.0;
double free = 0.0;
if (params._source != null && params._source.containsKey('aws')) {
  def aws = params._source.aws;
  if (aws != null && aws.containsKey('es')) {
    def es = aws.es;
    if (es != null && es.containsKey('metrics')) {
      def mets = es.metrics;
      if (mets != null && mets.containsKey('ClusterUsedSpace')) {
        def u = mets.ClusterUsedSpace;
        if (u != null && u.containsKey('max') && u.max != null) {
          used = ((Number)u.max).doubleValue();
        }
      }
      if (mets != null && mets.containsKey('FreeStorageSpace')) {
        def f = mets.FreeStorageSpace;
        if (f != null && f.containsKey('avg') && f.avg != null) {
          free = ((Number)f.avg).doubleValue();
        }
      }
    }
  }
}
if (used + free > 0) {
  emit(used / (used + free) * 100.0);
} else {
  emit(0.0);
}
""".strip()

RUNTIME_HTTP5 = """
double v = 0.0;
if (params._source != null && params._source.containsKey('aws')) {
  def aws = params._source.aws;
  if (aws != null && aws.containsKey('es')) {
    def es = aws.es;
    if (es != null && es.containsKey('metrics')) {
      def mets = es.metrics;
      if (mets != null && mets.containsKey('5xx')) {
        def m = mets['5xx'];
        if (m != null && m.containsKey('sum') && m.sum != null) {
          v = ((Number)m.sum).doubleValue();
        }
      }
    }
  }
}
emit(v);
""".strip()


def req(url, method="GET", body=None, kibana=False, content_type="application/json"):
    headers = {
        "Authorization": f"ApiKey {API_KEY}",
        "Content-Type": content_type,
    }
    if kibana:
        headers.update(
            {
                "kbn-xsrf": "true",
                "elastic-api-version": "2023-10-31",
                "x-elastic-internal-origin": "Kibana",
            }
        )
    data = None if body is None else (
        body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
    )
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, context=ctx, timeout=180) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except Exception:
            parsed = {"raw": raw[:2000]}
        return e.code, parsed


def put_policy_inputs(item, inputs):
    payload = {
        "name": item["name"],
        "description": item.get("description") or "",
        "namespace": item.get("namespace") or "default",
        "package": item["package"],
        "inputs": inputs,
        "vars": item.get("vars") or {},
        "cloud_connector": item.get("cloud_connector"),
    }
    if item.get("var_group_selections"):
        payload["var_group_selections"] = item["var_group_selections"]
    return req(
        KB + f"/api/fleet/managed_integrations/{item['id']}",
        "PUT",
        payload,
        kibana=True,
    )


def enable_aws_es():
    for pid in AWS_POLICY_IDS:
        st, body = req(KB + f"/api/fleet/managed_integrations/{pid}", kibana=True)
        item = body.get("item") or body
        if st != 200 or not item.get("id"):
            print("policy get fail", pid, st, body.get("message") or body)
            continue
        inputs = item.get("inputs") or {}
        cw = inputs.get("cloudwatch-aws/metrics") or {}
        streams = cw.setdefault("streams", {})
        stream = streams.setdefault("aws.cloudwatch_metrics", {})
        vars_ = stream.setdefault("vars", {})
        metrics = vars_.get("metrics")
        yaml = metrics.get("value") if isinstance(metrics, dict) else metrics
        yaml = yaml if isinstance(yaml, str) else ""
        cw["enabled"] = True
        stream["enabled"] = True
        if "AWS/ES" in yaml:
            print("aws.es already", item.get("name"), "connector", bool(item.get("cloud_connector")))
            continue
        new_yaml = yaml.rstrip() + "\n" + AWS_ES_YAML + "\n"
        if isinstance(metrics, dict):
            vars_["metrics"] = dict(metrics)
            vars_["metrics"]["value"] = new_yaml
        else:
            vars_["metrics"] = {"type": "yaml", "value": new_yaml}
        inputs["cloudwatch-aws/metrics"] = cw
        pst, pbody = put_policy_inputs(item, inputs)
        print(
            "aws.es enable",
            item.get("name"),
            pst,
            (pbody.get("item") or pbody).get("id") if pst < 400 else pbody.get("message") or pbody,
        )


def verify_ingest():
    q = (
        "FROM metrics-aws.cloudwatch_metrics-*\n"
        '| WHERE @timestamp > NOW() - 6 hours AND aws.cloudwatch.namespace == "AWS/ES"\n'
        "| STATS docs = COUNT(*),\n"
        "        domains = COUNT_DISTINCT(aws.dimensions.DomainName),\n"
        "        nodes = COUNT_DISTINCT(aws.dimensions.NodeId),\n"
        "        jvm = MAX(aws.es.metrics.JVMMemoryPressure.max)\n"
        "    BY cloud.account.id, aws.dimensions.DomainName\n"
        "| SORT docs DESC"
    )
    st, body = req(ES + "/_query", "POST", {"query": q})
    rows = body.get("values") or []
    print("esql aws.es", st, "rows", len(rows))
    for row in rows[:12]:
        print(" ", row)
    return len(rows) > 0


def ensure_server_log_connector():
    st, body = req(KB + f"/s/{SPACE}/api/actions/connector/{CONNECTOR_ID}", kibana=True)
    if st == 200 and body.get("id"):
        print("connector exists", CONNECTOR_ID)
        return
    st, body = req(
        KB + f"/s/{SPACE}/api/actions/connector/{CONNECTOR_ID}",
        "POST",
        {
            "name": "SRE server log",
            "connector_type_id": ".server-log",
            "config": {},
            "secrets": {},
        },
        kibana=True,
    )
    print("connector create", st, body.get("id") or body.get("message") or body)


def ensure_space():
    st, body = req(KB + f"/api/spaces/space/{SPACE}", kibana=True)
    if st == 200 and (body.get("id") == SPACE):
        print("space exists", SPACE)
        return
    st, body = req(
        KB + "/api/spaces/space",
        "POST",
        {
            "id": SPACE,
            "name": "SRE",
            "description": "SRE OpenSearch Domain/Node views and paging rules",
            "color": "#AA6556",
            "initials": "SR",
            "disabledFeatures": [],
        },
        kibana=True,
    )
    print("space create", st, body.get("id") or body.get("message") or body)


def find_data_view_id():
    st, existing = req(KB + f"/s/{SPACE}/api/data_views", kibana=True)
    if st != 200:
        return None
    views = existing.get("data_view") or existing.get("data_views") or []
    for dv in views:
        if dv.get("title") == DATA_VIEW_TITLE:
            return dv.get("id")
    return None


def runtime_fields():
    def rf(script):
        return {"type": "double", "script": {"source": script}}

    return {
        "sre.es.cluster_red": rf(RUNTIME_RED),
        "sre.es.indexing_rate": rf(RUNTIME_INDEX),
        "sre.es.nodes": rf(RUNTIME_NODES),
        "sre.es.used_pct": rf(RUNTIME_USED),
        "sre.es.http_5xx": rf(RUNTIME_HTTP5),
    }


def ensure_data_view():
    dv_id = find_data_view_id()
    payload = {
        "data_view": {
            "title": DATA_VIEW_TITLE,
            "name": "AWS OpenSearch CloudWatch",
            "timeFieldName": "@timestamp",
            "allowNoIndex": True,
            "runtimeFieldMap": runtime_fields(),
        }
    }
    if dv_id:
        st, body = req(
            KB + f"/s/{SPACE}/api/data_views/data_view/{dv_id}",
            "POST",
            payload,
            kibana=True,
        )
        print("data_view update", st, dv_id if st < 400 else body.get("message") or body)
        return dv_id
    st, body = req(
        KB + f"/s/{SPACE}/api/data_views/data_view",
        "POST",
        payload,
        kibana=True,
    )
    dv_id = ((body.get("data_view") or {}).get("id") if isinstance(body, dict) else None)
    print("data_view create", st, dv_id or body.get("message") or body)
    return dv_id


def put_dashboard(so_id, attributes, references):
    st, body = req(
        KB + f"/s/{SPACE}/api/saved_objects/dashboard/{so_id}?overwrite=true",
        "POST",
        {"attributes": attributes, "references": references},
        kibana=True,
    )
    print("dashboard", so_id, st, body.get("id") or body.get("message") or body)
    return st


DOMAIN_GROUP = ["aws.dimensions.DomainName", "cloud.account.id", "cloud.region"]
NODE_GROUP = [
    "aws.dimensions.DomainName",
    "aws.dimensions.NodeId",
    "cloud.account.id",
    "cloud.region",
]
DOMAIN_KQL = 'aws.cloudwatch.namespace : "AWS/ES" and not aws.dimensions.NodeId : *'
NODE_KQL = 'aws.cloudwatch.namespace : "AWS/ES" and aws.dimensions.NodeId : *'
RULE_TAGS = ["sre", "ge-vernova", "opensearch", "aws-es"]
CLASSIC_RULE_IDS = [
    "gev-sre-os-cluster-red",
    "gev-sre-os-cluster-yellow",
    "gev-sre-os-jvm-pressure",
    "gev-sre-os-jvm-pressure-crit",
    "gev-sre-os-rejected-search",
    "gev-sre-os-rejected-write",
    "gev-sre-os-writes-blocked",
    "gev-sre-os-snapshot-failure",
    "gev-sre-os-cpu",
    "gev-sre-os-cpu-crit",
    "gev-sre-os-used-space",
    "gev-sre-os-used-space-crit",
    "gev-sre-os-jvm-pressure-obs",
]


def enable_alerting_v2():
    st, body = req(
        KB + "/internal/kibana/global_settings",
        "POST",
        {"changes": {"alerting:v2:enabled": True}},
        kibana=True,
    )
    setting = ((body.get("settings") or {}).get("alerting:v2:enabled") or {})
    print("alerting v2", st, setting.get("userValue"))


def metric(name, agg, field):
    return {"name": name, "aggType": agg, "field": field}


def criterion(comparator, metrics, threshold, equation=None):
    item = {
        "comparator": comparator,
        "metrics": metrics,
        "threshold": threshold,
        "timeSize": 15,
        "timeUnit": "m",
    }
    if equation:
        item["equation"] = equation
    return item


def workflow_rule_action():
    return {
        "group": "custom_threshold.fired",
        "id": WORKFLOW_CONNECTOR_ID,
        "params": {
            "subAction": "run",
            "subActionParams": {
                "workflowId": WORKFLOW_ID,
                "summaryMode": False,
                "alertStates": {
                    "new": True,
                    "ongoing": False,
                    "recovered": True,
                },
            },
        },
        "frequency": {
            "summary": False,
            "notify_when": "onActionGroupChange",
            "throttle": None,
        },
    }


def custom_threshold_rule(
    name, message, criteria, kql, group_by, dv_id, dash=None, extra_actions=None
):
    link = dash or DOMAIN_DASH_URL
    actions = [
        {
            "group": "custom_threshold.fired",
            "id": CONNECTOR_ID,
            "params": {
                "message": message + " Dashboard: " + link,
                "level": "info",
            },
            "frequency": {
                "summary": False,
                "notify_when": "onActionGroupChange",
                "throttle": None,
            },
        }
    ]
    if extra_actions:
        actions.extend(extra_actions)
    return {
        "name": name,
        "tags": RULE_TAGS,
        "consumer": "observability",
        "rule_type_id": "observability.rules.custom_threshold",
        "schedule": {"interval": "5m"},
        "enabled": True,
        "params": {
            "criteria": criteria,
            "alertOnNoData": False,
            "alertOnGroupDisappear": False,
            "groupBy": group_by,
            "searchConfiguration": {
                "index": dv_id,
                "query": {"language": "kuery", "query": kql},
            },
        },
        "actions": actions,
    }


def v2_rule(name, description, esql, group_fields, dashboard_id="sre-opensearch-domain"):
    return {
        "kind": "alert",
        "metadata": {
            "name": name,
            "description": description,
            "tags": RULE_TAGS,
        },
        "time_field": "@timestamp",
        "schedule": {"every": "5m", "lookback": "15m"},
        "recovery_strategy": "no_breach",
        "no_data_strategy": "none",
        "query": {"format": "standalone", "breach": {"query": esql}},
        "grouping": {"fields": group_fields},
        "state_transition": {"pending_count": 1, "recovering_count": 1},
        "artifacts": [
            {
                "id": "domain-dash",
                "type": "dashboard",
                "data": {"dashboard_id": dashboard_id},
            }
        ],
    }


def timed_esql(body):
    return (
        "FROM metrics-aws.cloudwatch_metrics-*\n"
        "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
        + body
    )


def delete_classic_rule(rule_id):
    st, existing = req(KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}", kibana=True)
    if st != 200 or not existing.get("id"):
        return
    rtype = existing.get("rule_type_id")
    if rtype == "observability.rules.custom_threshold":
        return
    dst, _ = req(KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}", "DELETE", kibana=True)
    print("alert delete classic", rule_id, rtype, dst)


def put_ct_rule(rule_id, payload):
    st, existing = req(KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}", kibana=True)
    if st == 200 and existing.get("id"):
        dst, _ = req(KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}", "DELETE", kibana=True)
        print("alert replace", rule_id, existing.get("rule_type_id"), dst)
    st, body = req(
        KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}",
        "POST",
        payload,
        kibana=True,
    )
    print(
        "alert create",
        rule_id,
        st,
        body.get("id") or body.get("message") or body,
        body.get("rule_type_id"),
    )
    if st >= 400:
        (ROOT / "kibana" / f"{rule_id}-error.json").write_text(
            json.dumps(body, indent=2)[:4000]
        )
    return st


def put_v2_rule(rule_id, payload):
    st, body = req(
        KB + f"/s/{SPACE}/api/alerting/v2/rules/{rule_id}",
        "PUT",
        payload,
        kibana=True,
    )
    print(
        "v2 create",
        rule_id,
        st,
        body.get("id") or body.get("message") or body.get("code") or body,
    )
    if st >= 400:
        (ROOT / "kibana" / f"{rule_id}-v2-error.json").write_text(
            json.dumps(body, indent=2)[:4000]
        )
    return st


def rule_specs(dv_id):
    jvm_crit = [
        criterion(">", [metric("A", "max", "aws.es.metrics.JVMMemoryPressure.max")], [80]),
        criterion(">", [metric("A", "max", "aws.es.metrics.JVMMemoryPressure.max")], [92]),
    ]
    used = [
        criterion(
            ">",
            [
                metric("A", "max", "aws.es.metrics.ClusterUsedSpace.max"),
                metric("B", "avg", "aws.es.metrics.FreeStorageSpace.avg"),
            ],
            [85],
            "(A / (A + B)) * 100",
        ),
        criterion(
            ">",
            [
                metric("A", "max", "aws.es.metrics.ClusterUsedSpace.max"),
                metric("B", "avg", "aws.es.metrics.FreeStorageSpace.avg"),
            ],
            [90],
            "(A / (A + B)) * 100",
        ),
    ]
    return [
        {
            "id": "gev-sre-os-cluster-red",
            "name": "[SRE] OpenSearch cluster red",
            "message": "P1 OpenSearch cluster red (green=0 and yellow=0 for 15m). Clone of Splunk ClusterStatus.red.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch cluster red",
                "P1 OpenSearch cluster red (green=0 and yellow=0 for 15m). Clone of Splunk ClusterStatus.red.",
                [
                    criterion(
                        "<",
                        [metric("A", "max", "aws.es.metrics.ClusterStatus_green.max")],
                        [1],
                    ),
                    criterion(
                        "<",
                        [metric("A", "max", "aws.es.metrics.ClusterStatus_yellow.max")],
                        [1],
                    ),
                ],
                DOMAIN_KQL,
                DOMAIN_GROUP,
                dv_id,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch cluster red",
                "P1 OpenSearch cluster red (green=0 and yellow=0 for 15m). Clone of Splunk ClusterStatus.red.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NULL\n'
                    "| STATS green = MAX(aws.es.metrics.ClusterStatus_green.max),\n"
                    "        yellow = MAX(aws.es.metrics.ClusterStatus_yellow.max)\n"
                    "    BY aws.dimensions.DomainName, cloud.account.id, cloud.region\n"
                    "| WHERE green == 0 AND yellow == 0\n"
                    "| KEEP aws.dimensions.DomainName, cloud.account.id, cloud.region, green, yellow"
                ),
                DOMAIN_GROUP,
            ),
        },
        {
            "id": "gev-sre-os-cluster-yellow",
            "name": "[SRE] OpenSearch cluster yellow",
            "message": "P2 OpenSearch cluster yellow > 0 for 15m. Clone of Splunk ClusterStatus.yellow.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch cluster yellow",
                "P2 OpenSearch cluster yellow > 0 for 15m. Clone of Splunk ClusterStatus.yellow.",
                [
                    criterion(
                        ">",
                        [metric("A", "max", "aws.es.metrics.ClusterStatus_yellow.max")],
                        [0],
                    )
                ],
                DOMAIN_KQL,
                DOMAIN_GROUP,
                dv_id,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch cluster yellow",
                "P2 OpenSearch cluster yellow > 0 for 15m. Clone of Splunk ClusterStatus.yellow.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NULL\n'
                    "| STATS yellow = MAX(aws.es.metrics.ClusterStatus_yellow.max)\n"
                    "    BY aws.dimensions.DomainName, cloud.account.id, cloud.region\n"
                    "| WHERE yellow > 0\n"
                    "| KEEP aws.dimensions.DomainName, cloud.account.id, cloud.region, yellow"
                ),
                DOMAIN_GROUP,
            ),
        },
        {
            "id": "gev-sre-os-jvm-pressure",
            "name": "[SRE] OpenSearch JVM memory pressure > 80",
            "message": "P2 OpenSearch JVMMemoryPressure > 80 for 15m (P1 sibling fires at 92).",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch JVM memory pressure > 80",
                "P2 OpenSearch JVMMemoryPressure > 80 for 15m (P1 sibling fires at 92). Not in Splunk AWS/ES detectors.",
                [jvm_crit[0]],
                NODE_KQL,
                NODE_GROUP,
                dv_id,
                NODE_DASH_URL,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch JVM memory pressure > 80",
                "P2 OpenSearch JVMMemoryPressure > 80 for 15m (P1 sibling fires at 92).",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NOT NULL\n'
                    "| STATS jvm = MAX(aws.es.metrics.JVMMemoryPressure.max)\n"
                    "    BY aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region\n"
                    "| WHERE jvm > 80\n"
                    "| KEEP aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region, jvm"
                ),
                NODE_GROUP,
                "sre-opensearch-node",
            ),
        },
        {
            "id": "gev-sre-os-jvm-pressure-crit",
            "name": "[SRE] OpenSearch JVM memory pressure > 92",
            "message": "P1 OpenSearch JVMMemoryPressure > 92 for 15m.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch JVM memory pressure > 92",
                "P1 OpenSearch JVMMemoryPressure > 92 for 15m.",
                [jvm_crit[1]],
                NODE_KQL,
                NODE_GROUP,
                dv_id,
                NODE_DASH_URL,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch JVM memory pressure > 92",
                "P1 OpenSearch JVMMemoryPressure > 92 for 15m.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NOT NULL\n'
                    "| STATS jvm = MAX(aws.es.metrics.JVMMemoryPressure.max)\n"
                    "    BY aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region\n"
                    "| WHERE jvm > 92\n"
                    "| KEEP aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region, jvm"
                ),
                NODE_GROUP,
                "sre-opensearch-node",
            ),
        },
        {
            "id": "gev-sre-os-rejected-search",
            "name": "[SRE] OpenSearch search threadpool rejected",
            "message": "P2 OpenSearch ThreadpoolSearchRejected > 0 over 15m.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch search threadpool rejected",
                "P2 OpenSearch ThreadpoolSearchRejected > 0 over 15m. Not in Splunk AWS/ES detectors.",
                [
                    criterion(
                        ">",
                        [metric("A", "sum", "aws.es.metrics.ThreadpoolSearchRejected.sum")],
                        [0],
                    )
                ],
                NODE_KQL,
                NODE_GROUP,
                dv_id,
                NODE_DASH_URL,
                extra_actions=[workflow_rule_action()],
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch search threadpool rejected",
                "P2 OpenSearch ThreadpoolSearchRejected > 0 over 15m. Not in Splunk AWS/ES detectors.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NOT NULL\n'
                    "| STATS rej = SUM(aws.es.metrics.ThreadpoolSearchRejected.sum)\n"
                    "    BY aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region\n"
                    "| WHERE rej > 0\n"
                    "| KEEP aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region, rej"
                ),
                NODE_GROUP,
                "sre-opensearch-node",
            ),
        },
        {
            "id": "gev-sre-os-rejected-write",
            "name": "[SRE] OpenSearch write threadpool rejected",
            "message": "P2 OpenSearch ThreadpoolWriteRejected > 0 over 15m.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch write threadpool rejected",
                "P2 OpenSearch ThreadpoolWriteRejected > 0 over 15m. Sibling of search rejects.",
                [
                    criterion(
                        ">",
                        [metric("A", "sum", "aws.es.metrics.ThreadpoolWriteRejected.sum")],
                        [0],
                    )
                ],
                NODE_KQL,
                NODE_GROUP,
                dv_id,
                NODE_DASH_URL,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch write threadpool rejected",
                "P2 OpenSearch ThreadpoolWriteRejected > 0 over 15m. Sibling of search rejects.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NOT NULL\n'
                    "| STATS rej = SUM(aws.es.metrics.ThreadpoolWriteRejected.sum)\n"
                    "    BY aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region\n"
                    "| WHERE rej > 0\n"
                    "| KEEP aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region, rej"
                ),
                NODE_GROUP,
                "sre-opensearch-node",
            ),
        },
        {
            "id": "gev-sre-os-writes-blocked",
            "name": "[SRE] OpenSearch index writes blocked",
            "message": "P1 OpenSearch ClusterIndexWritesBlocked > 0 for 15m.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch index writes blocked",
                "P1 OpenSearch ClusterIndexWritesBlocked > 0 for 15m (flood-stage / write block).",
                [
                    criterion(
                        ">",
                        [metric("A", "max", "aws.es.metrics.ClusterIndexWritesBlocked.max")],
                        [0],
                    )
                ],
                DOMAIN_KQL,
                DOMAIN_GROUP,
                dv_id,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch index writes blocked",
                "P1 OpenSearch ClusterIndexWritesBlocked > 0 for 15m (flood-stage / write block).",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NULL\n'
                    "| STATS blocked = MAX(aws.es.metrics.ClusterIndexWritesBlocked.max)\n"
                    "    BY aws.dimensions.DomainName, cloud.account.id, cloud.region\n"
                    "| WHERE blocked > 0\n"
                    "| KEEP aws.dimensions.DomainName, cloud.account.id, cloud.region, blocked"
                ),
                DOMAIN_GROUP,
            ),
        },
        {
            "id": "gev-sre-os-snapshot-failure",
            "name": "[SRE] OpenSearch automated snapshot failure",
            "message": "P2 OpenSearch AutomatedSnapshotFailure > 0 for 15m.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch automated snapshot failure",
                "P2 OpenSearch AutomatedSnapshotFailure > 0 for 15m.",
                [
                    criterion(
                        ">",
                        [metric("A", "max", "aws.es.metrics.AutomatedSnapshotFailure.max")],
                        [0],
                    )
                ],
                DOMAIN_KQL,
                DOMAIN_GROUP,
                dv_id,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch automated snapshot failure",
                "P2 OpenSearch AutomatedSnapshotFailure > 0 for 15m.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NULL\n'
                    "| STATS snap = MAX(aws.es.metrics.AutomatedSnapshotFailure.max)\n"
                    "    BY aws.dimensions.DomainName, cloud.account.id, cloud.region\n"
                    "| WHERE snap > 0\n"
                    "| KEEP aws.dimensions.DomainName, cloud.account.id, cloud.region, snap"
                ),
                DOMAIN_GROUP,
            ),
        },
        {
            "id": "gev-sre-os-cpu",
            "name": "[SRE] OpenSearch CPU > 90",
            "message": "P2 OpenSearch CPUUtilization > 90 for 15m (P1 sibling fires at 95).",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch CPU > 90",
                "P2 OpenSearch CPUUtilization > 90 for 15m (P1 sibling fires at 95). Clone of Splunk CPUUtilization.",
                [
                    criterion(
                        ">",
                        [metric("A", "max", "aws.es.metrics.CPUUtilization.avg")],
                        [90],
                    )
                ],
                NODE_KQL,
                NODE_GROUP,
                dv_id,
                NODE_DASH_URL,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch CPU > 90",
                "P2 OpenSearch CPUUtilization > 90 for 15m (P1 sibling fires at 95). Clone of Splunk CPUUtilization.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NOT NULL\n'
                    "| STATS cpu = MAX(aws.es.metrics.CPUUtilization.avg)\n"
                    "    BY aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region\n"
                    "| WHERE cpu > 90\n"
                    "| KEEP aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region, cpu"
                ),
                NODE_GROUP,
                "sre-opensearch-node",
            ),
        },
        {
            "id": "gev-sre-os-cpu-crit",
            "name": "[SRE] OpenSearch CPU > 95",
            "message": "P1 OpenSearch CPUUtilization > 95 for 15m.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch CPU > 95",
                "P1 OpenSearch CPUUtilization > 95 for 15m. Clone of Splunk CPUUtilization critical.",
                [
                    criterion(
                        ">",
                        [metric("A", "max", "aws.es.metrics.CPUUtilization.avg")],
                        [95],
                    )
                ],
                NODE_KQL,
                NODE_GROUP,
                dv_id,
                NODE_DASH_URL,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch CPU > 95",
                "P1 OpenSearch CPUUtilization > 95 for 15m. Clone of Splunk CPUUtilization critical.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NOT NULL\n'
                    "| STATS cpu = MAX(aws.es.metrics.CPUUtilization.avg)\n"
                    "    BY aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region\n"
                    "| WHERE cpu > 95\n"
                    "| KEEP aws.dimensions.DomainName, aws.dimensions.NodeId, cloud.account.id, cloud.region, cpu"
                ),
                NODE_GROUP,
                "sre-opensearch-node",
            ),
        },
        {
            "id": "gev-sre-os-used-space",
            "name": "[SRE] OpenSearch used-space % > 85",
            "message": "P2 OpenSearch used-space % > 85 for 15m (USW Splunk formula).",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch used-space % > 85",
                "P2 OpenSearch used-space % > 85 for 15m (USW Splunk formula). P1 sibling fires at 90.",
                [used[0]],
                DOMAIN_KQL,
                DOMAIN_GROUP,
                dv_id,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch used-space % > 85",
                "P2 OpenSearch used-space % > 85 for 15m (USW Splunk formula). P1 sibling fires at 90.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NULL\n'
                    "| STATS used = MAX(aws.es.metrics.ClusterUsedSpace.max),\n"
                    "        free = AVG(aws.es.metrics.FreeStorageSpace.avg)\n"
                    "    BY aws.dimensions.DomainName, cloud.account.id, cloud.region\n"
                    "| EVAL pct = used / (used + free) * 100\n"
                    "| WHERE pct > 85\n"
                    "| KEEP aws.dimensions.DomainName, cloud.account.id, cloud.region, used, free, pct"
                ),
                DOMAIN_GROUP,
            ),
        },
        {
            "id": "gev-sre-os-used-space-crit",
            "name": "[SRE] OpenSearch used-space % > 90",
            "message": "P1 OpenSearch used-space % > 90 for 15m. Clone of Splunk ClusterUsedSpace critical.",
            "ct": custom_threshold_rule(
                "[SRE] OpenSearch used-space % > 90",
                "P1 OpenSearch used-space % > 90 for 15m. Clone of Splunk ClusterUsedSpace critical.",
                [used[1]],
                DOMAIN_KQL,
                DOMAIN_GROUP,
                dv_id,
            ),
            "v2": v2_rule(
                "[SRE] OpenSearch used-space % > 90",
                "P1 OpenSearch used-space % > 90 for 15m. Clone of Splunk ClusterUsedSpace critical.",
                timed_esql(
                    '| WHERE aws.cloudwatch.namespace == "AWS/ES" AND aws.dimensions.NodeId IS NULL\n'
                    "| STATS used = MAX(aws.es.metrics.ClusterUsedSpace.max),\n"
                    "        free = AVG(aws.es.metrics.FreeStorageSpace.avg)\n"
                    "    BY aws.dimensions.DomainName, cloud.account.id, cloud.region\n"
                    "| EVAL pct = used / (used + free) * 100\n"
                    "| WHERE pct > 90\n"
                    "| KEEP aws.dimensions.DomainName, cloud.account.id, cloud.region, used, free, pct"
                ),
                DOMAIN_GROUP,
            ),
        },
    ]


def ensure_cases_configure():
    payload = json.loads((ROOT / "kibana" / "cases" / "configure.json").read_text())
    st, body = req(
        KB + f"/s/{SPACE}/api/cases/configure?owner=observability",
        kibana=True,
    )
    existing = None
    if st == 200:
        if isinstance(body, list) and body:
            existing = body[0]
        elif isinstance(body, dict) and body.get("id"):
            existing = body
    if existing and existing.get("id"):
        patch = dict(payload)
        patch.pop("owner", None)
        patch["version"] = existing["version"]
        st, body = req(
            KB + f"/s/{SPACE}/api/cases/configure/{existing['id']}",
            "PATCH",
            patch,
            kibana=True,
        )
        print(
            "cases configure patch",
            st,
            body.get("id") or body.get("message") or body,
        )
        return body if st < 400 else existing
    st, body = req(
        KB + f"/s/{SPACE}/api/cases/configure",
        "POST",
        payload,
        kibana=True,
    )
    print(
        "cases configure create",
        st,
        body.get("id") if isinstance(body, dict) else body,
        body.get("message") if isinstance(body, dict) and st >= 400 else "",
    )
    return body


def upsert_workflow():
    yaml_text = (ROOT / "kibana" / "workflows" / f"{WORKFLOW_ID}.yaml").read_text()
    st, body = req(
        KB + f"/s/{SPACE}/api/workflows/workflow/{WORKFLOW_ID}",
        "PUT",
        {"yaml": yaml_text},
        kibana=True,
    )
    if st == 404:
        st, body = req(
            KB + f"/s/{SPACE}/api/workflows/workflow",
            "POST",
            {"id": WORKFLOW_ID, "yaml": yaml_text},
            kibana=True,
        )
    print(
        "workflow",
        WORKFLOW_ID,
        st,
        "valid" if isinstance(body, dict) and body.get("valid") else body.get("message") if isinstance(body, dict) else body,
        "enabled" if isinstance(body, dict) and body.get("enabled") else "",
    )
    if isinstance(body, dict) and body.get("valid") is False:
        print("workflow invalid", json.dumps(body, indent=2)[:4000])
    return body


def _agent_builder_payload(path, drop=()):
    raw = json.loads(path.read_text())
    for key in drop:
        raw.pop(key, None)
    return raw


def upsert_workflow_tool():
    src = ROOT / "kibana" / "tools" / f"{WORKFLOW_TOOL_ID}.json"
    create_body = _agent_builder_payload(src)
    update_body = {k: v for k, v in create_body.items() if k not in ("id", "type")}
    st, body = req(
        KB + f"/s/{SPACE}/api/agent_builder/tools/{WORKFLOW_TOOL_ID}",
        kibana=True,
    )
    if st == 200:
        st, body = req(
            KB + f"/s/{SPACE}/api/agent_builder/tools/{WORKFLOW_TOOL_ID}",
            "PUT",
            update_body,
            kibana=True,
        )
    else:
        st, body = req(
            KB + f"/s/{SPACE}/api/agent_builder/tools",
            "POST",
            create_body,
            kibana=True,
        )
    print(
        "workflow tool",
        WORKFLOW_TOOL_ID,
        st,
        body.get("id") if isinstance(body, dict) else body,
        body.get("message") if isinstance(body, dict) and st >= 400 else "",
    )
    return body


def upsert_agent():
    src = ROOT / "kibana" / "agents" / f"{AGENT_ID}.json"
    create_body = _agent_builder_payload(src)
    update_body = {k: v for k, v in create_body.items() if k not in ("id", "type")}
    st, body = req(
        KB + f"/s/{SPACE}/api/agent_builder/agents/{AGENT_ID}",
        kibana=True,
    )
    if st == 200:
        st, body = req(
            KB + f"/s/{SPACE}/api/agent_builder/agents/{AGENT_ID}",
            "PUT",
            update_body,
            kibana=True,
        )
    else:
        st, body = req(
            KB + f"/s/{SPACE}/api/agent_builder/agents",
            "POST",
            create_body,
            kibana=True,
        )
    print(
        "agent",
        AGENT_ID,
        st,
        body.get("id") if isinstance(body, dict) else body,
        body.get("message") if isinstance(body, dict) and st >= 400 else "",
    )
    return body


def _action_write_payload(action):
    item = {
        "group": action.get("group") or "custom_threshold.fired",
        "id": action["id"],
        "params": action.get("params") or {},
    }
    if action.get("frequency") is not None:
        item["frequency"] = action["frequency"]
    if action.get("uuid"):
        item["uuid"] = action["uuid"]
    return item


def attach_workflow_to_rule(rule_id=REJECTED_SEARCH_RULE_ID):
    st, existing = req(
        KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}",
        kibana=True,
    )
    if st != 200 or not existing.get("id"):
        print("rule missing; skip workflow action", rule_id, st)
        return st
    actions = []
    for action in existing.get("actions") or []:
        if action.get("id") == WORKFLOW_CONNECTOR_ID:
            continue
        actions.append(_action_write_payload(action))
    actions.append(workflow_rule_action())
    payload = {
        "name": existing["name"],
        "tags": existing.get("tags") or [],
        "schedule": existing["schedule"],
        "params": existing["params"],
        "actions": actions,
    }
    st, body = req(
        KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}",
        "PUT",
        payload,
        kibana=True,
    )
    print(
        "rule workflow action",
        rule_id,
        st,
        [a.get("id") for a in (body.get("actions") or [])]
        if st < 400
        else body.get("message") or body,
    )
    return st


def ensure_domain_endpoint_index():
    spec = json.loads(
        (ROOT / "elasticsearch" / "domain-endpoints-index.json").read_text()
    )
    index = spec["index"]
    st, body = req(ES + f"/{index}", kibana=False)
    if st == 200:
        print("domain endpoints index exists", index)
        return index
    st, body = req(
        ES + f"/{index}",
        "PUT",
        {"mappings": spec["mappings"]},
    )
    print(
        "domain endpoints index",
        index,
        st,
        body.get("acknowledged") if isinstance(body, dict) else body,
    )
    sample = json.loads(
        (ROOT / "elasticsearch" / "domain-endpoint.sample.json").read_text()
    )
    st, body = req(
        ES + f"/{index}/_create/_example",
        "PUT",
        sample,
    )
    if st in (200, 201):
        print("domain endpoints sample", st)
    elif st == 409:
        print("domain endpoints sample exists")
    else:
        print("domain endpoints sample", st, body.get("error") or body)
    return index


def install_p0():
    """Cases config + search-rejected workflow + rule action. Does not rebuild dashboards."""
    (ROOT / "kibana" / "cases").mkdir(parents=True, exist_ok=True)
    (ROOT / "kibana" / "workflows").mkdir(parents=True, exist_ok=True)
    (ROOT / "kibana" / "tools").mkdir(parents=True, exist_ok=True)
    (ROOT / "kibana" / "agents").mkdir(parents=True, exist_ok=True)
    (ROOT / "elasticsearch").mkdir(parents=True, exist_ok=True)
    ensure_space()
    ensure_cases_configure()
    ensure_domain_endpoint_index()
    upsert_workflow()
    upsert_workflow_tool()
    upsert_agent()
    attach_workflow_to_rule()
    dv_id = find_data_view_id()
    if dv_id:
        spec = next(
            s for s in rule_specs(dv_id) if s["id"] == REJECTED_SEARCH_RULE_ID
        )
        (ROOT / "kibana" / f"{REJECTED_SEARCH_RULE_ID}.json").write_text(
            json.dumps(spec["ct"], indent=2)
        )


def install_rules(dv_id=None):
    (ROOT / "kibana").mkdir(exist_ok=True)
    enable_alerting_v2()
    dv_id = dv_id or find_data_view_id()
    if not dv_id:
        print("no data view; skip rules")
        return
    for rid in CLASSIC_RULE_IDS:
        delete_classic_rule(rid)
    leftover, _ = req(
        KB + f"/s/{SPACE}/api/alerting/rule/gev-sre-os-jvm-pressure-obs",
        "DELETE",
        kibana=True,
    )
    if leftover < 400:
        print("alert delete leftover gev-sre-os-jvm-pressure-obs", leftover)
    for spec in rule_specs(dv_id):
        (ROOT / "kibana" / f"{spec['id']}.json").write_text(
            json.dumps(spec["ct"], indent=2)
        )
        (ROOT / "kibana" / f"{spec['id']}-v2.json").write_text(
            json.dumps(spec["v2"], indent=2)
        )
        put_ct_rule(spec["id"], spec["ct"])
        put_v2_rule(spec["id"], spec["v2"])


def main():
    (ROOT / "kibana").mkdir(exist_ok=True)
    enable_aws_es()
    verify_ingest()
    ensure_space()
    ensure_server_log_connector()
    dv_id = ensure_data_view()
    if not dv_id:
        print("no data view; skip dashboards")
        return
    attrs, refs = build_domain_dashboard(dv_id)
    put_dashboard("sre-opensearch-domain", attrs, refs)
    (ROOT / "kibana" / "sre-opensearch-domain.json").write_text(
        json.dumps({"attributes": attrs, "references": refs}, indent=2)
    )
    attrs2, refs2 = build_node_dashboard(dv_id)
    put_dashboard("sre-opensearch-node", attrs2, refs2)
    (ROOT / "kibana" / "sre-opensearch-node.json").write_text(
        json.dumps({"attributes": attrs2, "references": refs2}, indent=2)
    )
    attrs3, refs3 = build_fleet_dashboard(dv_id)
    put_dashboard("sre-opensearch-fleet", attrs3, refs3)
    (ROOT / "kibana" / "sre-opensearch-fleet.json").write_text(
        json.dumps({"attributes": attrs3, "references": refs3}, indent=2)
    )
    install_p0()
    install_rules(dv_id)


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["p0"]:
        install_p0()
    else:
        main()
