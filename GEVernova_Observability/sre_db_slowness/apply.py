#!/usr/bin/env python3
"""Apply SRE DB slowness walkthrough dashboard into the Kibana sre space.

Usage:
  ELASTIC_API_KEY=... python3 apply.py              # verify + dashboard
  ELASTIC_API_KEY=... python3 apply.py dashboard
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

from dashboards import (
    DASHBOARD_ID,
    DISCOVER_SEARCH_ID,
    build_discover_search,
    build_walkthrough_dashboard,
    verify_query_specs,
)

ROOT = Path(__file__).resolve().parent
ES = "https://my-observability-project-f2e495.es.us-west-2.aws.elastic.cloud:443"
KB = "https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud"
API_KEY = os.environ.get(
    "ELASTIC_API_KEY",
    "UnBSVGJhQUJKcXNqWTh1Yzc0TEk6Vm13c2dsYUlleC1hU1U3dnBYUndvZw==",
)
SPACE = "sre"
METRICS_DV_TITLE = "metrics-*"
TRACES_DV_TITLE = "traces-*"
LOGS_DV_TITLE = "logs-*"
APM_STATIC_DV_ID = "apm_static_data_view_id_sre"
# Full Kibana URL so the href is valid from classic Discover AND Lens.
# Kibana 9.4+ strips this from the APM static data view on APM load, and
# SRE Demo / logs / ingress views never inherited it. Re-apply everywhere
# that has trace.id. openLinkInCurrentTab so the data-grid click follows.
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
            "description": "SRE OpenSearch + K8s OOM + AppHub/Meridium + DB slowness views",
            "color": "#AA6556",
            "initials": "SR",
            "disabledFeatures": [],
        },
        kibana=True,
    )
    print("space create", st, body.get("id") or body.get("message") or body)


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


def dash_url(so_id=DASHBOARD_ID):
    return KB + f"/s/{SPACE}/app/dashboards#/view/{so_id}"


def discover_url(so_id=DISCOVER_SEARCH_ID):
    return (
        KB
        + f"/s/{SPACE}/app/discover#/view/{so_id}"
        + "?_g=(filters:!(),refreshInterval:(pause:!t,value:60000),time:(from:now-3d,to:now))"
    )


def install_discover():
    attrs = build_discover_search()
    (ROOT / "kibana").mkdir(exist_ok=True)
    out = ROOT / "kibana" / f"{DISCOVER_SEARCH_ID}.json"
    out.write_text(json.dumps({"attributes": attrs}, indent=2) + "\n")
    st, body = req(
        KB + f"/s/{SPACE}/api/saved_objects/search/{DISCOVER_SEARCH_ID}?overwrite=true",
        "POST",
        {"attributes": attrs},
        kibana=True,
    )
    tabs = (body.get("attributes") or {}).get("tabs") or []
    print(
        "discover",
        DISCOVER_SEARCH_ID,
        st,
        "tabs",
        [t.get("label") for t in tabs] if st < 400 else body.get("message") or body,
    )
    if st < 400:
        print("discover url", discover_url())
    req(
        KB + "/s/sre/api/saved_objects/search/gev-sre-db-walkthrough-search-probe",
        "DELETE",
        kibana=True,
    )
    return st


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


def _apply_trace_id_url_format(obj) -> int:
    """Put the APM URL formatter on every Lens/ES|QL column named trace.id."""
    n = 0
    if isinstance(obj, dict):
        field = obj.get("fieldName") or obj.get("columnId") or obj.get("column")
        if field in TRACE_ID_FORMAT_FIELDS:
            params = obj.setdefault("params", {})
            if params.get("format") != TRACE_ID_URL_FORMAT:
                params["format"] = TRACE_ID_URL_FORMAT
                n += 1
        for v in obj.values():
            n += _apply_trace_id_url_format(v)
    elif isinstance(obj, list):
        for v in obj:
            n += _apply_trace_id_url_format(v)
    return n


def ensure_trace_id_lens_urls():
    """Keep the traces table as Lens with a clickable trace.id.

    PUT /api/dashboards converts ES|QL Lens tables to vis data_table and
    drops column URL formatters (that API only formats number/percent/bytes/
    duration/custom). Stay on saved_objects so params.format survives.
    """
    st, so = req(
        KB + f"/s/{SPACE}/api/saved_objects/dashboard/{DASHBOARD_ID}",
        kibana=True,
    )
    if st != 200 or not isinstance(so, dict):
        print("trace.id lens skip; GET", st)
        return st
    attrs = so.get("attributes") or {}
    raw = attrs.get("panelsJSON")
    try:
        panels = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        print("trace.id lens skip; panelsJSON")
        return 400
    n = _apply_trace_id_url_format(panels)
    types = {
        p.get("panelIndex"): p.get("type")
        for p in panels
        if p.get("panelIndex") in ("db-tbl-tr", "db-tbl-logs", "db-tbl-webapi", "db-tbl-ing")
    }
    if n:
        attrs["panelsJSON"] = json.dumps(panels)
        st = put_dashboard(DASHBOARD_ID, attrs, so.get("references") or [])
    print("trace.id lens", types, "patched", n)
    return st


def snapshot_dashboard_api():
    """Read-only vis projection. Do not PUT — that strips trace.id links."""
    st, body = req(KB + f"/s/{SPACE}/api/dashboards/{DASHBOARD_ID}", kibana=True)
    if st != 200 or not isinstance(body, dict):
        print("dashboard api snapshot skip; GET", st)
        return st
    data = body.get("data") or {}
    (ROOT / "kibana" / f"{DASHBOARD_ID}-dash-api.json").write_text(
        json.dumps(data, indent=2) + "\n"
    )
    print("dashboard api snapshot", st, "panels", len(data.get("panels") or []))
    return st


def install_dashboard():
    ensure_data_view(METRICS_DV_TITLE, "All metrics")
    ensure_data_view(TRACES_DV_TITLE, "All traces")
    ensure_data_view(LOGS_DV_TITLE, "All logs")
    attrs, refs = build_walkthrough_dashboard()
    (ROOT / "kibana").mkdir(exist_ok=True)
    out = ROOT / "kibana" / f"{DASHBOARD_ID}.json"
    out.write_text(json.dumps({"attributes": attrs, "references": refs}, indent=2) + "\n")
    st = put_dashboard(DASHBOARD_ID, attrs, refs)
    link_st = ensure_trace_id_lens_urls()
    snap_st = snapshot_dashboard_api()
    disc_st = install_discover()
    if link_st >= 400:
        return link_st
    if snap_st >= 400:
        return snap_st
    if disc_st >= 400:
        return disc_st
    return st


def verify_queries():
    for name, q in verify_query_specs():
        st, body = req(ES + "/_query", "POST", {"query": q})
        if st >= 400 or "error" in body:
            print("verify FAIL", name, st, (body.get("error") or body))
        else:
            print("verify OK", name, "rows", len(body.get("values") or []))


def main(argv: list[str]):
    (ROOT / "kibana").mkdir(exist_ok=True)
    ensure_space()
    mode = argv[1] if len(argv) > 1 else "all"
    if mode in ("all", "verify"):
        verify_queries()
    if mode in ("all", "dashboard", "dashboards"):
        install_dashboard()
    if mode in ("discover",):
        install_discover()
    if mode not in ("all", "verify", "dashboard", "dashboards", "discover"):
        print("usage: apply.py [all|dashboard|discover|verify]")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
