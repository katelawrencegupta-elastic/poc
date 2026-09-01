#!/usr/bin/env python3
"""Dry-run by default. Force-unenroll offline Fleet agents and delete unenrolled records.

Usage:
  python3 fleet_agents_remove.py                  # dry-run (default)
  python3 fleet_agents_remove.py --apply --offline --stale-only
  python3 fleet_agents_remove.py --apply --unenrolled
  python3 fleet_agents_remove.py --apply --offline --unenrolled

Requires ES_API_KEY, or reads api_key from config.yaml in this directory.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = "https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud"
IDS_PATH = HERE / "fleet_agents_removal_ids.json"
INV_PATH = HERE / "fleet_agents_removal.json"
STALE_HOURS = 24.0


def load_api_key() -> str:
    key = os.environ.get("ES_API_KEY")
    if key:
        return key.strip()
    cfg = HERE / "config.yaml"
    for line in cfg.read_text().splitlines():
        line = line.strip()
        if line.startswith("api_key:"):
            return line.split(":", 1)[1].strip().strip('"')
    raise SystemExit("Set ES_API_KEY or put api_key in config.yaml")


def request(method: str, path: str, body: dict | None = None, api_key: str = "") -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        KB + path,
        method=method,
        data=data,
        headers={
            "Authorization": f"ApiKey {api_key}",
            "kbn-xsrf": "true",
            "Content-Type": "application/json",
            "elastic-api-version": "2023-10-31",
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"message": raw.decode(errors="replace")[:500]}
        return exc.code, parsed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="Execute changes (default is dry-run)")
    p.add_argument("--offline", action="store_true", help="Force-unenroll offline agents")
    p.add_argument("--unenrolled", action="store_true", help="DELETE unenrolled agent records")
    p.add_argument(
        "--stale-only",
        action="store_true",
        help="Offline: only agents with last_checkin older than 24h",
    )
    p.add_argument("--batch-size", type=int, default=50)
    args = p.parse_args()
    if args.apply and not (args.offline or args.unenrolled):
        raise SystemExit("--apply requires --offline and/or --unenrolled")

    ids = json.loads(IDS_PATH.read_text())
    inv = json.loads(INV_PATH.read_text())
    keep = {a["id"] for a in inv.get("keep_agents", [])}
    offline = [a for a in inv["offline_agents"] if a["id"] not in keep]
    unenrolled = [a for a in inv["unenrolled_agents"] if a["id"] not in keep]

    if args.stale_only:
        offline = [a for a in offline if (a.get("offline_hours") or 0) >= STALE_HOURS]

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"mode={mode}")
    print(f"keep (excluded): {len(keep)}")
    print(f"offline selected: {len(offline)}")
    print(f"unenrolled selected: {len(unenrolled)}")
    for a in offline:
        print(
            f"  OFFLINE  {a['id']}  hours={a.get('offline_hours')}  "
            f"host={a.get('hostname')}  last={a.get('last_checkin')}"
        )

    if not args.apply:
        print("\nNo API writes. Re-run with --apply --offline and/or --unenrolled.")
        return 0

    api_key = load_api_key()

    if args.offline and offline:
        body = {
            "agents": [a["id"] for a in offline],
            "force": True,
            "revoke": True,
        }
        status, resp = request("POST", "/api/fleet/agents/bulk_unenroll", body, api_key)
        print(f"bulk_unenroll HTTP {status} {json.dumps(resp)[:800]}")
        if status >= 400:
            return 1

    if args.unenrolled:
        deleted = 0
        failed = 0
        for i, a in enumerate(unenrolled, 1):
            status, resp = request("DELETE", f"/api/fleet/agents/{urllib.parse.quote(a['id'])}", None, api_key)
            if 200 <= status < 300:
                deleted += 1
            else:
                failed += 1
                print(f"DELETE {a['id']} HTTP {status} {resp}")
            if i % args.batch_size == 0:
                print(f"  deleted {deleted}/{len(unenrolled)} failed={failed}")
                time.sleep(0.2)
        print(f"unenrolled delete done: deleted={deleted} failed={failed}")
        if failed:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
