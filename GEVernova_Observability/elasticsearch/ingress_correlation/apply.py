#!/usr/bin/env python3
"""Apply ALB/WAF trace.id @custom pipelines, lookup-waf-trace, and logs-ingress persist.

Fleet already invokes logs-aws.elb_logs@custom and logs-aws.waf@custom.
Serverless has no ingest index processor, so a latest transform copies slim WAF
docs into the lookup-mode index for ES|QL LOOKUP JOIN. A 5m Kibana workflow
then persists inner-join matches into the logs-ingress-default data stream.

Usage:
  python3 apply.py              # pipelines, lookup, transform, persist, workflow
  python3 apply.py persist      # LOOKUP JOIN → logs-ingress-default only
  python3 apply.py workflow     # scheduled persist workflow + data view
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ES = "https://my-observability-project-f2e495.es.us-west-2.aws.elastic.cloud:443"
KB = "https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud"
API_KEY = os.environ.get(
    "ELASTIC_API_KEY",
    "UnBSVGJhQUJKcXNqWTh1Yzc0TEk6Vm13c2dsYUlleC1hU1U3dnBYUndvZw==",
)
LOOKUP_INDEX = "lookup-waf-trace"
TRANSFORM_ID = "lookup-waf-trace-latest"
ALB_PIPE = "logs-aws.elb_logs@custom"
WAF_PIPE = "logs-aws.waf@custom"
SLIM_PIPE = "lookup-waf-trace-slim"
INGRESS_STREAM = "logs-ingress-default"
SPACE = "sre"
WORKFLOW_ID = "gev-sre-alb-waf-ingress-persist"
LEGACY_WORKFLOW_ID = "gev-sre-alb-waf-ingress-correlation"
BACKFILL = os.environ.get("SKIP_BACKFILL", "") != "1"
BACKFILL_RANGE = os.environ.get("BACKFILL_RANGE", "now-15m")
PERSIST_MINUTES = int(os.environ.get("PERSIST_MINUTES", "10"))
SKIP_PERSIST = os.environ.get("SKIP_PERSIST", "") == "1"
ctx = ssl.create_default_context()


def load(name):
    return json.loads((ROOT / name).read_text())


def req(url, method="GET", body=None, timeout=180, kibana=False, content_type="application/json"):
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
        with urllib.request.urlopen(r, context=ctx, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except Exception:
            parsed = {"raw": raw[:3000]}
        return e.code, parsed


def put_pipeline(name, filename):
    st, body = req(ES + "/_ingest/pipeline/" + urllib.parse.quote(name, safe="@"), "PUT", load(filename))
    print("pipeline", name, st, body.get("acknowledged", body.get("error", body)))
    if st >= 400:
        raise SystemExit(f"pipeline {name} failed")


def simulate_extract():
    alb_docs = [
        {
            "_source": {
                "aws": {"elb": {"trace_id": "Root=1-6aa850b0-69da838931433473766d3cdd"}},
                "trace": {"id": "Root=1-6aa850b0-69da838931433473766d3cdd"},
            }
        },
        {
            "_source": {
                "aws": {
                    "elb": {
                        "trace_id": "Self=1-aaa;Root=1-44b0d8aa-523f3f02c911e766a3fc1cbc;Parent=91e113d9ea9ccebf;Sampled=1"
                    }
                }
            }
        },
    ]
    st, sim = req(
        ES + "/_ingest/pipeline/" + urllib.parse.quote(ALB_PIPE, safe="@") + "/_simulate",
        "POST",
        {"docs": alb_docs},
    )
    ids = [
        ((d.get("doc") or {}).get("_source") or {}).get("trace", {}).get("id")
        for d in sim.get("docs") or []
    ]
    print("simulate alb", st, ids)
    if ids != [
        "1-6aa850b0-69da838931433473766d3cdd",
        "1-44b0d8aa-523f3f02c911e766a3fc1cbc",
    ]:
        raise SystemExit(f"ALB simulate unexpected: {ids} {json.dumps(sim)[:1500]}")

    waf_docs = [
        {
            "_source": {
                "aws": {
                    "waf": {
                        "arn": "arn:aws:wafv2:example",
                        "request": {
                            "headers": {
                                "X-Amzn-Trace-Id": "Root=1-efc982ed-efe16d9cbae9f8e5c057f444;Parent=abc;Sampled=1",
                                "Authorization": "should-not-be-read-as-trace",
                                "tenant": "5f03fb17-3af2-48e9-879b-4e08c8efa490",
                            }
                        },
                    }
                },
                "event": {"action": "ALLOW"},
                "rule": {"id": "WAFWhitelistRule1"},
            }
        }
    ]
    st, sim = req(
        ES + "/_ingest/pipeline/" + urllib.parse.quote(WAF_PIPE, safe="@") + "/_simulate",
        "POST",
        {"docs": waf_docs},
    )
    src = ((sim.get("docs") or [{}])[0].get("doc") or {}).get("_source") or {}
    print("simulate waf", st, src.get("trace"), "tnt", src.get("tnt"))
    if (src.get("trace") or {}).get("id") != "1-efc982ed-efe16d9cbae9f8e5c057f444":
        raise SystemExit(f"WAF simulate unexpected: {json.dumps(sim)[:2000]}")
    if src.get("tnt") != "5f03fb17-3af2-48e9-879b-4e08c8efa490":
        raise SystemExit(f"WAF tnt unexpected: {src.get('tnt')} {json.dumps(sim)[:2000]}")

    slim_docs = [
        {
            "_source": {
                "@timestamp": "2026-09-14T20:00:00.000Z",
                "trace": {"id": "1-efc982ed-efe16d9cbae9f8e5c057f444"},
                "event": {"action": "ALLOW"},
                "rule": {"id": "WAFWhitelistRule1"},
                "aws": {
                    "waf": {
                        "arn": "arn:aws:wafv2:example",
                        "request": {
                            "headers": {
                                "Authorization": "secret",
                                "tenant": "5f03fb17-3af2-48e9-879b-4e08c8efa490",
                            }
                        },
                    }
                },
                "http": {"request": {"id": "rid"}},
            }
        }
    ]
    st, sim = req(ES + f"/_ingest/pipeline/{SLIM_PIPE}/_simulate", "POST", {"docs": slim_docs})
    doc = (sim.get("docs") or [{}])[0].get("doc") or {}
    src = doc.get("_source") or {}
    print("simulate slim", st, "id", doc.get("_id"), "tnt", src.get("tnt"), "keys", sorted(src.keys()), "has_headers", "request" in ((src.get("aws") or {}).get("waf") or {}))
    if "Authorization" in json.dumps(src) or src.get("aws", {}).get("waf", {}).get("request"):
        raise SystemExit(f"slim pipeline leaked headers: {json.dumps(src)[:1500]}")
    if doc.get("_id") != "1-efc982ed-efe16d9cbae9f8e5c057f444":
        raise SystemExit(f"slim _id unexpected: {doc.get('_id')}")
    if src.get("tnt") != "5f03fb17-3af2-48e9-879b-4e08c8efa490":
        raise SystemExit(f"slim tnt unexpected: {src.get('tnt')}")


def ensure_lookup_index():
    spec = load("lookup-waf-trace-index.json")
    st, body = req(ES + f"/{LOOKUP_INDEX}")
    if st != 200:
        st, body = req(ES + f"/{LOOKUP_INDEX}", "PUT", spec)
        print("lookup index create", st, body.get("acknowledged", body.get("error", body)))
        if st >= 400:
            raise SystemExit("lookup index create failed")
        return
    print("lookup index exists", LOOKUP_INDEX)
    mapping = ((spec.get("mappings") or {}).get("properties") or {}).get("tnt")
    if mapping:
        st, body = req(
            ES + f"/{LOOKUP_INDEX}/_mapping",
            "PUT",
            {"properties": {"tnt": mapping}},
        )
        print("lookup mapping tnt", st, body.get("acknowledged", body.get("error", body)))
        if st >= 400:
            raise SystemExit("lookup tnt mapping failed")


def ensure_transform():
    spec = load("lookup-waf-trace-transform.json")
    st, body = req(ES + f"/_transform/{TRANSFORM_ID}")
    if st == 200:
        req(ES + f"/_transform/{TRANSFORM_ID}/_stop?wait_for_completion=true&force=true", "POST")
        st, body = req(
            ES + f"/_transform/{TRANSFORM_ID}/_update?defer_validation=true",
            "POST",
            spec,
        )
        print("transform update", st, body.get("acknowledged", body.get("error", body)))
    else:
        st, body = req(ES + f"/_transform/{TRANSFORM_ID}?defer_validation=true", "PUT", spec)
        print("transform create", st, body.get("acknowledged", body.get("error", body)))
    if st >= 400:
        raise SystemExit(f"transform failed: {body}")


def backfill():
    if not BACKFILL:
        print("skip backfill")
        return
    for index, pipeline in (
        ("logs-aws.elb_logs-default", ALB_PIPE),
        ("logs-aws.waf-default", WAF_PIPE),
    ):
        q = urllib.parse.urlencode(
            {
                "pipeline": pipeline,
                "conflicts": "proceed",
                "wait_for_completion": "true",
                "requests_per_second": "-1",
            }
        )
        st, body = req(
            ES + f"/{index}/_update_by_query?{q}",
            "POST",
            {"query": {"range": {"@timestamp": {"gte": BACKFILL_RANGE}}}},
            timeout=300,
        )
        print(
            "backfill",
            index,
            st,
            "updated",
            body.get("updated"),
            "total",
            body.get("total"),
            "failures",
            len(body.get("failures") or []),
            body.get("error", {}).get("type") if st >= 400 else "",
        )


def start_transform():
    st, body = req(ES + f"/_transform/{TRANSFORM_ID}/_start", "POST")
    print("transform start", st, body.get("acknowledged", body.get("error", body)))


def refresh_lookup_from_waf():
    """Re-slim recent WAF docs into lookup-waf-trace so tnt is present without a full transform reset."""
    if not BACKFILL:
        print("skip lookup refresh")
        return
    st, body = req(
        ES + "/_reindex?wait_for_completion=true&refresh=true",
        "POST",
        {
            "source": {
                "index": "logs-aws.waf-default",
                "query": {
                    "bool": {
                        "filter": [
                            {"range": {"@timestamp": {"gte": BACKFILL_RANGE}}},
                            {"exists": {"field": "trace.id"}},
                        ]
                    }
                },
            },
            "dest": {
                "index": LOOKUP_INDEX,
                "pipeline": SLIM_PIPE,
                "op_type": "index",
            },
        },
        timeout=300,
    )
    print(
        "lookup refresh",
        st,
        "created",
        body.get("created"),
        "updated",
        body.get("updated"),
        "total",
        body.get("total"),
        body.get("error", {}).get("type") if st >= 400 else "",
    )


def ensure_ingress_stream():
    st, body = req(ES + f"/_data_stream/{INGRESS_STREAM}")
    if st == 200:
        print("data stream exists", INGRESS_STREAM)
        return
    st, body = req(ES + f"/_data_stream/{INGRESS_STREAM}", "PUT")
    print("data stream create", INGRESS_STREAM, st, body.get("acknowledged", body.get("error", body)))
    if st >= 400:
        raise SystemExit("logs-ingress-default create failed")


def _as_number(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return value


def row_to_ingress_doc(rec: dict) -> dict:
    method = rec.get("http_method")
    path = rec.get("url_path")
    status = rec.get("http_status_code")
    message = rec.get("message") or " ".join(
        str(part) for part in (method, path, status) if part is not None
    )
    waf_action = rec.get("waf_action")
    doc = {
        "@timestamp": rec.get("alb_timestamp"),
        "message": message,
        "trace": {"id": rec.get("trace.id")},
        "source": {
            "ip": rec.get("source_ip"),
            "port": _as_number(rec.get("source_port")),
        },
        "url": {
            "domain": rec.get("url_domain"),
            "path": rec.get("url_path"),
        },
        "http": {
            "request": {
                "method": rec.get("http_method"),
                "id": rec.get("http_request_id"),
            },
            "response": {
                "status_code": _as_number(rec.get("http_status_code")),
            },
        },
        "user_agent": {"original": rec.get("ua")},
        "tnt": rec.get("tnt"),
        "event": {
            "action": waf_action,
            "kind": "event",
            "dataset": "ingress",
            "category": ["web"],
        },
        "rule": {"id": rec.get("rule_id")},
        "aws": {
            "elb": {
                "name": rec.get("elb_name"),
                "target_group": {"arn": rec.get("target_group_arn")},
                "action_executed": rec.get("action_executed"),
                "backend": {
                    "ip": rec.get("backend_ip"),
                    "port": _as_number(rec.get("backend_port")),
                },
                "request_processing_time": {
                    "sec": _as_number(rec.get("request_processing_time_sec")),
                },
                "target_status_code": _as_number(rec.get("target_status_code")),
            },
            "waf": {
                "action": waf_action,
                "arn": rec.get("waf_arn"),
            },
        },
    }
    tnt = rec.get("tnt")
    if tnt:
        doc["tnt"] = tnt
    else:
        doc.pop("tnt", None)
    return doc


def _persist_query(slice_start: int, slice_end: int) -> str:
    """LOOKUP JOIN one minute of ALB onto lookup-waf-trace. Slices dodge the 10k ES|QL cap."""
    template = (ROOT / "persist.esql").read_text()
    old = "| WHERE @timestamp > NOW() - 10 minutes AND trace.id IS NOT NULL"
    new = (
        f"| WHERE @timestamp > NOW() - {slice_end} minutes "
        f"AND @timestamp <= NOW() - {slice_start} minutes AND trace.id IS NOT NULL"
    )
    if old not in template:
        raise SystemExit("persist.esql WHERE clause changed; update _persist_query")
    return template.replace(old, new, 1)


def persist():
    """Run LOOKUP JOIN for PERSIST_MINUTES and create docs in logs-ingress-default."""
    if SKIP_PERSIST:
        print("skip persist")
        return
    ensure_lookup_index()
    ensure_ingress_stream()
    created = conflicts = errors = rows_total = 0
    error_samples = []
    for slice_start in range(PERSIST_MINUTES):
        query = _persist_query(slice_start, slice_start + 1)
        st, body = req(ES + "/_query", "POST", {"query": query}, timeout=180)
        if st >= 400:
            print("persist query failed", slice_start, st, json.dumps(body)[:2000])
            raise SystemExit("persist ES|QL failed")
        cols = [c["name"] for c in body.get("columns") or []]
        rows = body.get("values") or []
        rows_total += len(rows)
        print("persist slice", f"{slice_start + 1}m", "rows", len(rows))
        batch = []
        for row in rows:
            rec = dict(zip(cols, row))
            tid = rec.get("trace.id")
            if not tid:
                continue
            batch.append({"create": {"_index": INGRESS_STREAM, "_id": tid}})
            batch.append(row_to_ingress_doc(rec))
            if len(batch) >= 1000:
                c, k, e, samples = _bulk(batch)
                created += c
                conflicts += k
                errors += e
                error_samples.extend(samples)
                batch = []
        if batch:
            c, k, e, samples = _bulk(batch)
            created += c
            conflicts += k
            errors += e
            error_samples.extend(samples)
    print(
        "persist bulk",
        "rows",
        rows_total,
        "created",
        created,
        "conflicts",
        conflicts,
        "errors",
        errors,
    )
    for sample in error_samples[:5]:
        print("persist error sample", sample)
    if errors:
        raise SystemExit("persist bulk had non-conflict errors")


def _bulk(operations):
    payload = "\n".join(json.dumps(op, default=str) for op in operations) + "\n"
    st, body = req(
        ES + "/_bulk?filter_path=items.create.status,items.create.error,errors",
        "POST",
        payload.encode(),
        timeout=180,
        content_type="application/x-ndjson",
    )
    if st >= 400:
        return 0, 0, 1, [json.dumps(body)[:500]]
    created = conflicts = errors = 0
    samples = []
    for item in body.get("items") or []:
        res = item.get("create") or {}
        status = res.get("status")
        if status in (200, 201):
            created += 1
        elif status == 409:
            conflicts += 1
        else:
            errors += 1
            if len(samples) < 5:
                samples.append({"status": status, "error": res.get("error")})
    return created, conflicts, errors, samples


def upsert_workflow():
    yaml_text = (
        ROOT / "kibana" / "workflows" / f"{WORKFLOW_ID}.yaml"
    ).read_text()
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
        "valid" if isinstance(body, dict) and body.get("valid") else (
            body.get("message") if isinstance(body, dict) else body
        ),
        "enabled" if isinstance(body, dict) and body.get("enabled") else "",
    )
    if isinstance(body, dict) and body.get("valid") is False:
        err = ROOT / f"{WORKFLOW_ID}-invalid.json"
        err.write_text(json.dumps(body, indent=2)[:8000])
        print("workflow invalid ->", err)
        raise SystemExit("persist workflow invalid")
    return body


def disable_legacy_etl_workflow():
    st, body = req(
        KB + f"/s/{SPACE}/api/workflows/workflow/{LEGACY_WORKFLOW_ID}",
        kibana=True,
    )
    if st == 404:
        print("legacy workflow absent", LEGACY_WORKFLOW_ID)
        return
    yaml_text = body.get("yaml") or ""
    if "enabled: true" not in yaml_text and body.get("enabled") is not True:
        print("legacy workflow already disabled", LEGACY_WORKFLOW_ID)
        return
    patched = yaml_text.replace("enabled: true", "enabled: false", 1)
    if patched == yaml_text:
        patched = "enabled: false\n" + yaml_text
    st, body = req(
        KB + f"/s/{SPACE}/api/workflows/workflow/{LEGACY_WORKFLOW_ID}",
        "PUT",
        {"yaml": patched},
        kibana=True,
    )
    print(
        "legacy workflow disable",
        LEGACY_WORKFLOW_ID,
        st,
        "enabled",
        body.get("enabled") if isinstance(body, dict) else body,
    )


def ensure_ingress_trace_id_url(dv_id: str):
    if not dv_id:
        return
    fmt = {
        "id": "url",
        "params": {
            "type": "a",
            "urlTemplate": f"{KB}/s/{SPACE}/app/apm/link-to/trace/{{{{value}}}}",
            "labelTemplate": "{{value}}",
            "openLinkInCurrentTab": True,
        },
    }
    st, body = req(KB + f"/s/{SPACE}/api/data_views/data_view/{dv_id}", kibana=True)
    dv = body.get("data_view") if st == 200 and isinstance(body, dict) else {}
    formats = dict(dv.get("fieldFormats") or {})
    formats["trace.id"] = fmt
    formats["trace_id"] = fmt
    st, body = req(
        KB + f"/s/{SPACE}/api/data_views/data_view/{dv_id}",
        "POST",
        {"data_view": {"fieldFormats": formats}},
        kibana=True,
    )
    live = ((body.get("data_view") or {}).get("fieldFormats") or {}).get("trace.id") or {}
    print("trace url", dv.get("name") or dv_id, st, (live.get("params") or {}).get("urlTemplate"))


def ensure_data_view():
    title = f"{INGRESS_STREAM}*"
    name = "Ingress (ALB × WAF)"
    st, existing = req(KB + f"/s/{SPACE}/api/data_views", kibana=True)
    views = []
    if st == 200:
        views = existing.get("data_view") or existing.get("data_views") or []
    for dv in views:
        if dv.get("title") == title:
            print("data_view exists", title, dv.get("id"))
            ensure_ingress_trace_id_url(dv.get("id"))
            return dv.get("id")
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
    print("data_view create", title, st, dv_id or (body.get("message") if isinstance(body, dict) else body))
    if dv_id:
        ensure_ingress_trace_id_url(dv_id)
    return dv_id


def verify_persist():
    st, body = req(
        ES + f"/{INGRESS_STREAM}/_count",
        "POST",
        {"query": {"range": {"@timestamp": {"gte": "now-15m"}}}},
    )
    print("verify", INGRESS_STREAM, "15m", st, body.get("count") if st == 200 else body.get("error", {}).get("type"))


def apply_join_stack():
    put_pipeline(SLIM_PIPE, "lookup-waf-trace-slim.json")
    put_pipeline(ALB_PIPE, "logs-aws.elb_logs@custom.json")
    put_pipeline(WAF_PIPE, "logs-aws.waf@custom.json")
    simulate_extract()
    ensure_lookup_index()
    ensure_transform()
    backfill()
    start_transform()
    refresh_lookup_from_waf()


def apply_persist_stack():
    persist()
    upsert_workflow()
    disable_legacy_etl_workflow()
    ensure_data_view()
    verify_persist()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    target = argv[0] if argv else "all"
    if target in ("persist",):
        persist()
        verify_persist()
    elif target in ("workflow",):
        upsert_workflow()
        disable_legacy_etl_workflow()
        ensure_data_view()
    elif target in ("all", ""):
        apply_join_stack()
        apply_persist_stack()
    else:
        raise SystemExit(f"unknown target {target!r}; use persist|workflow or no args")
    print("done")


if __name__ == "__main__":
    main()
