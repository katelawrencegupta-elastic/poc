#!/usr/bin/env python3
"""Apply FinOps rightsizing + demo extras (evidence, spend vs savings, alerts, cases, ess_billing).

Does not ingest Compute Optimizer — use ingest_compute_optimizer.py.
Does not delete live CO docs. Sample recs keep demo statuses and are tagged hidden_reason=seeded_sample.
Set SKIP_SAMPLES=1 to skip reseeding. ess_billing needs ESS_ORG_ID and ESS_BILLING_API_KEY.

  python3 apply.py            # demo dashboards / samples (default)
  python3 apply.py vega       # Cut A rightsizing charts + Vega horizontal bars on hub
  python3 apply.py svs        # Vega-Lite-inspired spend vs savings charts
  python3 apply.py hub-tabs   # tab strip on every FinOps dashboard (hub = Overview)
  python3 apply.py workflow   # assistant tools + spend-spike + rightsizing HITL and auto-approve workflows
  python3 apply.py all        # demo then workflow
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dashboards import (
    build_billing_overview,
    build_spend_vs_savings,
)
from hub_tabs import ALL_DASHBOARD_IDS, HUB_ID, inject_tabs_saved_object, tabs_panel
from svs_vega import (
    SVS_ID,
    VEGA_VIS as SVS_VEGA_VIS,
    chart_panels as svs_chart_panels,
    verify_svs_queries,
    vis_so_payload as svs_vis_so_payload,
)
from vega import (
    DASHBOARD_ID as RS_DASHBOARD_ID,
    HBAR_LAYOUT,
    VEGA_BAR_CHARTS,
    native_hbar_panel,
    overview_payload,
    verify_vega_queries,
    vis_attributes,
)

ROOT = Path(__file__).resolve().parent
ES = "https://my-observability-project-f2e495.es.us-west-2.aws.elastic.cloud:443"
KB = "https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud"
API_KEY = os.environ.get(
    "ELASTIC_API_KEY",
    "UnBSVGJhQUJKcXNqWTh1Yzc0TEk6Vm13c2dsYUlleC1hU1U3dnBYUndvZw==",
)
DATA_VIEW_TITLE = "logs-finops.rightsizing-*"
METRICS_VIEW_ID = "metrics-*"
EXISTING_CASE_ID = "4328f86f-b250-477e-b9ab-ada067c83e30"
APM_DEV_ARN = "arn:aws:ec2:us-west-2:041298796264:instance/i-09c920d4ff962442f"
STAGE_ARN = "arn:aws:ec2:us-west-2:985408759551:instance/i-046010bf81f3e6e54"
HIDDEN_ARN = "arn:aws:ec2:us-west-2:041298796264:volume/vol-0samplehide01"
DONE_ARN = "arn:aws:ec2:us-west-2:985408759551:instance/i-0sampledone01"
SEED_TS = "2026-09-09T16:00:00.000Z"
AWS_POLICY_IDS = [
    "9ce8892d-4166-4151-872e-583f452a396f",
    "efc7088e-9752-4420-845c-31563d193442",
    "9477478c-13e4-4c6b-909a-d8de4b3aa179",
    "e947d8c4-97ab-4f58-9921-5c3797391b1f",
]
WORKFLOW_CONNECTOR_ID = "system-connector-.workflows"
SPIKE_WORKFLOW_ID = "gev-finops-spend-spike-case"
RIGHTSIZE_WORKFLOW_ID = "gev-finops-rightsize-case"
SPIKE_AUTO_WORKFLOW_ID = "gev-finops-spend-spike-auto-approve"
RIGHTSIZE_AUTO_WORKFLOW_ID = "gev-finops-rightsize-auto-approve"
AGENT_ID = "meridian-finops-ai-assistant"
SPIKE_RULE_IDS = [
    "gev-finops-alert-dod-spike",
    "gev-finops-alert-service-dod-spike",
    "meridian-alert-staging-daily",
]
ESQL_TOOL_IDS = [
    "gev-finops-aws-spend",
    "gev-finops-aws-top-accounts",
    "gev-finops-aws-top-services",
    "gev-finops-stage-spend",
    "gev-finops-slo-posture",
    "gev-finops-rightsizing-queue",
    "gev-finops-low-cpu",
    "gev-finops-rds-idle",
]
WORKFLOW_TOOL_IDS = [
    "gev-finops-spike-run",
    "gev-finops-rightsize-run",
    "gev-finops-spike-run-auto-approve",
    "gev-finops-rightsize-run-auto-approve",
]
ctx = ssl.create_default_context()


def load(rel):
    return json.loads((ROOT / rel).read_text())


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


def find_data_view_id(title=DATA_VIEW_TITLE):
    st, existing = req(KB + "/s/finops/api/data_views", kibana=True)
    if st != 200:
        return None
    views = existing.get("data_view") or existing.get("data_views") or []
    for dv in views:
        if dv.get("title") == title:
            return dv.get("id")
    return None


def ensure_data_view(title, name, allow_no_index=False):
    dv_id = find_data_view_id(title)
    if dv_id:
        print("data_view exists", title, dv_id)
        return dv_id
    st, body = req(
        KB + "/s/finops/api/data_views/data_view",
        "POST",
        {
            "data_view": {
                "title": title,
                "name": name,
                "timeFieldName": "@timestamp",
                "allowNoIndex": allow_no_index,
            }
        },
        kibana=True,
    )
    dv_id = ((body.get("data_view") or {}).get("id") if isinstance(body, dict) else None)
    print("data_view create", title, st, dv_id or body)
    return dv_id


def put_dashboard(so_id, attributes, references):
    st, body = req(
        KB + f"/s/finops/api/saved_objects/dashboard/{so_id}?overwrite=true",
        "POST",
        {"attributes": attributes, "references": references},
        kibana=True,
    )
    print("dashboard", so_id, st, body.get("id") or body.get("message") or body)
    return st


def publish_rightsizing_overview(rs_id=None):
    """Cut A: KPIs + queue via dashboard API vis types; scatter/heatmap/RDS from ES|QL."""
    rs_id = rs_id or ensure_data_view(DATA_VIEW_TITLE, "FinOps Rightsizing")
    ec2_id = ensure_data_view("metrics-aws.ec2_metrics-*", "AWS EC2 metrics")
    rds_id = ensure_data_view("metrics-aws.rds-*", "AWS RDS metrics")
    if not (rs_id and rds_id):
        print("rightsizing overview skip; missing data views", rs_id, rds_id)
        return 400
    latest_id = ensure_data_view(
        "finops-rightsizing-latest*",
        "FinOps Rightsizing latest",
        allow_no_index=True,
    )
    req(ES + "/_transform/finops-rightsizing-latest/_start", "POST")
    rec_view = latest_id or rs_id
    payload = overview_payload(rec_view, ec2_id, rds_id)
    st, body = req(
        KB + f"/s/finops/api/dashboards/{RS_DASHBOARD_ID}",
        "PUT",
        payload,
        kibana=True,
    )
    n = len(((body.get("data") or {}).get("panels") or []))
    print(
        "dashboard",
        RS_DASHBOARD_ID,
        st,
        f"panels={n}" if st < 400 else (body.get("message") or body),
    )
    if st < 400:
        (ROOT / "kibana/dashboard-saved-object.json").write_text(
            json.dumps(body.get("data") or payload, indent=2) + "\n"
        )
        print(
            "dashboard url",
            KB + f"/s/finops/app/dashboards#/view/{RS_DASHBOARD_ID}",
        )
        _verify_rightsizing_charts()
        install_hub_tabs(ids=[RS_DASHBOARD_ID])
    return st


def _verify_rightsizing_charts():
    for name, q in verify_vega_queries():
        st, body = req(ES + "/_query", "POST", {"query": q})
        if st >= 400 or "error" in body:
            print("verify FAIL", name, st, (body.get("error") or body))
        else:
            print("verify OK", name, "rows", len(body.get("values") or []))
    st, d = req(KB + f"/s/finops/api/dashboards/{RS_DASHBOARD_ID}", kibana=True)
    panels = ((d.get("data") or {}).get("panels") or []) if st == 200 else []
    by_id = {p.get("id"): p for p in panels}
    expected = [
        ("rs-m-identified", "vis", "metric"),
        ("rs-m-captured", "vis", "metric"),
        ("rs-m-parked", "vis", "metric"),
        ("rs-m-recs", "vis", "metric"),
        ("rs-vega-scatter", "vis", "xy"),
        ("rs-vega-heat", "vis", "heatmap"),
        ("rs-table", "vis", "data_table"),
        ("rs-vega-rds", "vis", "xy"),
        ("rs-rds-table", "vis", "data_table"),
        ("rs-md", "markdown", None),
        ("rs-notes", "markdown", None),
        ("rs-acct", "options_list_control", None),
    ]
    for pid, ptype, ctype in expected:
        p = by_id.get(pid)
        got = (p.get("type") if p else None, (p.get("config") or {}).get("type") if p else None)
        ok = p and p.get("type") == ptype and (ctype is None or got[1] == ctype)
        print("panel", pid, "OK" if ok else f"FAIL {got}")
    dropped = {"rs-pie", "rs-cpu", "rs-ufl", "rs-ures"}
    leftover = dropped & set(by_id)
    print("quota/pie dropped", "OK" if not leftover else leftover)


def install_hub_tabs(ids=None):
    """Add or refresh the horizontal FinOps tab strip via saved objects (survives UI save)."""
    (ROOT / "kibana/hub-tabs.json").write_text(json.dumps(tabs_panel(), indent=2) + "\n")
    for did in ids or ALL_DASHBOARD_IDS:
        st, so = req(KB + f"/s/finops/api/saved_objects/dashboard/{did}", kibana=True)
        if st != 200 or not isinstance(so, dict) or not so.get("attributes"):
            print("hub-tabs skip", did, st, so.get("message") if isinstance(so, dict) else so)
            continue
        attrs, refs = inject_tabs_saved_object(
            so["attributes"], so.get("references") or []
        )
        st, body = req(
            KB + f"/s/finops/api/saved_objects/dashboard/{did}?overwrite=true",
            "POST",
            {"attributes": attrs, "references": refs},
            kibana=True,
        )
        panels = json.loads(attrs.get("panelsJSON") or "[]")
        tab = next((p for p in panels if p.get("panelIndex") == "finops-hub-tabs"), {})
        print(
            "hub-tabs",
            did,
            st,
            "section",
            (tab.get("gridData") or {}).get("sectionId"),
            "refs",
            len([r for r in refs if str(r.get("name") or "").startswith("finops-hub-tabs:")]),
        )
    # confirm hub via dashboards API
    st, d = req(KB + f"/s/finops/api/dashboards/{HUB_ID}", kibana=True)
    data = (d.get("data") or {}) if st == 200 else {}
    found = []
    for p in data.get("panels") or []:
        if p.get("id") == "finops-hub-tabs" or p.get("type") == "links":
            found.append(("top", p.get("id")))
        for inner in p.get("panels") or []:
            if inner.get("id") == "finops-hub-tabs" or inner.get("type") == "links":
                found.append(("section:"+str(p.get("title")), inner.get("id"), inner.get("grid")))
    print("hub-tabs visible on hub GET", found or "MISSING")


def publish_vega_bar_visualizations():
    """Create/update Vega visualization saved objects (Visualize library)."""
    vis_dir = ROOT / "kibana"
    vis_dir.mkdir(exist_ok=True)
    for item in VEGA_BAR_CHARTS:
        spec = item["spec"]() if callable(item["spec"]) else item["spec"]
        payload = {
            "attributes": vis_attributes(
                item["title"], spec, item.get("description") or ""
            ),
            "references": [],
        }
        (vis_dir / f"{item['vis_id']}.json").write_text(
            json.dumps(payload, indent=2) + "\n"
        )
        st, body = req(
            KB
            + f"/s/finops/api/saved_objects/visualization/{item['vis_id']}?overwrite=true",
            "POST",
            payload,
            kibana=True,
        )
        print(
            "vega vis",
            item["vis_id"],
            st,
            body.get("id") if st < 400 else (body.get("message") or body),
        )


def upsert_native_hbar_panels():
    """Put Vega-style horizontal ES|QL bars on live dashboards (type vis, not visualization)."""
    by_dash = {}
    for item in VEGA_BAR_CHARTS:
        by_dash.setdefault(item["dashboard"], []).append(item)
    for did, items in by_dash.items():
        st, d = req(KB + f"/s/finops/api/dashboards/{did}", kibana=True)
        if st != 200:
            print("hbar upsert skip", did, st)
            continue
        data = d["data"]
        placed = []
        for item in items:
            panel = native_hbar_panel(item)
            layout = HBAR_LAYOUT[item["panel_id"]]
            sid = layout.get("section_id")
            pid = panel["id"]
            if sid:
                sec = next((p for p in data.get("panels") or [] if p.get("id") == sid), None)
                if not sec:
                    print("hbar missing section", did, sid)
                    continue
                inner = [p for p in (sec.get("panels") or []) if p.get("id") != pid]
                inner.append(panel)
                sec["panels"] = inner
            else:
                data["panels"] = [p for p in data.get("panels") or [] if p.get("id") != pid]
                data["panels"].append(panel)
            placed.append(pid)
        payload = {
            "title": data.get("title"),
            "description": data.get("description") or "",
            "time_range": data.get("time_range"),
            "query": data.get("query"),
            "filters": data.get("filters") or [],
            "tags": data.get("tags") or [],
            "options": data.get("options"),
            "panels": data.get("panels"),
        }
        st, body = req(KB + f"/s/finops/api/dashboards/{did}", "PUT", payload, kibana=True)
        types = []
        if st < 400:

            def find(panels, pid):
                for p in panels or []:
                    if p.get("id") == pid:
                        return p
                    r = find(p.get("panels"), pid)
                    if r:
                        return r

            for pid in placed:
                p = find(body["data"].get("panels"), pid)
                ly = ((p or {}).get("config") or {}).get("layers") or [{}]
                types.append((pid[:8], (p or {}).get("type"), ly[0].get("type")))
        print(
            "hbar upsert",
            did,
            st,
            types or placed,
            (body.get("message") or "")[:160] if st >= 400 else "",
        )


def install_vega_bars():
    """Vega-Lite specs as vis SOs; live panels are native bar_horizontal (dash API)."""
    publish_vega_bar_visualizations()
    upsert_native_hbar_panels()
    install_hub_tabs()


SVS_KEEP = {
    "finops-hub-tabs",
    "svs-bill",
    "svs-id",
    "svs-cap",
    "svs-park",
    "svs-ess-kpi",
    "svs-ess",
}
SVS_GRIDS = {
    "svs-bill": (0, 11, 12, 6),
    "svs-id": (12, 11, 12, 6),
    "svs-cap": (24, 11, 12, 6),
    "svs-park": (36, 11, 12, 6),
    "svs-ess-kpi": (0, 87, 12, 6),
    "svs-ess": (12, 87, 36, 12),
}


def upgrade_spend_vs_savings():
    """Replace static SVS tables/pie with Vega-Lite-inspired native charts."""
    for name, q in verify_svs_queries():
        st, body = req(ES + "/_query", "POST", {"query": q})
        if st >= 400 or "error" in body:
            print("svs query FAIL", name, st, (body.get("error") or body))
        else:
            print("svs query OK", name, "rows", len(body.get("values") or []))
    vis_dir = ROOT / "kibana"
    vis_dir.mkdir(exist_ok=True)
    for item in SVS_VEGA_VIS:
        payload = svs_vis_so_payload(item)
        (vis_dir / f"{item['vis_id']}.json").write_text(
            json.dumps(payload, indent=2) + "\n"
        )
        st, body = req(
            KB
            + f"/s/finops/api/saved_objects/visualization/{item['vis_id']}?overwrite=true",
            "POST",
            payload,
            kibana=True,
        )
        print(
            "svs vega vis",
            item["vis_id"],
            st,
            body.get("id") if st < 400 else (body.get("message") or body),
        )
    st, d = req(KB + f"/s/finops/api/dashboards/{SVS_ID}", kibana=True)
    if st != 200:
        print("svs upgrade skip", st, d.get("message") if isinstance(d, dict) else d)
        return st
    data = d["data"]
    kept = []
    for p in data.get("panels") or []:
        pid = p.get("id")
        if pid not in SVS_KEEP:
            continue
        if pid in SVS_GRIDS:
            x, y, w, h = SVS_GRIDS[pid]
            p["grid"] = {"x": x, "y": y, "w": w, "h": h}
        kept.append(p)
    panels = kept + svs_chart_panels()
    payload = {
        "title": data.get("title"),
        "description": data.get("description") or "",
        "time_range": data.get("time_range") or {"from": "now-30d", "to": "now"},
        "query": data.get("query"),
        "filters": data.get("filters") or [],
        "tags": data.get("tags") or [],
        "options": data.get("options"),
        "panels": panels,
        "pinned_panels": data.get("pinned_panels") or [],
    }
    st, body = req(KB + f"/s/finops/api/dashboards/{SVS_ID}", "PUT", payload, kibana=True)
    n = len(((body.get("data") or {}).get("panels") or [])) if st < 400 else 0
    print(
        "svs upgrade",
        st,
        f"panels={n}" if st < 400 else (body.get("message") or body),
    )
    if st < 400:
        (ROOT / "kibana/spend-vs-savings-dashboard-api.json").write_text(
            json.dumps(body.get("data") or payload, indent=2) + "\n"
        )
        wanted = {
            "svs-xy": ("xy", "area_stacked"),
            "svs-pie": ("waffle", None),
            "svs-heat": ("heatmap", None),
            "svs-spend-acct": ("xy", "bar_horizontal"),
            "svs-id-acct": ("xy", "bar_horizontal"),
            "svs-svc": ("xy", "bar_horizontal"),
            "svs-act": ("xy", "bar_horizontal"),
            "svs-scatter": ("xy", "line"),
            "svs-act-heat": ("heatmap", None),
        }

        def find(ps, pid):
            for p in ps or []:
                if p.get("id") == pid:
                    return p
                r = find(p.get("panels"), pid)
                if r:
                    return r

        live = (body.get("data") or {}).get("panels") or []
        for pid, (ctype, layer) in wanted.items():
            p = find(live, pid)
            got_c = (p.get("config") or {}).get("type") if p else None
            got_l = ((p.get("config") or {}).get("layers") or [{}])[0].get("type")
            ok = p and got_c == ctype and (layer is None or got_l == layer)
            print("svs panel", pid, "OK" if ok else f"FAIL {got_c}/{got_l}")
        install_hub_tabs(ids=[SVS_ID])
        print(
            "svs url",
            KB + f"/s/finops/app/dashboards#/view/{SVS_ID}",
        )
    return st


def cleanup_vega_probes():
    vis_ids = [
        "gev-finops-vega-probe",
        "gev-finops-vega-bar-vis",
    ]
    dash_ids = [
        "gev-finops-vega-probe-a",
        "gev-finops-vega-probe-b",
        "gev-finops-vega-probe-c",
        "gev-finops-vega-probe-d",
        "gev-finops-vega-probe-so",
        "gev-finops-vega-probe-mix",
        "gev-finops-vega-probe-clone",
        "gev-finops-vega-probe-heat",
        "gev-finops-vega-probe-rds",
        "gev-finops-vega-probe-scatter",
        "gev-finops-vega-probe-scatter2",
        "gev-finops-vega-probe-metric",
        "gev-finops-vega-probe-ctrl",
        "gev-finops-vega-probe-pts",
        "gev-finops-vega-bar-probe",
        "gev-finops-vega-so-probe",
        "gev-finops-hbar-probe",
    ]
    for so_id in vis_ids:
        st, _ = req(
            KB + f"/s/finops/api/saved_objects/visualization/{so_id}",
            "DELETE",
            kibana=True,
        )
        print("cleanup visualization", so_id, st)
    for so_id in dash_ids:
        st, _ = req(
            KB + f"/s/finops/api/saved_objects/dashboard/{so_id}",
            "DELETE",
            kibana=True,
        )
        print("cleanup dashboard", so_id, st)


def rec_id_for_arn(arn):
    st, body = req(
        ES + "/logs-finops.rightsizing-default/_search",
        "POST",
        {
            "size": 1,
            "sort": [{"@timestamp": "desc"}],
            "_source": ["finops.rightsizing.id"],
            "query": {"term": {"finops.rightsizing.resource_arn": arn}},
        },
    )
    hits = (body.get("hits") or {}).get("hits") or []
    if not hits:
        return None
    return ((hits[0].get("_source") or {}).get("finops") or {}).get("rightsizing", {}).get("id")


def put_custom_field(payload, key, value, ftype="text"):
    fields = payload.setdefault("customFields", [])
    for f in fields:
        if f.get("key") == key:
            f["value"] = value
            return
    fields.append({"key": key, "type": ftype, "value": value})


def find_case_by_title(title):
    st, body = req(
        KB + "/s/finops/api/cases/_find?perPage=50&owner=observability",
        kibana=True,
    )
    for c in body.get("cases") or []:
        if c.get("title") == title:
            return c
    return None


def create_or_patch_case(rel, rightsizing_id, force_status=None):
    payload = load(rel)
    if rightsizing_id:
        put_custom_field(payload, "rightsizing-id", rightsizing_id)
    desired_status = force_status or payload.pop("status", None)
    existing = find_case_by_title(payload["title"])
    if existing:
        patch = {
            "cases": [
                {
                    "id": existing["id"],
                    "version": existing["version"],
                    "title": payload["title"],
                    "description": payload["description"],
                    "tags": payload.get("tags") or [],
                    "category": payload.get("category"),
                    "customFields": payload.get("customFields") or [],
                }
            ]
        }
        if desired_status:
            patch["cases"][0]["status"] = desired_status
        st, body = req(KB + "/s/finops/api/cases", "PATCH", patch, kibana=True)
        cid = ((body.get("cases") or [{}])[0].get("id") if isinstance(body, dict) else None)
        print("case patch", payload["title"], st, cid or body.get("message"))
        return cid or existing["id"]
    st, body = req(KB + "/s/finops/api/cases", "POST", payload, kibana=True)
    cid = body.get("id")
    print("case create", payload["title"], st, cid or body.get("message"))
    if st == 200 and desired_status and desired_status != "open":
        st2, body2 = req(
            KB + "/s/finops/api/cases",
            "PATCH",
            {
                "cases": [
                    {
                        "id": body["id"],
                        "version": body["version"],
                        "status": desired_status,
                    }
                ]
            },
            kibana=True,
        )
        print("case status", desired_status, st2, body2.get("message") if st2 >= 400 else "ok")
    return cid


def attach_rec(arn, case_id, status):
    st, ubq = req(
        ES + "/logs-finops.rightsizing-default/_update_by_query?refresh=true",
        "POST",
        {
            "query": {"term": {"finops.rightsizing.resource_arn": arn}},
            "script": {
                "lang": "painless",
                "source": (
                    "ctx._source.finops.rightsizing.case_id = params.cid; "
                    "ctx._source.finops.rightsizing.status = params.status;"
                    "if (params.status == 'hidden' && "
                    "(ctx._source.finops.rightsizing.hidden_reason == null || "
                    "ctx._source.finops.rightsizing.hidden_reason == '')) {"
                    "  ctx._source.finops.rightsizing.hidden_reason = 'seeded_sample';"
                    "}"
                ),
                "params": {"cid": case_id, "status": status},
            },
        },
    )
    print("attach rec", status, arn.split("/")[-1], st, ubq.get("updated"))


def check_nat_namespaces():
    for pid in AWS_POLICY_IDS:
        st, body = req(KB + f"/api/fleet/package_policies/{pid}", kibana=True)
        item = body.get("item") or body
        name = item.get("name")
        yaml = ""
        for inp in item.get("inputs") or []:
            for s in inp.get("streams") or []:
                if (s.get("data_stream") or {}).get("dataset") == "aws.cloudwatch_metrics":
                    yaml = ((s.get("vars") or {}).get("metrics") or {}).get("value") or ""
        print(
            "cw namespaces",
            name,
            "NAT",
            "AWS/NATGateway" in yaml,
            "S3SL",
            "AWS/S3/Storage-Lens" in yaml,
        )


ESS_BILLING_POLICY_ID = "62b6de1c-f8b4-43b7-938e-56b0358080bd"
ESS_CREDITS_FINOPS_ID = "952b4e0a-1a55-4794-8c57-d26b8c6d9086"
ESS_CREDITS_PACKAGE_ID = "ess_billing-creditsdashboard"


def enable_ess_credits_stream(policy_id):
    """Turn on metrics-ess_billing.credits without rotating the billing API key."""
    st, mi = req(KB + f"/api/fleet/managed_integrations/{policy_id}", kibana=True)
    if st != 200:
        print("ess_billing managed get", st, mi.get("message") if isinstance(mi, dict) else mi)
        return False
    item = mi.get("item") or mi
    inputs = item.get("inputs") or {}
    cel = inputs.get("ESS Billing-cel") or {}
    streams = cel.get("streams") or {}
    credits = streams.get("ess_billing.credits") or {}
    if credits.get("enabled"):
        print("ess_billing credits stream already enabled")
        return True
    credits["enabled"] = True
    streams["ess_billing.credits"] = credits
    cel["streams"] = streams
    inputs["ESS Billing-cel"] = cel
    payload = {
        "name": item.get("name"),
        "namespace": item.get("namespace"),
        "description": item.get("description") or "",
        "package": {
            "name": "ess_billing",
            "version": (item.get("package") or {}).get("version") or "1.9.1",
        },
        "inputs": inputs,
    }
    st, body = req(KB + f"/api/fleet/managed_integrations/{policy_id}", "PUT", payload, kibana=True)
    enabled = (
        (((body.get("item") or body).get("inputs") or {})
         .get("ESS Billing-cel") or {})
        .get("streams", {})
        .get("ess_billing.credits", {})
        .get("enabled")
    )
    print("ess_billing credits enable", st, enabled if st < 400 else body.get("message") or body)
    return st < 400 and bool(enabled)


def restore_ess_credits_panels():
    """FinOps copy dropped Vega/markdown; copy them from the package dashboard."""
    st, default = req(
        KB + f"/s/default/api/saved_objects/dashboard/{ESS_CREDITS_PACKAGE_ID}",
        kibana=True,
    )
    st2, finops = req(
        KB + f"/s/finops/api/saved_objects/dashboard/{ESS_CREDITS_FINOPS_ID}",
        kibana=True,
    )
    if st != 200 or st2 != 200:
        print("ess credits restore skip", st, st2)
        return
    d_panels = json.loads(default["attributes"].get("panelsJSON") or "[]")
    f_panels = json.loads(finops["attributes"].get("panelsJSON") or "[]")
    f_ids = {p.get("panelIndex") for p in f_panels}
    y_shift = 4 if any(p.get("panelIndex") == "finops-hub-tabs" for p in f_panels) else 0
    added = []
    for p in d_panels:
        pid = p.get("panelIndex")
        if pid in f_ids:
            continue
        panel = json.loads(json.dumps(p))
        g = panel.get("gridData") or {}
        g["y"] = int(g.get("y") or 0) + y_shift
        panel["gridData"] = g
        f_panels.append(panel)
        added.append(pid)
    d_refs = default.get("references") or []
    f_refs = finops.get("references") or []
    names = {r.get("name") for r in f_refs}
    skip_ids = {ESS_CREDITS_PACKAGE_ID, "ess_billing-billingdashboard"}
    extra_refs = [
        r
        for r in d_refs
        if r.get("name") not in names
        and not (r.get("type") == "dashboard" and r.get("id") in skip_ids)
    ]
    attrs = dict(finops["attributes"])
    if default["attributes"].get("controlGroupInput") and not attrs.get("controlGroupInput"):
        attrs["controlGroupInput"] = default["attributes"]["controlGroupInput"]
    if added or extra_refs or attrs.get("controlGroupInput") != finops["attributes"].get("controlGroupInput"):
        attrs["panelsJSON"] = json.dumps(f_panels)
        st, body = req(
            KB + f"/s/finops/api/saved_objects/dashboard/{ESS_CREDITS_FINOPS_ID}?overwrite=true",
            "POST",
            {"attributes": attrs, "references": f_refs + extra_refs},
            kibana=True,
        )
        print("ess credits restore", st, "added", added or "none")
    else:
        print("ess credits panels already complete")


def install_ess_billing():
    st, body = req(
        KB + "/api/fleet/epm/packages/ess_billing/1.9.1",
        "POST",
        {"force": True},
        kibana=True,
    )
    print("ess_billing package", st, body.get("items") and "ok" or body.get("message") or (body.get("response") and "ok") or st)

    org = os.environ.get("ESS_ORG_ID") or os.environ.get("ELASTIC_ORG_ID") or "3727967088"
    key = os.environ.get("ESS_BILLING_API_KEY") or os.environ.get("ELASTIC_CLOUD_BILLING_API_KEY")
    st, existing = req(
        KB + "/api/fleet/package_policies?kuery=ingest-package-policies.package.name:ess_billing",
        kibana=True,
    )
    items = existing.get("items") or []
    policy_id = (items[0].get("id") if items else None) or ESS_BILLING_POLICY_ID
    if items:
        print("ess_billing policy exists", items[0].get("id"), items[0].get("name"))
        enable_ess_credits_stream(policy_id)
    elif not org or not key:
        print("ess_billing skipped: set ESS_ORG_ID and ESS_BILLING_API_KEY")
    else:
        payload = load("kibana/ess_billing-policy.json")
        payload["inputs"]["ESS Billing-cel"]["vars"]["organization_id"] = int(org) if str(org).isdigit() else org
        payload["inputs"]["ESS Billing-cel"]["vars"]["api_key"] = key
        st, body = req(KB + "/api/fleet/managed_integrations", "POST", payload, kibana=True)
        if st >= 400:
            st, body = req(KB + "/api/fleet/agentless_policies", "POST", payload, kibana=True)
        print("ess_billing install", st, body.get("item", body).get("id") if st < 400 else body.get("message") or body)

    st, ds = req(ES + "/_data_stream/metrics-ess_billing.credits-default", "PUT")
    if st == 400 and "already exists" in json.dumps(ds):
        print("ess credits data_stream exists")
    else:
        print("ess credits data_stream", st, ds if st >= 400 else "ok")

    ensure_data_view(
        "metrics-ess_billing.credits-*", "Elastic Cloud credits", allow_no_index=True
    )
    restore_ess_credits_panels()

    st, copy = req(
        KB + "/api/spaces/_copy_saved_objects",
        "POST",
        {
            "objects": [{"type": "dashboard", "id": "ess_billing-billingdashboard"}],
            "spaces": ["finops"],
            "includeReferences": True,
            "overwrite": True,
            "createNewCopies": False,
        },
        kibana=True,
    )
    print("ess_billing dashboard copy", st, (copy.get("finops") or {}).get("success") if isinstance(copy, dict) else copy)


def main():
    st, body = req(
        ES + "/_ingest/pipeline/finops-rightsizing",
        "PUT",
        load("elasticsearch/ingest-pipeline.json"),
    )
    print("pipeline", st, body if st >= 400 else "ok")

    st, body = req(
        ES + "/_index_template/logs-finops.rightsizing",
        "PUT",
        load("elasticsearch/index-template.json"),
    )
    print("index_template", st, body if st >= 400 else "ok")

    st, body = req(ES + "/_data_stream/logs-finops.rightsizing-default", "PUT")
    if st == 400 and "already exists" in json.dumps(body):
        print("data_stream exists")
    else:
        print("data_stream", st, body if st >= 400 else "ok")

    st, del_body = req(
        ES + "/logs-finops.rightsizing-default/_delete_by_query?refresh=true&conflicts=proceed",
        "POST",
        {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"finops.rightsizing.hidden_reason": "seeded_sample"}},
                        {"term": {"@timestamp": SEED_TS}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        },
    )
    print("delete seeded samples only", st, del_body.get("deleted"))

    skip_samples = os.environ.get("SKIP_SAMPLES", "0") == "1"
    if skip_samples:
        print("SKIP_SAMPLES=1, not reseeding")
    else:
        ndjson = (ROOT / "sample/recommendations.ndjson").read_text().strip().splitlines()
        bulk = []
        for line in ndjson:
            doc = json.loads(line)
            rs = doc.setdefault("finops", {}).setdefault("rightsizing", {})
            rs["hidden_reason"] = "seeded_sample"
            bulk.append('{"create":{}}')
            bulk.append(json.dumps(doc, separators=(",", ":")))
        st, bulk_res = req(
            ES + "/logs-finops.rightsizing-default/_bulk?refresh=true",
            "POST",
            ("\n".join(bulk) + "\n").encode(),
            content_type="application/x-ndjson",
        )
        print("sample bulk errors", (bulk_res or {}).get("errors"))

    req(ES + "/_transform/finops-rightsizing-latest/_stop?wait_for_completion=true&force=true", "POST")
    req(ES + "/_transform/finops-rightsizing-latest/_reset", "POST")

    st, tbody = req(
        ES + "/_index_template/finops-rightsizing-latest",
        "PUT",
        load("elasticsearch/latest-index-template.json"),
    )
    print("latest_index_template", st, tbody if st >= 400 else "ok")
    st, tbody = req(
        ES + "/_transform/finops-rightsizing-latest",
        "PUT",
        load("elasticsearch/transform-latest.json"),
    )
    if st == 400 and "already exists" in json.dumps(tbody):
        print("transform exists")
    else:
        print("transform put", st, tbody if st >= 400 else "ok")
    req(ES + "/_transform/finops-rightsizing-latest/_start", "POST")

    dv_id = ensure_data_view(DATA_VIEW_TITLE, "FinOps Rightsizing")
    ec2_id = ensure_data_view("metrics-aws.ec2_metrics-*", "AWS EC2 metrics")
    cw_id = ensure_data_view("metrics-aws.cloudwatch_metrics-*", "AWS CloudWatch metrics")
    billing_id = ensure_data_view("metrics-aws.billing-*", "AWS Cost Explorer billing")
    ess_id = ensure_data_view("metrics-ess_billing.billing-*", "Elastic Cloud billing", allow_no_index=True)
    ensure_data_view(
        "metrics-ess_billing.credits-*", "Elastic Cloud credits", allow_no_index=True
    )

    if dv_id:
        publish_rightsizing_overview(dv_id)
    if dv_id and billing_id:
        attrs2, refs2 = build_spend_vs_savings(dv_id, billing_id, ess_id or billing_id)
        put_dashboard("finops-spend-vs-savings", attrs2, refs2)
        (ROOT / "kibana/spend-vs-savings-saved-object.json").write_text(
            json.dumps({"attributes": attrs2, "references": refs2}, indent=2)
        )
        upgrade_spend_vs_savings()
    if billing_id:
        attrs3, refs3 = build_billing_overview(billing_id)
        put_dashboard("finops-aws-billing-overview-unblended", attrs3, refs3)
        (ROOT / "kibana/aws-billing-overview-saved-object.json").write_text(
            json.dumps({"attributes": attrs3, "references": refs3}, indent=2)
        )

    install_hub_tabs()

    st, cfg = req(KB + "/s/finops/api/cases/configure?owner=observability", kibana=True)
    print("cases configure", st, "exists" if cfg else "empty")

    rec_dev = rec_id_for_arn(APM_DEV_ARN)
    rec_stg = rec_id_for_arn(STAGE_ARN)
    rec_hid = rec_id_for_arn(HIDDEN_ARN)
    rec_done = rec_id_for_arn(DONE_ARN)

    inprog = find_case_by_title("Rightsizing: actions-runner m5.large to t3.medium")
    if not inprog:
        existing_old = None
        st, body = req(KB + f"/s/finops/api/cases/{EXISTING_CASE_ID}", kibana=True)
        if st == 200 and body.get("id"):
            existing_old = body
        if existing_old:
            payload = load("kibana/cases/in-progress-actions-runner.json")
            if rec_dev:
                put_custom_field(payload, "rightsizing-id", rec_dev)
            st, body = req(
                KB + "/s/finops/api/cases",
                "PATCH",
                {
                    "cases": [
                        {
                            "id": EXISTING_CASE_ID,
                            "version": existing_old["version"],
                            "title": payload["title"],
                            "description": payload["description"],
                            "tags": payload["tags"],
                            "category": payload["category"],
                            "customFields": payload["customFields"],
                            "status": "in-progress",
                        }
                    ]
                },
                kibana=True,
            )
            print("retarget existing case", st, body.get("message") if st >= 400 else EXISTING_CASE_ID)
            cid_inprog = EXISTING_CASE_ID
        else:
            cid_inprog = create_or_patch_case(
                "kibana/cases/in-progress-actions-runner.json", rec_dev, "in-progress"
            )
    else:
        cid_inprog = create_or_patch_case(
            "kibana/cases/in-progress-actions-runner.json", rec_dev, "in-progress"
        )

    cid_open = create_or_patch_case("kibana/cases/open-ai-bridge.json", rec_stg)
    cid_done = create_or_patch_case(
        "kibana/cases/closed-sample-worker.json", rec_done, "closed"
    )
    cid_hid = create_or_patch_case("kibana/cases/infeasible-idle-ebs.json", rec_hid)

    if skip_samples:
        print("skip attach_rec (samples not seeded)")
    else:
        if cid_inprog:
            attach_rec(APM_DEV_ARN, cid_inprog, "in_progress")
        if cid_open:
            attach_rec(STAGE_ARN, cid_open, "open")
        if cid_done:
            attach_rec(DONE_ARN, cid_done, "done")
        if cid_hid:
            attach_rec(HIDDEN_ARN, cid_hid, "hidden")

    st, existing_rule = req(
        KB + "/s/finops/api/alerting/rule/gev-finops-alert-service-dod-spike",
        kibana=True,
    )
    if st == 200 and existing_rule.get("id"):
        print("alert exists gev-finops-alert-service-dod-spike")
    else:
        rule = load("kibana/alert-service-dod.json")
        st, body = req(
            KB + "/s/finops/api/alerting/rule/gev-finops-alert-service-dod-spike",
            "POST",
            rule,
            kibana=True,
        )
        print("alert create", st, body.get("id") or body.get("message") or body)

    check_nat_namespaces()
    install_ess_billing()

    q = (
        "FROM logs-finops.rightsizing-*\n"
        "| WHERE @timestamp > NOW() - 14 days\n"
        "| STATS recs = COUNT_DISTINCT(finops.rightsizing.id),\n"
        "        estimated_usd = SUM(finops.rightsizing.estimated_monthly_savings),\n"
        "        realized_usd = SUM(finops.rightsizing.realized_savings)\n"
        "    BY finops.rightsizing.status\n"
        "| SORT recs DESC"
    )
    st, body = req(ES + "/_query", "POST", {"query": q})
    print("esql status_summary", st, (body or {}).get("values"))

    q2 = (
        "FROM metrics-aws.ec2_metrics-*\n"
        "| WHERE @timestamp > NOW() - 14 days AND cloud.instance.id == \"i-09c920d4ff962442f\"\n"
        "| STATS cpu_avg = AVG(aws.ec2.metrics.CPUUtilization.avg), docs = COUNT(*)"
    )
    st, body = req(ES + "/_query", "POST", {"query": q2})
    print("esql evidence actions-runner", st, (body or {}).get("values"))


def merge_case_fields():
    extra = load("kibana/cases/configure-fields.json")
    st, body = req(KB + "/s/finops/api/cases/configure", kibana=True)
    existing = None
    if st == 200:
        if isinstance(body, list) and body:
            existing = next(
                (c for c in body if c.get("owner") == "observability"), body[0]
            )
        elif isinstance(body, dict) and body.get("id"):
            existing = body
    if not existing:
        print("cases configure missing; skip merge")
        return
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
    t_added = 0
    for t in extra.get("templates") or []:
        if t["key"] not in t_keys:
            templates.append(t)
            t_added += 1
    if added == 0 and t_added == 0:
        print(
            "cases configure unchanged",
            "fields",
            len(fields),
            "templates",
            len(templates),
        )
        return existing
    st, body = req(
        KB + f"/s/finops/api/cases/configure/{existing['id']}",
        "PATCH",
        {
            "version": existing["version"],
            "customFields": fields,
            "templates": templates,
        },
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


def upsert_workflow(workflow_id: str):
    yaml_text = (ROOT / "kibana" / "workflows" / f"{workflow_id}.yaml").read_text()
    st, body = req(
        KB + f"/s/finops/api/workflows/workflow/{workflow_id}",
        "PUT",
        {"yaml": yaml_text},
        kibana=True,
    )
    if st == 404:
        st, body = req(
            KB + "/s/finops/api/workflows/workflow",
            "POST",
            {"id": workflow_id, "yaml": yaml_text},
            kibana=True,
        )
    print(
        "workflow",
        workflow_id,
        st,
        "valid"
        if isinstance(body, dict) and body.get("valid")
        else (body.get("message") if isinstance(body, dict) else body),
        "enabled" if isinstance(body, dict) and body.get("enabled") else "",
    )
    if isinstance(body, dict) and body.get("valid") is False:
        err = ROOT / "kibana" / f"{workflow_id}-invalid.json"
        err.write_text(json.dumps(body, indent=2)[:8000])
        print("workflow invalid ->", err)
    return body


def _agent_builder_payload(path: Path):
    raw = json.loads(path.read_text())
    for key in (
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "readonly",
        "permissions",
        "experimental",
        "schema",
        "confirmation",
    ):
        raw.pop(key, None)
    return raw


def upsert_agent_builder(kind: str, item_id: str, rel: str):
    src = ROOT / rel
    create_body = _agent_builder_payload(src)
    update_body = {k: v for k, v in create_body.items() if k not in ("id", "type")}
    collection = "tools" if kind == "tool" else "agents"
    st, body = req(
        KB + f"/s/finops/api/agent_builder/{collection}/{item_id}", kibana=True
    )
    if st == 200:
        st, body = req(
            KB + f"/s/finops/api/agent_builder/{collection}/{item_id}",
            "PUT",
            update_body,
            kibana=True,
        )
    else:
        st, body = req(
            KB + f"/s/finops/api/agent_builder/{collection}",
            "POST",
            create_body,
            kibana=True,
        )
    print(
        kind,
        item_id,
        st,
        body.get("id") if isinstance(body, dict) else body,
        body.get("message") if isinstance(body, dict) and st >= 400 else "",
    )
    if st >= 400 and isinstance(body, dict):
        err = ROOT / "kibana" / f"{item_id}-error.json"
        err.write_text(json.dumps(body, indent=2)[:4000])
    return body


def workflow_rule_action(workflow_id: str):
    return {
        "group": "query matched",
        "id": WORKFLOW_CONNECTOR_ID,
        "params": {
            "subAction": "run",
            "subActionParams": {
                "workflowId": workflow_id,
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


def attach_spike_workflow(rule_id: str):
    st, existing = req(KB + f"/s/finops/api/alerting/rule/{rule_id}", kibana=True)
    if st != 200 or not existing.get("id"):
        print("rule missing; skip workflow action", rule_id, st)
        return st
    actions = []
    for action in existing.get("actions") or []:
        if action.get("id") == WORKFLOW_CONNECTOR_ID:
            continue
        item = {
            "group": action.get("group") or "query matched",
            "id": action["id"],
            "params": action.get("params") or {},
        }
        if action.get("frequency") is not None:
            item["frequency"] = action["frequency"]
        if action.get("uuid"):
            item["uuid"] = action["uuid"]
        actions.append(item)
    actions.append(workflow_rule_action(SPIKE_WORKFLOW_ID))
    payload = {
        "name": existing["name"],
        "tags": existing.get("tags") or [],
        "schedule": existing["schedule"],
        "params": existing["params"],
        "actions": actions,
    }
    st, body = req(
        KB + f"/s/finops/api/alerting/rule/{rule_id}",
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


def verify_agentic_queries():
    checks = [
        (
            "aws-spend",
            "FROM metrics-aws.billing-*\n"
            "| WHERE @timestamp > NOW() - 30 days "
            'AND aws.billing.group_definition.key == "LINKED_ACCOUNT"\n'
            "| STATS total_spend = SUM(aws.billing.UnblendedCost.amount)",
        ),
        (
            "slo-posture",
            "FROM .slo-observability.summary-v3.6\n"
            '| WHERE slo.id LIKE "gev-finops-slo-*" OR slo.id LIKE "meridian-slo-*"\n'
            "| KEEP slo.id, slo.name, errorBudgetRemaining",
        ),
        (
            "rightsizing-queue",
            "FROM logs-finops.rightsizing-*\n"
            "| WHERE @timestamp > NOW() - 90 days "
            'AND finops.rightsizing.status IN ("open", "in_progress")\n'
            "| STATS recs = COUNT_DISTINCT(finops.rightsizing.id)",
        ),
        (
            "low-cpu",
            "FROM metrics-aws.ec2_metrics-*\n"
            "| WHERE @timestamp > NOW() - 14 days\n"
            "| STATS cpu_avg = AVG(aws.ec2.metrics.CPUUtilization.avg) "
            "BY cloud.instance.id\n"
            "| WHERE cpu_avg < 5\n"
            "| LIMIT 3",
        ),
        (
            "rds-idle",
            "FROM metrics-aws.rds-*\n"
            "| WHERE @timestamp > NOW() - 14 days "
            "AND aws.rds.metrics.DBLoad.avg IS NOT NULL\n"
            "| STATS dbload_avg = AVG(aws.rds.metrics.DBLoad.avg) "
            "BY aws.dimensions.DBInstanceIdentifier\n"
            "| SORT dbload_avg ASC\n"
            "| LIMIT 3",
        ),
    ]
    for name, q in checks:
        st, body = req(ES + "/_query", "POST", {"query": q})
        if st >= 400 or "error" in body:
            print("verify FAIL", name, st, (body.get("error") or body))
        else:
            print("verify OK", name, "rows", len(body.get("values") or []))


def install_agentic_stack():
    st, body = req(
        ES + "/_ingest/pipeline/finops-rightsizing",
        "PUT",
        load("elasticsearch/ingest-pipeline.json"),
    )
    print("pipeline", st, body if st >= 400 else "ok")
    merge_case_fields()
    upsert_workflow(SPIKE_WORKFLOW_ID)
    upsert_workflow(RIGHTSIZE_WORKFLOW_ID)
    upsert_workflow(SPIKE_AUTO_WORKFLOW_ID)
    upsert_workflow(RIGHTSIZE_AUTO_WORKFLOW_ID)
    for tool_id in ESQL_TOOL_IDS:
        upsert_agent_builder("tool", tool_id, f"kibana/tools/{tool_id}.json")
    for tool_id in WORKFLOW_TOOL_IDS:
        upsert_agent_builder("tool", tool_id, f"kibana/tools/{tool_id}.json")
    upsert_agent_builder("agent", AGENT_ID, f"kibana/agents/{AGENT_ID}.json")
    for rule_id in SPIKE_RULE_IDS:
        attach_spike_workflow(rule_id)
    publish_rightsizing_overview()
    verify_agentic_queries()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if mode in ("demo", "all"):
        main()
    if mode == "vega":
        publish_rightsizing_overview()
        install_vega_bars()
        upgrade_spend_vs_savings()
        cleanup_vega_probes()
    if mode == "svs":
        upgrade_spend_vs_savings()
    if mode == "hub-tabs":
        install_hub_tabs()
    if mode in ("workflow", "all"):
        install_agentic_stack()
        install_hub_tabs()
    if mode not in ("demo", "all", "workflow", "vega", "hub-tabs", "svs"):
        print("usage: apply.py [demo|vega|svs|hub-tabs|workflow|all]")
        raise SystemExit(2)
