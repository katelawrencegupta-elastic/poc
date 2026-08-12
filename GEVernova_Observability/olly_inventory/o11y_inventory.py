#!/usr/bin/env python3
"""
Splunk Observability Cloud (SignalFx) inventory script.

Inventories dashboards, dashboard groups, detectors (alerts), muting rules,
teams, and synthetics tests from a Splunk Observability Cloud org using the
v2 REST API. Optionally inventories metric names (--include-metrics) and
per-metric MTS (metric time series) counts (--mts-counts).

Requires only the Python standard library (Python 3.8+).

Usage:
    export SFX_TOKEN="<your-org-access-token or session token>"
    export SFX_REALM="us1"          # e.g. us0, us1, eu0, ap0 ...
    python3 o11y_inventory.py [--output-dir o11y_inventory] [--include-charts]
                              [--include-metrics] [--mts-counts]

The API token needs read access (an Org token with API permissions, or a
user session token). Realm is visible in the Observability Cloud URL,
e.g. https://app.us1.signalfx.com -> realm us1.

Outputs (in --output-dir):
    raw/<object>.json      full API payloads
    <object>.csv           flattened summaries
    inventory_summary.txt  counts overview
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PAGE_LIMIT = 200  # max objects per API page


def api_get(realm, token, path, params=None):
    """Single GET against the SignalFx API. Returns parsed JSON."""
    url = f"https://api.{realm}.signalfx.com{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "X-SF-TOKEN": token,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        if e.code == 401:
            sys.exit(f"ERROR: 401 Unauthorized on {path}. Check SFX_TOKEN "
                     f"(must be an org access token with API access).")
        if e.code == 404:
            # Endpoint not enabled for this org (e.g. no entitlement); skip.
            print(f"  WARNING: {path} returned 404, skipping. ({body})")
            return None
        raise RuntimeError(f"HTTP {e.code} on {url}: {body}") from e


def fetch_all(realm, token, path, label):
    """Fetch every page of a paginated collection endpoint."""
    results = []
    offset = 0
    while True:
        page = api_get(realm, token, path,
                       {"limit": PAGE_LIMIT, "offset": offset})
        if page is None:
            return None  # endpoint unavailable
        batch = page.get("results", [])
        results.extend(batch)
        total = page.get("count", len(results))
        print(f"  {label}: fetched {len(results)}/{total}")
        if len(batch) < PAGE_LIMIT or len(results) >= total:
            return results
        offset += PAGE_LIMIT
        time.sleep(0.2)  # be gentle with rate limits


def ts(millis):
    """Epoch millis -> ISO date string."""
    if not millis:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(millis / 1000))


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_raw(outdir, name, data):
    path = os.path.join(outdir, "raw", f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def summarize_detector_rules(detector):
    """Compact 'severity:notify-count' summary of a detector's rules."""
    parts = []
    for rule in detector.get("rules", []):
        sev = rule.get("severity", "?")
        n = len(rule.get("notifications") or [])
        parts.append(f"{sev}({n} notif)")
    return "; ".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--realm", default=os.environ.get("SFX_REALM"),
                    help="Realm, e.g. us0/us1/eu0 (or set SFX_REALM)")
    ap.add_argument("--token", default=os.environ.get("SFX_TOKEN"),
                    help="API token (or set SFX_TOKEN)")
    ap.add_argument("--output-dir", default="o11y_inventory",
                    help="Directory for output files")
    ap.add_argument("--include-charts", action="store_true",
                    help="Also inventory standalone charts (can be slow on "
                         "large orgs)")
    ap.add_argument("--include-metrics", action="store_true",
                    help="Also inventory metric names/metadata")
    ap.add_argument("--mts-counts", action="store_true",
                    help="Fetch active MTS count per metric (implies "
                         "--include-metrics; one API call per metric, slow "
                         "on orgs with many metrics)")
    ap.add_argument("--max-metrics", type=int, default=10000,
                    help="Cap on number of metrics to inventory "
                         "(default 10000)")
    args = ap.parse_args()
    if args.mts_counts:
        args.include_metrics = True

    if not args.realm or not args.token:
        sys.exit("ERROR: provide --realm/--token or set SFX_REALM and SFX_TOKEN.")

    outdir = args.output_dir
    os.makedirs(os.path.join(outdir, "raw"), exist_ok=True)
    counts = {}

    # --- Teams (fetched first so we can resolve team IDs to names) ---
    print("Fetching teams...")
    teams = fetch_all(args.realm, args.token, "/v2/team", "teams") or []
    team_names = {t["id"]: t.get("name", "") for t in teams}
    if teams:
        write_raw(outdir, "teams", teams)
        write_csv(os.path.join(outdir, "teams.csv"), [{
            "id": t.get("id"),
            "name": t.get("name"),
            "description": t.get("description", ""),
            "members": len(t.get("members") or []),
        } for t in teams], ["id", "name", "description", "members"])
    counts["teams"] = len(teams)

    # --- Dashboard groups ---
    print("Fetching dashboard groups...")
    groups = fetch_all(args.realm, args.token, "/v2/dashboardgroup",
                       "dashboard groups") or []
    group_names = {g["id"]: g.get("name", "") for g in groups}
    if groups:
        write_raw(outdir, "dashboard_groups", groups)
        write_csv(os.path.join(outdir, "dashboard_groups.csv"), [{
            "id": g.get("id"),
            "name": g.get("name"),
            "description": g.get("description", ""),
            "dashboards": len(g.get("dashboards") or []),
            "teams": "; ".join(team_names.get(tid, tid)
                               for tid in (g.get("teams") or [])),
            "creator": g.get("creator", ""),
            "created": ts(g.get("created")),
            "last_updated": ts(g.get("lastUpdated")),
        } for g in groups], ["id", "name", "description", "dashboards",
                             "teams", "creator", "created", "last_updated"])
    counts["dashboard_groups"] = len(groups)

    # --- Dashboards ---
    print("Fetching dashboards...")
    dashboards = fetch_all(args.realm, args.token, "/v2/dashboard",
                           "dashboards") or []
    if dashboards:
        write_raw(outdir, "dashboards", dashboards)
        write_csv(os.path.join(outdir, "dashboards.csv"), [{
            "id": d.get("id"),
            "name": d.get("name"),
            "group_id": d.get("groupId", ""),
            "group_name": group_names.get(d.get("groupId"), ""),
            "description": d.get("description", ""),
            "charts": len(d.get("charts") or []),
            "creator": d.get("creator", ""),
            "created": ts(d.get("created")),
            "last_updated": ts(d.get("lastUpdated")),
        } for d in dashboards], ["id", "name", "group_id", "group_name",
                                 "description", "charts", "creator",
                                 "created", "last_updated"])
    counts["dashboards"] = len(dashboards)
    counts["charts_on_dashboards"] = sum(
        len(d.get("charts") or []) for d in dashboards)

    # --- Detectors (alerts) ---
    print("Fetching detectors (alerts)...")
    detectors = fetch_all(args.realm, args.token, "/v2/detector",
                          "detectors") or []
    if detectors:
        write_raw(outdir, "detectors", detectors)
        write_csv(os.path.join(outdir, "detectors.csv"), [{
            "id": d.get("id"),
            "name": d.get("name"),
            "description": d.get("description", ""),
            "status": d.get("status", ""),
            "detector_origin": d.get("detectorOrigin", ""),
            "rules": summarize_detector_rules(d),
            "teams": "; ".join(team_names.get(tid, tid)
                               for tid in (d.get("teams") or [])),
            "creator": d.get("creator", ""),
            "created": ts(d.get("created")),
            "last_updated": ts(d.get("lastUpdated")),
            "program_text": (d.get("programText") or "").replace("\n", " | "),
        } for d in detectors], ["id", "name", "description", "status",
                                "detector_origin", "rules", "teams",
                                "creator", "created", "last_updated",
                                "program_text"])
    counts["detectors"] = len(detectors)

    # --- Alert muting rules ---
    print("Fetching alert muting rules...")
    mutings = fetch_all(args.realm, args.token, "/v2/alertmuting",
                        "muting rules")
    if mutings:
        write_raw(outdir, "alert_muting_rules", mutings)
        write_csv(os.path.join(outdir, "alert_muting_rules.csv"), [{
            "id": m.get("id"),
            "description": m.get("description", ""),
            "start": ts(m.get("startTime")),
            "stop": ts(m.get("stopTime")),
            "filters": json.dumps(m.get("filters") or []),
            "creator": m.get("creator", ""),
        } for m in mutings], ["id", "description", "start", "stop",
                              "filters", "creator"])
    counts["alert_muting_rules"] = len(mutings or [])

    # --- Synthetics tests ---
    # Single (non-paginated) endpoint; returns all tests in a "tests" array.
    # Returns 404 if the org has no Synthetics entitlement.
    print("Fetching synthetics tests...")
    synth_resp = api_get(args.realm, args.token, "/v2/synthetics/tests")
    synthetics = (synth_resp or {}).get("tests", [])
    if synthetics:
        write_raw(outdir, "synthetics_tests", synthetics)
        write_csv(os.path.join(outdir, "synthetics_tests.csv"), [{
            "id": s.get("id"),
            "name": s.get("name"),
            "type": s.get("type", ""),
            "active": s.get("active", ""),
            "frequency_min": s.get("frequency", ""),
            "locations": "; ".join(s.get("locationIds") or []),
            "last_run_status": s.get("lastRunStatus", ""),
            "last_run_at": s.get("lastRunAt", ""),
            "created": s.get("createdAt", ""),
            "last_updated": s.get("updatedAt", ""),
        } for s in synthetics], ["id", "name", "type", "active",
                                 "frequency_min", "locations",
                                 "last_run_status", "last_run_at",
                                 "created", "last_updated"])
        print(f"  synthetics tests: fetched {len(synthetics)}")
    counts["synthetics_tests"] = len(synthetics)

    # --- Metric names / MTS usage (optional) ---
    if args.include_metrics:
        print("Fetching metric names...")
        metrics = []
        offset = 0
        total = None
        while True:
            page = api_get(args.realm, args.token, "/v2/metric",
                           {"query": "name:*", "limit": PAGE_LIMIT,
                            "offset": offset})
            if page is None:
                break
            batch = page.get("results", [])
            metrics.extend(batch)
            total = page.get("count", len(metrics))
            print(f"  metrics: fetched {len(metrics)}/{total}")
            if len(batch) < PAGE_LIMIT or len(metrics) >= total:
                break
            if len(metrics) >= args.max_metrics:
                print(f"  WARNING: hit --max-metrics cap ({args.max_metrics}); "
                      f"org reports {total} metrics total.")
                break
            offset += PAGE_LIMIT
            time.sleep(0.2)

        rows = [{
            "name": m.get("name"),
            "type": m.get("type", ""),
            "custom": (m.get("custom", "")
                       if "custom" in m else m.get("customCreated", "")),
            "description": m.get("description", ""),
            "created": ts(m.get("created")),
            "last_updated": ts(m.get("lastUpdated")),
            "mts_count": "",
        } for m in metrics]

        # Per-metric MTS count: one metadata search per metric, reading the
        # matching-series count. Slow but avoids SignalFlow complexity.
        total_mts = 0
        if args.mts_counts and rows:
            est_min = len(rows) * 0.15 / 60
            print(f"Fetching MTS counts for {len(rows)} metrics "
                  f"(~{est_min:.0f} min)...")
            for i, row in enumerate(rows, 1):
                mts = api_get(args.realm, args.token, "/v2/metrictimeseries",
                              {"query": f'sf_metric:"{row["name"]}"',
                               "limit": 1})
                n = (mts or {}).get("count", 0)
                row["mts_count"] = n
                total_mts += n
                if i % 100 == 0 or i == len(rows):
                    print(f"  MTS counts: {i}/{len(rows)}")
                time.sleep(0.1)
            rows.sort(key=lambda r: r["mts_count"] or 0, reverse=True)

        if metrics:
            write_raw(outdir, "metrics", metrics)
            write_csv(os.path.join(outdir, "metrics.csv"), rows,
                      ["name", "type", "custom", "description", "created",
                       "last_updated", "mts_count"])
        counts["metrics"] = len(metrics)
        if total is not None and total > len(metrics):
            counts["metrics_in_org_total"] = total
        if args.mts_counts:
            counts["active_mts_total"] = total_mts

    # --- Standalone charts (optional; large orgs may have thousands) ---
    if args.include_charts:
        print("Fetching charts...")
        charts = fetch_all(args.realm, args.token, "/v2/chart", "charts") or []
        if charts:
            write_raw(outdir, "charts", charts)
            write_csv(os.path.join(outdir, "charts.csv"), [{
                "id": c.get("id"),
                "name": c.get("name"),
                "type": (c.get("options") or {}).get("type", ""),
                "creator": c.get("creator", ""),
                "created": ts(c.get("created")),
                "last_updated": ts(c.get("lastUpdated")),
            } for c in charts], ["id", "name", "type", "creator",
                                 "created", "last_updated"])
        counts["charts_total"] = len(charts)

    # --- Summary ---
    lines = ["Splunk Observability Cloud inventory",
             f"Realm: {args.realm}",
             f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
             ""]
    lines += [f"{k:24s} {v}" for k, v in counts.items()]
    summary = "\n".join(lines)
    with open(os.path.join(outdir, "inventory_summary.txt"), "w",
              encoding="utf-8") as f:
        f.write(summary + "\n")
    print("\n" + summary)
    print(f"\nOutput written to: {os.path.abspath(outdir)}/")


if __name__ == "__main__":
    main()
