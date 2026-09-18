#!/usr/bin/env python3
"""Apply SRE AppHub → Meridium latency: dashboard, v2 ES|QL rules, workflow.

Usage:
  ELASTIC_API_KEY=... python3 apply.py              # full install
  ELASTIC_API_KEY=... python3 apply.py dashboard
  ELASTIC_API_KEY=... python3 apply.py rules
  ELASTIC_API_KEY=... python3 apply.py workflow
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

from dashboards import DASHBOARD_ID, INTRO, build_latency_dashboard, verify_query_specs
from vega import TABLE_GRIDS, inline_chart_panels, verify_vega_queries

ROOT = Path(__file__).resolve().parent
ES = "https://my-observability-project-f2e495.es.us-west-2.aws.elastic.cloud:443"
KB = "https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud"
API_KEY = os.environ.get(
    "ELASTIC_API_KEY",
    "UnBSVGJhQUJKcXNqWTh1Yzc0TEk6Vm13c2dsYUlleC1hU1U3dnBYUndvZw==",
)
SPACE = "sre"
WORKFLOW_ID = "gev-sre-apphub-meridium-latency-case"
WORKFLOW_AUTO_ID = "gev-sre-apphub-meridium-auto-approve"
WORKFLOW_AUTO_CODE_ID = "gev-sre-apphub-meridium-latency-auto-code"
WORKFLOW_TOOL_ID = "gev-sre-apphub-meridium-run"
WORKFLOW_AUTO_TOOL_ID = "gev-sre-apphub-meridium-run-auto-approve"
WORKFLOW_AUTO_CODE_TOOL_ID = "gev-sre-apphub-meridium-run-auto-code"
AGENT_ID = "gev-sre-apphub-meridium"
CONNECTOR_ID = "gev-sre-server-log"
WORKFLOW_CONNECTOR_ID = "system-connector-.workflows"
RULE_TAGS = ["sre", "ge-vernova", "apphub", "meridium", "latency"]
GROUP_FIELDS = [
    "resource.attributes.service.name",
    "attributes.span.destination.service.resource",
]
METRICS_DV_TITLE = "metrics-*"
TRACES_DV_TITLE = "traces-*"
# Full Kibana URL so the href is valid from classic Discover AND Lens.
# Relative apm/link-to/... 404s on nested Discover/ES|QL routes; /app/apm/...
# without /s/{space} drops the SRE space. Kibana 9.4+ strips this format from
# the APM static data view on every APM load (isEqual against transaction.*
# only), so we re-apply it to every SRE view that has trace.id.
# openLinkInCurrentTab: data-grid cell click otherwise swallows target=_blank.
TRACE_ID_URL_FORMAT = {
    "id": "url",
    "params": {
        "type": "a",
        "urlTemplate": f"{KB}/s/{SPACE}/app/apm/link-to/trace/{{{{value}}}}",
        "labelTemplate": "{{value}}",
        "openLinkInCurrentTab": True,
    },
}
TRACE_ID_FORMAT_FIELDS = ("trace.id", "trace_id")
APM_STATIC_DV_ID = "apm_static_data_view_id_sre"
HOP_KQL = (
    "resource.attributes.service.name: *apphub* and "
    "(attributes.span.destination.service.resource: *classic* or "
    "attributes.span.destination.service.resource: *meridium*)"
)
CLASSIC_RULE_IDS = [
    "gev-sre-apphub-meridium-latency",
    "gev-sre-apphub-meridium-errors",
    "gev-sre-apphub-meridium-timeouts",
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
            "description": "SRE OpenSearch + K8s OOM + AppHub/Meridium views and paging rules",
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
                "id": "am-dash",
                "type": "dashboard",
                "data": {"dashboard_id": DASHBOARD_ID},
            }
        ],
    }


def rule_specs():
    return [
        {
            "id": "gev-sre-apphub-meridium-latency",
            "v2": v2_rule(
                "[SRE] AppHub → Meridium avg latency ≥ 500ms",
                "P2: destination avg response time ≥ 500 ms with ≥30 calls in the lookback "
                "(AppHub client → APM Classic / Meridium ingress).",
                load_esql("dest-latency.esql"),
                lookback="15m",
            ),
        },
        {
            "id": "gev-sre-apphub-meridium-errors",
            "v2": v2_rule(
                "[SRE] AppHub → Meridium error rate ≥ 5%",
                "P1: destination failure share ≥ 5% with ≥20 calls in the lookback.",
                load_esql("dest-errors.esql"),
                lookback="15m",
            ),
        },
        {
            "id": "gev-sre-apphub-meridium-timeouts",
            "v2": v2_rule(
                "[SRE] AppHub → Meridium client timeouts ≥ 30s",
                "P1: ≥3 AppHub client spans to Classic/Meridium lasted ≥30s (often ~300s abort).",
                load_esql("dest-timeouts.esql"),
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


def trace_id_field_formats(existing=None):
    formats = dict(existing or {})
    for field in TRACE_ID_FORMAT_FIELDS:
        formats[field] = TRACE_ID_URL_FORMAT
    return formats


def _data_view_has_trace_id(dv: dict) -> bool:
    fields = dv.get("fields") or {}
    if any(fields.get(field) for field in TRACE_ID_FORMAT_FIELDS):
        return True
    title = (dv.get("title") or "").lower()
    name = (dv.get("name") or "").lower()
    dv_id = dv.get("id") or ""
    return (
        dv_id == APM_STATIC_DV_ID
        or "trace" in title
        or "trace" in name
        or name == "sre demo"
    )


def ensure_trace_id_url(dv_id: str):
    st, body = req(
        KB + f"/s/{SPACE}/api/data_views/data_view/{dv_id}",
        kibana=True,
    )
    dv = body.get("data_view") if st == 200 and isinstance(body, dict) else {}
    if not dv:
        print("trace.id url skip", dv_id, st, body.get("message") if isinstance(body, dict) else body)
        return
    formats = trace_id_field_formats(dv.get("fieldFormats"))
    st, body = req(
        KB + f"/s/{SPACE}/api/data_views/data_view/{dv_id}",
        "POST",
        {"data_view": {"fieldFormats": formats}},
        kibana=True,
    )
    live = (body.get("data_view") or {}).get("fieldFormats") or {}
    if st >= 400:
        print("trace.id url", dv.get("name") or dv_id, st, body.get("message") or body)
        return
    params = (live.get("trace.id") or live.get("trace_id") or {}).get("params") or {}
    print(
        "trace url",
        dv.get("name") or dv_id,
        params.get("urlTemplate"),
        "tab" if params.get("openLinkInCurrentTab") else "blank",
    )


def ensure_all_trace_id_urls():
    st, existing = req(KB + f"/s/{SPACE}/api/data_views", kibana=True)
    views = existing.get("data_view") or existing.get("data_views") or [] if st == 200 else []
    ids = [dv.get("id") for dv in views if dv.get("id")]
    if APM_STATIC_DV_ID not in ids:
        ids.append(APM_STATIC_DV_ID)
    for dv_id in ids:
        st, body = req(KB + f"/s/{SPACE}/api/data_views/data_view/{dv_id}", kibana=True)
        dv = body.get("data_view") if st == 200 and isinstance(body, dict) else {}
        if dv and _data_view_has_trace_id(dv):
            ensure_trace_id_url(dv_id)


def ensure_data_view(title: str, name: str):
    dv_id = find_data_view_id(title)
    if dv_id:
        print("data_view exists", title, dv_id)
        if title == TRACES_DV_TITLE:
            ensure_all_trace_id_urls()
        return dv_id
    payload = {
        "data_view": {
            "title": title,
            "name": name,
            "timeFieldName": "@timestamp",
            "allowNoIndex": True,
        }
    }
    if title == TRACES_DV_TITLE:
        payload["data_view"]["fieldFormats"] = trace_id_field_formats()
    st, body = req(
        KB + f"/s/{SPACE}/api/data_views/data_view",
        "POST",
        payload,
        kibana=True,
    )
    dv_id = ((body.get("data_view") or {}).get("id") if isinstance(body, dict) else None)
    print("data_view create", title, st, dv_id or body.get("message") or body)
    if title == TRACES_DV_TITLE:
        ensure_all_trace_id_urls()
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
    # Auto-wake uses the no-HITL path (RCA → escalate_meridium_owners or
    # investigate_apphub_proxy). HITL variant remains for manual / agent tool
    # gev-sre-apphub-meridium-run.
    return {
        "id": WORKFLOW_CONNECTOR_ID,
        "params": {
            "subAction": "run",
            "subActionParams": {
                "workflowId": WORKFLOW_AUTO_ID,
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


def classic_rule_specs(traces_dv_id: str):
    return [
        {
            "id": "gev-sre-apphub-meridium-latency",
            "ct": custom_threshold_rule(
                "[SRE] AppHub → Meridium avg latency ≥ 500ms",
                "P2 AppHub client avg span duration ≥ 500ms over 15m "
                f"(classic companion → workflow {WORKFLOW_AUTO_ID}).",
                [
                    criterion(
                        ">",
                        [metric("A", "avg", "attributes.span.duration.us")],
                        [500000],
                    )
                ],
                HOP_KQL,
                GROUP_FIELDS,
                traces_dv_id,
            ),
        },
        {
            "id": "gev-sre-apphub-meridium-errors",
            "ct": custom_threshold_rule(
                "[SRE] AppHub → Meridium error rate ≥ 5%",
                "P1 AppHub client failures to Classic/Meridium "
                f"(classic companion → workflow {WORKFLOW_AUTO_ID}). Count ≥ 20 over 15m.",
                [criterion(">", [metric("A", "count")], [19])],
                HOP_KQL + " and attributes.event.outcome: failure",
                GROUP_FIELDS,
                traces_dv_id,
            ),
        },
        {
            "id": "gev-sre-apphub-meridium-timeouts",
            "ct": custom_threshold_rule(
                "[SRE] AppHub → Meridium client timeouts ≥ 30s",
                "P1 AppHub client spans ≥ 30s "
                f"(classic companion → workflow {WORKFLOW_AUTO_ID}). Count ≥ 3 over 15m.",
                [criterion(">", [metric("A", "count")], [2])],
                HOP_KQL + " and attributes.span.duration.us >= 30000000",
                GROUP_FIELDS,
                traces_dv_id,
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
        "tags": existing.get("tags") or RULE_TAGS,
        "schedule": existing.get("schedule") or {"interval": "5m"},
        "params": existing.get("params") or {},
        "actions": actions,
        "throttle": existing.get("throttle"),
        "notify_when": existing.get("notify_when"),
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
    traces_dv = ensure_data_view(TRACES_DV_TITLE, "All traces")
    if not traces_dv:
        print("missing traces data view; skip classic rules")
        return
    for spec in classic_rule_specs(traces_dv):
        put_ct_rule(spec["id"], spec["ct"])
        attach_workflow_to_rule(spec["id"], with_workflow=True)


def install_rules():
    enable_alerting_v2()
    for spec in rule_specs():
        put_v2_rule(spec["id"], spec["v2"])
    install_classic_rules()


def merge_case_fields():
    extra = json.loads((ROOT / "kibana" / "cases" / "configure-fields.json").read_text())
    st, body = req(KB + f"/s/{SPACE}/api/cases/configure", kibana=True)
    existing = None
    if st == 200:
        if isinstance(body, list) and body:
            existing = body[0]
        elif isinstance(body, dict) and body.get("id"):
            existing = body
    if not existing:
        print("cases configure missing; skip merge (OpenSearch/OOM install first)")
        return None

    templates = list(existing.get("templates") or [])
    t_keys = {t.get("key") for t in templates}
    added = 0
    for t in extra.get("templates") or []:
        if t["key"] not in t_keys:
            templates.append(t)
            added += 1
    if added == 0:
        print("cases configure unchanged (latency template exists)")
        return existing
    patch = {
        "version": existing["version"],
        "customFields": existing.get("customFields") or [],
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


def _drop_chart_panel(panel: dict) -> bool:
    pid = panel.get("id") or ""
    ref = (panel.get("config") or {}).get("ref_id") or ""
    if pid.startswith("am-vega-") or pid in ("am-heat", "am-host-bar", "am-test-vega", "p1"):
        return True
    if str(ref).startswith("gev-sre-apphub-meridium-vega"):
        return True
    return False


def enhance_dashboard_charts():
    """Keep auto-bucket XY, drop broken Vega refs, add inline heatmap + host bars."""
    st, body = req(
        KB + f"/s/{SPACE}/api/dashboards/{DASHBOARD_ID}",
        kibana=True,
    )
    if st != 200 or not isinstance(body, dict):
        print("dashboard enhance skip; GET", st, body)
        return st
    data = body.get("data") or {}
    kept = [p for p in (data.get("panels") or []) if not _drop_chart_panel(p)]
    for panel in kept:
        pid = panel.get("id")
        if pid in TABLE_GRIDS:
            panel["grid"] = dict(TABLE_GRIDS[pid])
        if pid == "am-md":
            cfg = panel.setdefault("config", {})
            cfg["content"] = INTRO
            cfg["title"] = "How to read AppHub → Meridium latency"
            cfg["hide_title"] = False
    data["panels"] = kept + inline_chart_panels()
    data["time_range"] = {"from": "now-3d", "to": "now"}
    payload = {
        k: data[k]
        for k in (
            "title",
            "description",
            "time_range",
            "options",
            "filters",
            "query",
            "tags",
            "panels",
            "pinned_panels",
        )
        if k in data
    }
    st, body = req(
        KB + f"/s/{SPACE}/api/dashboards/{DASHBOARD_ID}",
        "PUT",
        payload,
        kibana=True,
    )
    print(
        "dashboard chart enhance",
        st,
        "panels",
        len((body.get("data") or {}).get("panels") or [])
        if st < 400
        else body.get("message") or body,
    )
    if st < 400:
        (ROOT / "kibana" / f"{DASHBOARD_ID}-dash-api.json").write_text(
            json.dumps(body.get("data") or payload, indent=2) + "\n"
        )
    return st


def cleanup_vega_probes():
    for kind, so_id in (
        ("dashboard", "am-vega-embed-probe"),
        ("dashboard", "am-vega-so-probe"),
        ("dashboard", "am-vega-so-probe2"),
        ("dashboard", "am-xy-schema-probe"),
        ("dashboard", "am-inline-vis-probe"),
        ("dashboard", "am-type-probe"),
        ("visualization", "am-test-vega"),
        ("visualization", "gev-sre-apphub-meridium-vega-trend"),
        ("visualization", "gev-sre-apphub-meridium-vega-bubble"),
        ("visualization", "gev-sre-apphub-meridium-vega-heat"),
    ):
        st, _ = req(
            KB + f"/s/{SPACE}/api/saved_objects/{kind}/{so_id}",
            "DELETE",
            kibana=True,
        )
        print("cleanup", kind, so_id, st)


def install_dashboard():
    ensure_data_view(METRICS_DV_TITLE, "All metrics")
    ensure_data_view(TRACES_DV_TITLE, "All traces")
    attrs, refs = build_latency_dashboard()
    out = ROOT / "kibana" / f"{DASHBOARD_ID}.json"
    out.write_text(json.dumps({"attributes": attrs, "references": refs}, indent=2) + "\n")
    st = put_dashboard(DASHBOARD_ID, attrs, refs)
    enhance_st = enhance_dashboard_charts()
    cleanup_vega_probes()
    for spec in rule_specs():
        put_v2_rule(spec["id"], spec["v2"])
    return enhance_st if enhance_st >= 400 else st


def verify_queries():
    checks = [
        (
            "dest-latency",
            load_esql("dest-latency.esql").replace(
                "@timestamp >= ?_tstart AND @timestamp < ?_tend",
                "@timestamp >= NOW() - 15 minutes",
            ),
        ),
        (
            "dest-errors",
            load_esql("dest-errors.esql").replace(
                "@timestamp >= ?_tstart AND @timestamp < ?_tend",
                "@timestamp >= NOW() - 15 minutes",
            ),
        ),
        (
            "dest-timeouts",
            load_esql("dest-timeouts.esql").replace(
                "@timestamp >= ?_tstart AND @timestamp < ?_tend",
                "@timestamp >= NOW() - 15 minutes",
            ),
        ),
    ]
    checks.extend(verify_query_specs())
    checks.extend(verify_vega_queries())
    for name, q in checks:
        st, body = req(ES + "/_query", "POST", {"query": q})
        if st >= 400 or "error" in body:
            print("verify FAIL", name, st, (body.get("error") or body))
        else:
            print("verify OK", name, "rows", len(body.get("values") or []))


def install_workflow_stack():
    merge_case_fields()
    upsert_workflow(WORKFLOW_ID)
    upsert_workflow(WORKFLOW_AUTO_ID)
    upsert_workflow(WORKFLOW_AUTO_CODE_ID)
    upsert_workflow_tool(WORKFLOW_TOOL_ID)
    upsert_workflow_tool(WORKFLOW_AUTO_TOOL_ID)
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
