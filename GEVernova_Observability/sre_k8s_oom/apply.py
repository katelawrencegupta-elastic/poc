#!/usr/bin/env python3
"""Apply SRE K8s OOM / crash-burst detection: dashboard, v2 ES|QL rules, workflow.

Does not patch live Deployments. Wave 0 OTel status.reason must be rolled out
separately via elastic-otel-values-live.yaml / otel.yaml.

Usage:
  ELASTIC_API_KEY=... python3 apply.py              # full install
  ELASTIC_API_KEY=... python3 apply.py dashboard    # dashboard only
  ELASTIC_API_KEY=... python3 apply.py rules        # rules only
  ELASTIC_API_KEY=... python3 apply.py workflow     # workflow + agent + tool
  ELASTIC_API_KEY=... python3 apply.py verify
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dashboards import DASHBOARD_ID, build_oom_crash_dashboard, verify_query_specs

ROOT = Path(__file__).resolve().parent
ES = "https://my-observability-project-f2e495.es.us-west-2.aws.elastic.cloud:443"
KB = "https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud"
API_KEY = os.environ.get(
    "ELASTIC_API_KEY",
    "UnBSVGJhQUJKcXNqWTh1Yzc0TEk6Vm13c2dsYUlleC1hU1U3dnBYUndvZw==",
)
SPACE = "sre"
WORKFLOW_ID = "gev-sre-k8s-oom-crash-case"
WORKFLOW_AUTO_CODE_ID = "gev-sre-k8s-oom-crash-auto-code"
WORKFLOW_TOOL_ID = "gev-sre-k8s-oom-run"
WORKFLOW_AUTO_CODE_TOOL_ID = "gev-sre-k8s-oom-run-auto-code"
AGENT_ID = "gev-sre-k8s-oom"
CONNECTOR_ID = "gev-sre-server-log"
WORKFLOW_CONNECTOR_ID = "system-connector-.workflows"
RULE_TAGS = ["sre", "ge-vernova", "k8s", "oom"]
GROUP_FIELDS = [
    "resource.attributes.k8s.cluster.name",
    "resource.attributes.k8s.namespace.name",
    "resource.attributes.k8s.deployment.name",
    "resource.attributes.k8s.container.name",
]
LOGS_DV_TITLE = "logs-*"
METRICS_DV_TITLE = "metrics-*"
OOM_PHRASE_KQL = (
    '(body.text: "Out of memory." or body.text: "Out of memory" '
    "or body.text: OutOfMemoryError or body.text: \"java.lang.OutOfMemoryError\" "
    "or body.text: OOMKilled or body.text: OutOfMemoryException) "
    "and resource.attributes.k8s.deployment.name: *"
)
MEM_KQL = (
    "metrics.k8s.container.memory_limit_utilization: * "
    'and not resource.attributes.k8s.container.name: "datadog-agent-injected" '
    "and resource.attributes.k8s.deployment.name: *"
)
RESTART_KQL = (
    "metrics.k8s.container.restarts: * "
    'and not resource.attributes.k8s.container.name: "datadog-agent-injected" '
    "and resource.attributes.k8s.deployment.name: *"
)
CLASSIC_RULE_IDS = [
    "gev-sre-k8s-oom-phrase",
    "gev-sre-k8s-mem-limit-saturate",
    "gev-sre-k8s-restart-burst",
]
ctx = ssl.create_default_context()


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


def load_esql(name: str) -> str:
    return (ROOT / "esql" / name).read_text().strip()


def timed(body: str) -> str:
    # Queries already include ?_tstart / ?_tend placeholders.
    return body


def enable_alerting_v2():
    st, body = req(
        KB + "/internal/kibana/global_settings",
        "POST",
        {"changes": {"alerting:v2:enabled": True}},
        kibana=True,
    )
    setting = ((body.get("settings") or {}).get("alerting:v2:enabled") or {})
    print("alerting v2", st, setting.get("userValue"))


def ensure_space():
    st, body = req(KB + f"/api/spaces/space/{SPACE}", kibana=True)
    if st == 200 and body.get("id") == SPACE:
        print("space exists", SPACE)
        return
    st, body = req(
        KB + "/api/spaces/space",
        "POST",
        {
            "id": SPACE,
            "name": "SRE",
            "description": "SRE OpenSearch + K8s OOM views and paging rules",
            "color": "#AA6556",
            "initials": "SR",
            "disabledFeatures": [],
        },
        kibana=True,
    )
    print("space create", st, body.get("id") or body.get("message") or body)


def v2_rule(name: str, description: str, esql: str, lookback: str = "15m"):
    return {
        "kind": "alert",
        "metadata": {
            "name": name,
            "description": description,
            "tags": RULE_TAGS,
        },
        "time_field": "@timestamp",
        "schedule": {"every": "5m", "lookback": lookback},
        "recovery_strategy": "no_breach",
        "no_data_strategy": "none",
        "query": {"format": "standalone", "breach": {"query": esql}},
        "grouping": {"fields": GROUP_FIELDS},
        "state_transition": {"pending_count": 1, "recovering_count": 1},
        "artifacts": [
            {
                "id": "oom-dash",
                "type": "dashboard",
                "data": {"dashboard_id": DASHBOARD_ID},
            }
        ],
    }


def rule_specs():
    return [
        {
            "id": "gev-sre-k8s-restart-burst",
            "v2": v2_rule(
                "[SRE] K8s multi-pod restart burst",
                "P2: ≥2 pods in the same deployment each gained ≥1 restart in the lookback "
                "(excludes datadog-agent-injected). Wakes investigation without naming OOM.",
                timed(load_esql("restart-burst.esql")),
                lookback="30m",
            ),
        },
        {
            "id": "gev-sre-k8s-oom-phrase",
            "v2": v2_rule(
                "[SRE] K8s OOM phrase in container logs",
                "P1: container logs matched Out of memory / OutOfMemoryError / OOMKilled "
                "(phrase / QSTR — not loose MATCH).",
                timed(load_esql("oom-phrase.esql")),
                lookback="15m",
            ),
        },
        {
            "id": "gev-sre-k8s-mem-limit-saturate",
            "v2": v2_rule(
                "[SRE] K8s container memory limit ≥ 95%",
                "P2: k8s.container.memory_limit_utilization ≥ 0.95 for ≥5 samples in lookback "
                "(excludes datadog-agent-injected). Pair with restart burst for oom.likely.",
                timed(load_esql("mem-limit-saturate.esql")),
                lookback="15m",
            ),
        },
        {
            "id": "gev-sre-k8s-oomkilled-status",
            "v2": v2_rule(
                "[SRE] K8s container status reason OOMKilled",
                "P1: k8s.container.status.reason == OOMKilled (requires OTel Wave 0 enablement). "
                "May return no breaches until collectors are rolled.",
                timed(load_esql("oomkilled-status.esql")),
                lookback="15m",
            ),
        },
    ]


def put_v2_rule(rule_id: str, payload: dict):
    out = ROOT / "kibana" / f"{rule_id}-v2.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
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


def find_data_view_id(title: str):
    st, existing = req(KB + f"/s/{SPACE}/api/data_views", kibana=True)
    if st != 200:
        return None
    views = existing.get("data_view") or existing.get("data_views") or []
    for dv in views:
        if dv.get("title") == title:
            return dv.get("id")
    return None


def ensure_data_view(title: str, name: str):
    dv_id = find_data_view_id(title)
    if dv_id:
        print("data_view exists", title, dv_id)
        return dv_id
    st, body = req(
        KB + f"/s/{SPACE}/api/data_views/data_view",
        "POST",
        {
            "data_view": {
                "title": title,
                "name": name,
                "timeFieldName": "@timestamp",
                "allowNoIndex": True,
            }
        },
        kibana=True,
    )
    dv_id = ((body.get("data_view") or {}).get("id") if isinstance(body, dict) else None)
    print("data_view create", title, st, dv_id or body.get("message") or body)
    return dv_id


def metric(name, agg, field=None):
    item = {"name": name, "aggType": agg}
    if field:
        item["field"] = field
    return item


def criterion(comparator, metrics, threshold, time_size=15, time_unit="m"):
    return {
        "comparator": comparator,
        "metrics": metrics,
        "threshold": threshold,
        "timeSize": time_size,
        "timeUnit": time_unit,
    }


def workflow_rule_action():
    # Match live OpenSearch wiring: workflow connector without a group field.
    # Auto-wake uses the no-HITL path (approve_code_ticket); HITL variant remains
    # available for manual / agent tool gev-sre-k8s-oom-run.
    return {
        "id": WORKFLOW_CONNECTOR_ID,
        "params": {
            "subAction": "run",
            "subActionParams": {
                "workflowId": WORKFLOW_AUTO_CODE_ID,
                "summaryMode": False,
                "alertStates": {
                    "new": True,
                    "ongoing": False,
                    "recovered": True,
                },
            },
        },
    }


def custom_threshold_rule(name, message, criteria, kql, group_by, dv_id, with_workflow=True):
    actions = [
        {
            "group": "custom_threshold.fired",
            "id": CONNECTOR_ID,
            "params": {
                "message": message,
                "level": "info",
            },
            "frequency": {
                "summary": False,
                "notify_when": "onActionGroupChange",
                "throttle": None,
            },
        },
    ]
    # Restart companion uses absolute lifetime counters and is too noisy for
    # auto-case/workflow wake. OOM phrase + mem-saturate remain the auto-wake path;
    # the agent detects true multi-pod Δ bursts via ES|QL.
    if with_workflow:
        actions.append(workflow_rule_action())
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


def classic_rule_specs(logs_dv_id: str, metrics_dv_id: str):
    return [
        {
            "id": "gev-sre-k8s-oom-phrase",
            "ct": custom_threshold_rule(
                "[SRE] K8s OOM phrase in container logs",
                "P1 OOM phrase in container logs (classic companion → workflow "
                f"{WORKFLOW_AUTO_CODE_ID}).",
                [criterion(">", [metric("A", "count")], [0])],
                OOM_PHRASE_KQL,
                GROUP_FIELDS,
                logs_dv_id,
            ),
        },
        {
            "id": "gev-sre-k8s-mem-limit-saturate",
            "ct": custom_threshold_rule(
                "[SRE] K8s container memory limit ≥ 95%",
                "P2 memory_limit_utilization max ≥ 0.95 for 15m (classic companion → "
                f"workflow {WORKFLOW_AUTO_CODE_ID}).",
                [
                    criterion(
                        ">",
                        [
                            metric(
                                "A",
                                "max",
                                "metrics.k8s.container.memory_limit_utilization",
                            )
                        ],
                        [0.95],
                    )
                ],
                MEM_KQL,
                GROUP_FIELDS,
                metrics_dv_id,
            ),
        },
        {
            "id": "gev-sre-k8s-restart-burst",
            "ct": custom_threshold_rule(
                "[SRE] K8s multi-pod restart burst",
                "P2 coarse restart signal: max k8s.container.restarts ≥ 5 over 15m "
                "(absolute counters — not multi-pod Δ). Does NOT auto-start the case "
                "workflow; agent / v2 ES|QL detect true crash bursts and investigate OOM.",
                [
                    criterion(
                        ">",
                        [metric("A", "max", "metrics.k8s.container.restarts")],
                        [5],
                    )
                ],
                RESTART_KQL,
                GROUP_FIELDS,
                metrics_dv_id,
                with_workflow=False,
            ),
        },
    ]


def put_ct_rule(rule_id: str, payload: dict):
    out = ROOT / "kibana" / f"{rule_id}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    st, existing = req(KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}", kibana=True)
    if st == 200 and existing.get("id"):
        dst, _ = req(
            KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}",
            "DELETE",
            kibana=True,
        )
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
    elif st < 400:
        actions = body.get("actions") or []
        print(
            "  actions",
            [a.get("id") for a in actions],
            "workflow" if any(a.get("id") == WORKFLOW_CONNECTOR_ID for a in actions) else "NO WORKFLOW",
        )
    return st


def attach_workflow_to_rule(rule_id: str, with_workflow: bool = True):
    """Idempotent: ensure classic rule has (or lacks) the workflow action."""
    st, existing = req(KB + f"/s/{SPACE}/api/alerting/rule/{rule_id}", kibana=True)
    if st != 200 or not existing.get("id"):
        print("rule missing; skip workflow action", rule_id, st)
        return st
    actions = []
    for action in existing.get("actions") or []:
        if action.get("id") == WORKFLOW_CONNECTOR_ID:
            continue
        item = {
            "group": action.get("group") or "custom_threshold.fired",
            "id": action["id"],
            "params": action.get("params") or {},
        }
        if action.get("frequency") is not None:
            item["frequency"] = action["frequency"]
        if action.get("uuid"):
            item["uuid"] = action["uuid"]
        actions.append(item)
    if with_workflow:
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
        "ATTACH" if with_workflow else "DETACH",
    )
    return st


def install_classic_rules():
    ensure_server_log_connector()
    logs_dv = ensure_data_view(LOGS_DV_TITLE, "All logs")
    metrics_dv = ensure_data_view(METRICS_DV_TITLE, "All metrics")
    if not logs_dv or not metrics_dv:
        print("missing data views; skip classic rules", logs_dv, metrics_dv)
        return
    for spec in classic_rule_specs(logs_dv, metrics_dv):
        put_ct_rule(spec["id"], spec["ct"])
        # Restart-burst intentionally has no workflow (absolute counters are noisy).
        wants_workflow = any(
            a.get("id") == WORKFLOW_CONNECTOR_ID
            for a in (spec["ct"].get("actions") or [])
        )
        attach_workflow_to_rule(spec["id"], with_workflow=wants_workflow)


def install_rules():
    enable_alerting_v2()
    for spec in rule_specs():
        put_v2_rule(spec["id"], spec["v2"])
    install_classic_rules()


def merge_case_fields():
    """Merge K8s custom fields + template into existing observability case config."""
    extra = json.loads((ROOT / "kibana" / "cases" / "configure-fields.json").read_text())
    st, body = req(KB + f"/s/{SPACE}/api/cases/configure", kibana=True)
    existing = None
    if st == 200:
        if isinstance(body, list) and body:
            existing = body[0]
        elif isinstance(body, dict) and body.get("id"):
            existing = body
    if not existing:
        print("cases configure missing; create minimal")
        payload = {
            "owner": "observability",
            "closure_type": "close-by-user",
            "connector": {
                "id": "none",
                "name": "none",
                "type": ".none",
                "fields": None,
            },
            "customFields": extra["customFields"],
            "templates": extra["templates"],
        }
        st, body = req(
            KB + f"/s/{SPACE}/api/cases/configure",
            "POST",
            payload,
            kibana=True,
        )
        print("cases configure create", st, body.get("id") or body.get("message") or body)
        return body

    fields = list(existing.get("customFields") or [])
    by_key = {f.get("key"): f for f in fields}
    added = 0
    for f in extra.get("customFields") or []:
        if f["key"] not in by_key and len(fields) < 10:
            fields.append(f)
            by_key[f["key"]] = f
            added += 1

    templates = list(existing.get("templates") or [])
    t_keys = {t.get("key") for t in templates}
    for t in extra.get("templates") or []:
        if t["key"] not in t_keys:
            templates.append(t)

    if added == 0 and len(templates) == len(existing.get("templates") or []):
        # Still patch if new template arrived
        if all(t.get("key") in t_keys for t in extra.get("templates") or []):
            print("cases configure unchanged (field cap 10; template exists)")
            return existing

    patch = {
        "version": existing["version"],
        "customFields": fields,
        "templates": templates,
    }
    st, body = req(
        KB + f"/s/{SPACE}/api/cases/configure/{existing['id']}",
        "PATCH",
        patch,
        kibana=True,
    )
    print(
        "cases configure merge",
        st,
        body.get("id") or body.get("message") or body,
        "fields",
        len(fields),
        "templates",
        len(templates),
    )
    return body


def upsert_workflow(workflow_id: str = WORKFLOW_ID):
    yaml_text = (ROOT / "kibana" / "workflows" / f"{workflow_id}.yaml").read_text()
    st, body = req(
        KB + f"/s/{SPACE}/api/workflows/workflow/{workflow_id}",
        "PUT",
        {"yaml": yaml_text},
        kibana=True,
    )
    if st == 404:
        st, body = req(
            KB + f"/s/{SPACE}/api/workflows/workflow",
            "POST",
            {"id": workflow_id, "yaml": yaml_text},
            kibana=True,
        )
    print(
        "workflow",
        workflow_id,
        st,
        "valid" if isinstance(body, dict) and body.get("valid") else (
            body.get("message") if isinstance(body, dict) else body
        ),
        "enabled" if isinstance(body, dict) and body.get("enabled") else "",
    )
    if isinstance(body, dict) and body.get("valid") is False:
        err = ROOT / "kibana" / f"{workflow_id}-invalid.json"
        err.write_text(json.dumps(body, indent=2)[:6000])
        print("workflow invalid ->", err)
    return body


def _agent_builder_payload(path: Path, drop=()):
    raw = json.loads(path.read_text())
    for key in drop:
        raw.pop(key, None)
    return raw


def upsert_workflow_tool(tool_id: str = WORKFLOW_TOOL_ID):
    src = ROOT / "kibana" / "tools" / f"{tool_id}.json"
    create_body = _agent_builder_payload(src)
    update_body = {k: v for k, v in create_body.items() if k not in ("id", "type")}
    st, body = req(
        KB + f"/s/{SPACE}/api/agent_builder/tools/{tool_id}",
        kibana=True,
    )
    if st == 200:
        st, body = req(
            KB + f"/s/{SPACE}/api/agent_builder/tools/{tool_id}",
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
        tool_id,
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


def dash_url(so_id=DASHBOARD_ID):
    return KB + f"/s/{SPACE}/app/dashboards#/view/{so_id}"


def put_dashboard(so_id, attributes, references):
    st, body = req(
        KB + f"/s/{SPACE}/api/saved_objects/dashboard/{so_id}?overwrite=true",
        "POST",
        {"attributes": attributes, "references": references},
        kibana=True,
    )
    print("dashboard", so_id, st, body.get("id") or body.get("message") or body)
    if st < 400:
        print("dashboard url", dash_url(so_id))
    return st


def install_dashboard():
    ensure_data_view(LOGS_DV_TITLE, "All logs")
    ensure_data_view(METRICS_DV_TITLE, "All metrics")
    attrs, refs = build_oom_crash_dashboard()
    out = ROOT / "kibana" / f"{DASHBOARD_ID}.json"
    out.write_text(json.dumps({"attributes": attrs, "references": refs}, indent=2) + "\n")
    st = put_dashboard(DASHBOARD_ID, attrs, refs)
    for spec in rule_specs():
        put_v2_rule(spec["id"], spec["v2"])
    # Drop the schema-probe dashboard if it is still around.
    dst, _ = req(
        KB + f"/s/{SPACE}/api/saved_objects/dashboard/{DASHBOARD_ID}-test",
        "DELETE",
        kibana=True,
    )
    if dst < 400 or dst == 404:
        print("dashboard test cleanup", dst)
    return st


def verify_queries():
    """Smoke-test detection ES|QL with NOW()-relative windows."""
    checks = [
        (
            "restart-burst",
            load_esql("restart-burst.esql").replace(
                "@timestamp >= ?_tstart AND @timestamp < ?_tend",
                "@timestamp >= NOW() - 30 minutes",
            ),
        ),
        (
            "oom-phrase",
            load_esql("oom-phrase.esql").replace(
                "@timestamp >= ?_tstart AND @timestamp < ?_tend",
                "@timestamp >= NOW() - 3 days",
            ),
        ),
        (
            "mem-limit-saturate",
            load_esql("mem-limit-saturate.esql").replace(
                "@timestamp >= ?_tstart AND @timestamp < ?_tend",
                "@timestamp >= NOW() - 15 minutes",
            ),
        ),
    ]
    checks.extend(verify_query_specs())
    for name, q in checks:
        st, body = req(ES + "/_query", "POST", {"query": q})
        if st >= 400 or "error" in body:
            print("verify FAIL", name, st, (body.get("error") or body))
        else:
            print("verify OK", name, "rows", len(body.get("values") or []))


def install_workflow_stack():
    merge_case_fields()
    upsert_workflow(WORKFLOW_ID)
    upsert_workflow(WORKFLOW_AUTO_CODE_ID)
    upsert_workflow_tool(WORKFLOW_TOOL_ID)
    upsert_workflow_tool(WORKFLOW_AUTO_CODE_TOOL_ID)
    upsert_agent()


def main(argv: list[str]):
    (ROOT / "kibana").mkdir(exist_ok=True)
    ensure_space()
    mode = argv[1] if len(argv) > 1 else "all"
    if mode in ("all", "verify"):
        verify_queries()
    if mode in ("all", "dashboard", "dashboards"):
        install_dashboard()
    if mode in ("all", "rules"):
        install_rules()
    if mode in ("all", "workflow"):
        install_workflow_stack()
    if mode not in ("all", "rules", "workflow", "verify", "dashboard", "dashboards"):
        print("usage: apply.py [all|dashboard|rules|workflow|verify]")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
