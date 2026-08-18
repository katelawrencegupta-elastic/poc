"""CLI for GEH synthetic telemetry factories."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .elastic import (
    DEFAULT_ELASTIC_URL,
    DEFAULT_HONEYCOMB_INDEX,
    DEFAULT_INDICATOR_INDEX,
    DEFAULT_INDICATOR_SOURCE_MONTH,
    DEFAULT_MANUAL_INDEX,
    DEFAULT_PARTS_INDEX,
    DEFAULT_REPAIR_INDEX,
    CT_HYBRID_SEARCH_APP,
    ElasticConfig,
    deploy_ct_hybrid_search_application,
    fetch_indicator_system_keys,
    index_honeycomb,
    index_honeycomb_samples,
    index_indicator_events,
    index_manuals,
    index_parts,
    index_repairs,
    ping,
    run_ct_hybrid_search,
)
from .kibana import (
    DEFAULT_KIBANA_URL,
    DETAIL_DASHBOARD_ID,
    OVERVIEW_DASHBOARD_ID,
    PCD_COLLIMATION_WORKFLOW_ID,
    CT_HYBRID_SEARCH_WORKFLOW_ID,
    SQL2ESQL_WORKFLOW_ID,
    SQL2DQL_WORKFLOW_ID,
    KibanaConfig,
    dashboard_url,
    deploy_ct_hybrid_search_workflow,
    deploy_geh_dashboards,
    deploy_pcd_collimation_rule_and_workflow,
    deploy_sql2dql_workflow,
    deploy_sql2esql_workflow,
    kibana_request,
)
from .envfile import load_dotenv
from .honeycomb import (
    HoneycombConfig,
    generate_honeycomb,
    generate_honeycomb_sample_set,
)
from .indicators import IndicatorConfig, events_to_dicts, generate_indicator_events
from .manuals import generate_manuals, summarize_manuals
from .parts import PartsConfig, generate_machine_parts, summarize_machine_parts
from .repairs import RepairConfig, generate_repair_history, summarize_repairs
from .semantic import (
    DEFAULT_SEMANTIC_INFERENCE_ID,
    default_semantic_plans,
    enable_semantic_processing,
    verify_semantic_search,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_ndjson(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _add_elastic_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--to-elastic",
        action="store_true",
        help=f"Bulk-index to Elasticsearch (default URL: {DEFAULT_ELASTIC_URL})",
    )
    parser.add_argument(
        "--elastic-url",
        default=None,
        help="Elasticsearch URL (or ELASTIC_URL)",
    )
    parser.add_argument("--api-key", default=None, help="API key (or ELASTIC_API_KEY)")
    parser.add_argument("--user", default=None, help="Basic auth user (or ELASTIC_USER)")
    parser.add_argument(
        "--password", default=None, help="Basic auth password (or ELASTIC_PASSWORD)"
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh index after bulk so docs are immediately searchable",
    )


def _elastic_config(args: argparse.Namespace) -> ElasticConfig:
    return ElasticConfig.from_env(
        url=args.elastic_url,
        api_key=args.api_key,
        username=args.user,
        password=args.password,
        verify_certs=False if args.insecure else None,
    )


def _report_bulk(label: str, result) -> None:
    print(
        f"{label}: indexed={result.indexed} errors={result.errors}",
        file=sys.stderr,
    )
    if result.errors:
        for item in result.items:
            action = next(iter(item.values()), {})
            err = action.get("error")
            if err:
                print(f"  bulk error: {err}", file=sys.stderr)


def _cmd_indicators(args: argparse.Namespace) -> int:
    start = None
    if args.start:
        start = datetime.fromisoformat(args.start)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    cfg = IndicatorConfig(
        sessions=args.sessions,
        exams_per_session=(args.min_exams, args.max_exams),
        collateral_per_exam=(args.min_collateral, args.max_collateral),
        error_rate=args.error_rate,
        profile=args.profile,
        sysids=args.sysid,
        site_ids=args.site,
        machine_types=args.machine_type,
        start=start,
        seed=args.seed,
        es_style=not args.domain,
        critical_bias=args.critical_bias,
    )
    events = generate_indicator_events(cfg)
    rows = events_to_dicts(events, es_style=True if args.to_elastic else not args.domain)

    if args.out:
        out = Path(args.out)
        if out.suffix.lower() == ".json":
            _write_json(out, rows)
        else:
            _write_ndjson(out, rows)
        print(f"wrote {len(rows)} events -> {out}", file=sys.stderr)

    if args.to_elastic:
        es = _elastic_config(args)
        result = index_indicator_events(
            es,
            rows,
            index=args.index,
            refresh=args.refresh,
        )
        _report_bulk(f"indicators -> {es.url}", result)
        return 1 if result.errors else 0

    if not args.out:
        for row in rows:
            print(json.dumps(row, separators=(",", ":")))
    return 0


def _cmd_honeycomb(args: argparse.Namespace) -> int:
    failed = None
    if args.failed_modules is not None:
        failed = [int(x) for x in args.failed_modules.split(",") if x.strip()]
    if args.sample_like:
        cfg = HoneycombConfig.sample_fail(
            seed=args.seed,
            session_id=args.session_id,
            collimation=args.collimation,
        )
        if args.status == "pass":
            cfg = HoneycombConfig.sample_pass(
                seed=args.seed,
                session_id=args.session_id,
                collimation=args.collimation,
            )
        if args.bad_modules is not None:
            cfg.bad_module_count = args.bad_modules
        if failed is not None:
            cfg.failed_modules = failed
    else:
        cfg = HoneycombConfig(
            status=args.status,
            collimation=args.collimation,
            bad_module_count=args.bad_modules,
            failed_modules=failed,
            seed=args.seed,
            session_id=args.session_id,
        )
    payload = generate_honeycomb(cfg)

    if args.out:
        out = Path(args.out)
        _write_json(out, payload)
        print(f"wrote honeycomb -> {out}", file=sys.stderr)

    if args.to_elastic:
        es = _elastic_config(args)
        result = index_honeycomb(
            es,
            payload,
            index=args.index,
            refresh=args.refresh,
        )
        _report_bulk(f"honeycomb -> {es.url}", result)
        return 1 if result.errors else 0

    if not args.out:
        print(json.dumps(payload, indent=2))
    return 0


def _cmd_honeycomb_samples(args: argparse.Namespace) -> int:
    samples = generate_honeycomb_sample_set(
        count=args.count,
        seed=args.seed,
        pass_ratio=args.pass_ratio,
        site_ids=args.site,
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for i, sample in enumerate(samples):
        status = sample.payload.get("status", "unknown")
        sysid = sample.meta.get("sysid", "unknown")
        name = f"honeycomb_{i:02d}_{sysid}_{status}.json"
        path = out_dir / name
        _write_json(path, {"payload": sample.payload, "meta": sample.meta})
        summary.append(
            {
                "file": name,
                "status": status,
                "sysid": sysid,
                "hospital": sample.meta.get("hospital"),
                "machine_type": sample.meta.get("machine_type"),
                "is_bad_count": next(
                    (
                        sample.payload[k]["map"]["is_bad_count"]
                        for k in sample.payload
                        if k not in ("specid", "status")
                    ),
                    None,
                ),
            }
        )
    _write_json(out_dir / "manifest.json", summary)
    print(f"wrote {len(samples)} honeycomb samples -> {out_dir}", file=sys.stderr)

    if args.to_elastic:
        es = _elastic_config(args)
        result = index_honeycomb_samples(
            es,
            samples,
            index=args.index,
            refresh=args.refresh,
        )
        _report_bulk(f"honeycomb samples -> {es.url}", result)
        return 1 if result.errors else 0
    return 0


def _cmd_fixtures(args: argparse.Namespace) -> int:
    root = Path(args.out_dir)
    root.mkdir(parents=True, exist_ok=True)

    micro = generate_indicator_events(
        IndicatorConfig(
            sessions=1,
            exams_per_session=(1, 1),
            collateral_per_exam=(2, 3),
            error_rate=1.0,
            sysids=["CTBAY52WSO"],
            seed=1,
            start=datetime(2026, 7, 9, 8, 0, 0, tzinfo=timezone.utc),
        )
    )
    micro_rows = events_to_dicts(micro, es_style=True)
    _write_ndjson(root / "micro_indicators.ndjson", micro_rows)
    micro_hc_fail = generate_honeycomb(
        HoneycombConfig(
            status="fail",
            bad_module_count=8,
            failed_modules=[13],
            seed=1,
        )
    )
    micro_hc_pass = generate_honeycomb(HoneycombConfig(status="pass", seed=1))
    _write_json(root / "micro_honeycomb_fail.json", micro_hc_fail)
    _write_json(root / "micro_honeycomb_pass.json", micro_hc_pass)

    session = generate_indicator_events(
        IndicatorConfig(
            sessions=6,
            exams_per_session=(2, 4),
            collateral_per_exam=(1, 5),
            error_rate=1.0,
            sysids=["CTBAY52WSO"],
            seed=2,
            start=datetime(2026, 7, 9, 6, 0, 0, tzinfo=timezone.utc),
        )
    )
    session_rows = events_to_dicts(session, es_style=True)
    _write_ndjson(root / "session_indicators.ndjson", session_rows)
    session_hc = generate_honeycomb(
        HoneycombConfig(status="fail", bad_module_count=40, seed=2)
    )
    _write_json(root / "session_honeycomb_fail.json", session_hc)

    load = generate_indicator_events(
        IndicatorConfig(
            sessions=args.load_sessions,
            exams_per_session=(1, 4),
            collateral_per_exam=(0, 6),
            error_rate=1.0,
            seed=3,
            start=datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
    )
    load_rows = events_to_dicts(load, es_style=True)
    _write_ndjson(root / "load_indicators.ndjson", load_rows)
    load_hc = generate_honeycomb(HoneycombConfig(status="fail", seed=3))
    _write_json(root / "load_honeycomb_fail.json", load_hc)

    print(
        f"wrote fixtures under {root} "
        f"(micro={len(micro)}, session={len(session)}, load={len(load)} indicator events)",
        file=sys.stderr,
    )

    if args.to_elastic:
        es = _elastic_config(args)
        tier = args.tier
        failed = False
        if tier in ("micro", "all"):
            result = index_indicator_events(
                es, micro_rows, index=args.indicator_index, refresh=args.refresh
            )
            _report_bulk("micro indicators", result)
            r1 = index_honeycomb(
                es, micro_hc_fail, index=args.honeycomb_index, refresh=args.refresh
            )
            _report_bulk("micro honeycomb fail", r1)
            r2 = index_honeycomb(
                es, micro_hc_pass, index=args.honeycomb_index, refresh=args.refresh
            )
            _report_bulk("micro honeycomb pass", r2)
            failed = failed or bool(result.errors or r1.errors or r2.errors)
        if tier in ("session", "all"):
            result = index_indicator_events(
                es, session_rows, index=args.indicator_index, refresh=args.refresh
            )
            _report_bulk("session indicators", result)
            rh = index_honeycomb(
                es, session_hc, index=args.honeycomb_index, refresh=args.refresh
            )
            _report_bulk("session honeycomb", rh)
            failed = failed or bool(result.errors or rh.errors)
        if tier in ("load", "all"):
            result = index_indicator_events(
                es, load_rows, index=args.indicator_index, refresh=args.refresh
            )
            _report_bulk("load indicators", result)
            rh = index_honeycomb(
                es, load_hc, index=args.honeycomb_index, refresh=args.refresh
            )
            _report_bulk("load honeycomb", rh)
            failed = failed or bool(result.errors or rh.errors)
        print(f"pushed tier={tier} -> {es.url}", file=sys.stderr)
        return 1 if failed else 0

    return 0


def _cmd_ping(args: argparse.Namespace) -> int:
    es = _elastic_config(args)
    info = ping(es)
    print(json.dumps(info, indent=2))
    return 0


def _cmd_repairs(args: argparse.Namespace) -> int:
    history_end = None
    if args.history_end:
        history_end = datetime.fromisoformat(args.history_end)
        if history_end.tzinfo is None:
            history_end = history_end.replace(tzinfo=timezone.utc)

    source_index = args.source_index or DEFAULT_INDICATOR_SOURCE_MONTH
    target_index = args.index or DEFAULT_REPAIR_INDEX

    if args.systems_from == "elastic" or args.to_elastic:
        es = _elastic_config(args)
        systems = fetch_indicator_system_keys(es, index=source_index)
        print(
            f"loaded {len(systems)} sysid/machine_type/sw_version keys "
            f"from {source_index}",
            file=sys.stderr,
        )
    else:
        print(
            "error: repairs requires --systems-from elastic "
            "(or --to-elastic, which implies fetching from Elastic)",
            file=sys.stderr,
        )
        return 2

    if not systems:
        print("error: no systems found in source index", file=sys.stderr)
        return 1

    cfg = RepairConfig(
        systems=systems,
        seed=args.seed,
        history_end=history_end,
        min_repairs=args.min_repairs,
        max_repairs=args.max_repairs,
        index=target_index,
        source_indicator_index=source_index,
    )
    docs = generate_repair_history(cfg)
    summary = summarize_repairs(docs)
    print(json.dumps(summary, indent=2), file=sys.stderr)

    if args.out:
        out = Path(args.out)
        if out.suffix.lower() == ".json":
            _write_json(out, docs)
        else:
            _write_ndjson(out, docs)
        print(f"wrote {len(docs)} repairs -> {out}", file=sys.stderr)

    if args.to_elastic:
        result = index_repairs(
            es,
            docs,
            index=target_index,
            refresh=args.refresh,
            ensure_index=not args.no_create_index,
        )
        _report_bulk(f"repairs -> {target_index}", result)
        return 1 if result.errors else 0

    if not args.out:
        for row in docs:
            print(json.dumps(row, separators=(",", ":")))
    return 0


def _cmd_manuals(args: argparse.Namespace) -> int:
    target_index = args.index or DEFAULT_MANUAL_INDEX
    systypes = args.systype or None
    docs = generate_manuals(systypes=systypes, index=target_index)
    summary = summarize_manuals(docs)
    print(json.dumps(summary, indent=2), file=sys.stderr)

    if args.out:
        out = Path(args.out)
        if out.suffix.lower() == ".json":
            _write_json(out, docs)
        else:
            _write_ndjson(out, docs)
        print(f"wrote {len(docs)} manuals -> {out}", file=sys.stderr)

    if args.to_elastic:
        es = _elastic_config(args)
        result = index_manuals(
            es,
            docs,
            index=target_index,
            refresh=args.refresh,
            ensure_index=not args.no_create_index,
        )
        _report_bulk(f"manuals -> {target_index}", result)
        return 1 if result.errors else 0

    if not args.out:
        for row in docs:
            print(json.dumps(row, separators=(",", ":")))
    return 0


def _cmd_parts(args: argparse.Namespace) -> int:
    source_index = args.source_index or DEFAULT_INDICATOR_SOURCE_MONTH
    target_index = args.index or DEFAULT_PARTS_INDEX

    if args.systems_from == "elastic" or args.to_elastic:
        es = _elastic_config(args)
        systems = fetch_indicator_system_keys(es, index=source_index)
        print(
            f"loaded {len(systems)} sysid/machine_type/sw_version keys "
            f"from {source_index}",
            file=sys.stderr,
        )
    else:
        print(
            "error: parts requires --systems-from elastic "
            "(or --to-elastic, which implies fetching from Elastic)",
            file=sys.stderr,
        )
        return 2

    if not systems:
        print("error: no systems found in source index", file=sys.stderr)
        return 1

    cfg = PartsConfig(
        systems=systems,
        index=target_index,
        source_indicator_index=source_index,
    )
    docs = generate_machine_parts(cfg)
    summary = summarize_machine_parts(docs)
    print(json.dumps(summary, indent=2), file=sys.stderr)

    if args.out:
        out = Path(args.out)
        if out.suffix.lower() == ".json":
            _write_json(out, docs)
        else:
            _write_ndjson(out, docs)
        print(f"wrote {len(docs)} machine parts docs -> {out}", file=sys.stderr)

    if args.to_elastic:
        result = index_parts(
            es,
            docs,
            index=target_index,
            refresh=args.refresh,
            ensure_index=not args.no_create_index,
        )
        _report_bulk(f"parts -> {target_index}", result)
        return 1 if result.errors else 0

    if not args.out:
        for row in docs:
            print(json.dumps(row, separators=(",", ":")))
    return 0


def _cmd_semantic(args: argparse.Namespace) -> int:
    """Add semantic_text mappings and backfill semantic_search on CT indexes."""
    if not args.to_elastic and not args.dry_run:
        print(
            "error: semantic requires --to-elastic (or --dry-run)",
            file=sys.stderr,
        )
        return 2

    es = _elastic_config(args)
    # Inference-backed updates need a generous timeout.
    es.timeout_s = max(es.timeout_s, float(args.timeout or 180.0))

    plans = default_semantic_plans()
    if args.only:
        wanted = set(args.only)
        plans = [p for p in plans if p.label in wanted]
        if not plans:
            print(
                f"error: no plans matched --only {args.only}; "
                f"known: manuals, manuals_lookup, repairs, parts",
                file=sys.stderr,
            )
            return 2

    inference_id = args.inference_id or DEFAULT_SEMANTIC_INFERENCE_ID
    print(
        json.dumps(
            {
                "inference_id": inference_id,
                "indexes": [p.index for p in plans],
                "chunk_size": args.chunk_size,
            },
            indent=2,
        ),
        file=sys.stderr,
    )

    if args.dry_run:
        print("dry-run: no cluster writes", file=sys.stderr)
        return 0

    reports = enable_semantic_processing(
        es,
        plans=plans,
        inference_id=inference_id,
        chunk_size=args.chunk_size,
        refresh=args.refresh,
    )
    print(json.dumps(reports, indent=2))

    if args.verify:
        checks = [
            ("manuals", "image banding after detector module replacement"),
            ("repairs", "laser alignment scout FOV misregistration"),
            ("parts", "cooling pump pressure sensor kit"),
        ]
        label_to_index = {p.label: p.index for p in plans}
        verify_out: dict[str, Any] = {}
        for label, query in checks:
            idx = label_to_index.get(label)
            if not idx:
                continue
            try:
                hits = verify_semantic_search(es, idx, query, size=3)
                verify_out[label] = {
                    "index": idx,
                    "query": query,
                    "hit_count": len(hits),
                    "top": hits,
                }
            except RuntimeError as exc:
                verify_out[label] = {"index": idx, "query": query, "error": str(exc)}
        print(json.dumps({"verify": verify_out}, indent=2), file=sys.stderr)

    err_total = sum(r.get("errors", 0) for r in reports if isinstance(r, dict))
    return 1 if err_total else 0


def _cmd_dashboards(args: argparse.Namespace) -> int:
    es = _elastic_config(args)
    kbn = KibanaConfig.from_env(
        url=args.kibana_url,
        api_key=args.api_key,
        username=args.user,
        password=args.password,
        verify_certs=False if args.insecure else None,
        elastic=es,
    )
    directory = Path(args.definitions_dir) if args.definitions_dir else None
    results = deploy_geh_dashboards(kbn, directory=directory)
    for dashboard_id, payload in results.items():
        title = payload.get("data", {}).get("title", dashboard_id)
        print(
            f"{dashboard_id}: {title}\n  {dashboard_url(kbn, dashboard_id)}",
            file=sys.stderr,
        )
    print(
        f"overview={OVERVIEW_DASHBOARD_ID} detail={DETAIL_DASHBOARD_ID}",
        file=sys.stderr,
    )
    return 0


def _cmd_alerts(args: argparse.Namespace) -> int:
    es = _elastic_config(args)
    kbn = KibanaConfig.from_env(
        url=args.kibana_url,
        api_key=args.api_key,
        username=args.user,
        password=args.password,
        verify_certs=False if args.insecure else None,
        elastic=es,
    )
    result = deploy_pcd_collimation_rule_and_workflow(
        kbn,
        workflow_directory=Path(args.workflow_dir) if args.workflow_dir else None,
        rule_directory=Path(args.rule_dir) if args.rule_dir else None,
    )
    rule = result["rule"]
    print(
        f"workflow={result['workflow_id']} enabled={result['workflow'].get('enabled')}\n"
        f"  {result['workflow_url']}\n"
        f"rule={rule.get('name')} id={result['rule_id']} enabled={rule.get('enabled')}\n"
        f"  {result['rule_url']}",
        file=sys.stderr,
    )
    print(json.dumps({
        "workflow_id": result["workflow_id"],
        "rule_id": result["rule_id"],
        "workflow_url": result["workflow_url"],
        "rule_url": result["rule_url"],
    }))
    return 0


def _cmd_hybrid_search_api(args: argparse.Namespace) -> int:
    es = _elastic_config(args)
    app = deploy_ct_hybrid_search_application(
        es,
        directory=Path(args.search_app_dir) if args.search_app_dir else None,
        name=args.name,
    )
    kbn = KibanaConfig.from_env(
        url=args.kibana_url,
        api_key=args.api_key,
        username=args.user,
        password=args.password,
        verify_certs=False if args.insecure else None,
        elastic=es,
    )
    wf = deploy_ct_hybrid_search_workflow(
        kbn,
        workflow_directory=Path(args.workflow_dir) if args.workflow_dir else None,
    )
    print(
        f"search_application={app['name']}\n"
        f"  POST {app['endpoint']}\n"
        f"workflow={wf['workflow_id']} enabled={wf['workflow'].get('enabled')} "
        f"valid={wf['workflow'].get('valid')}\n"
        f"  POST {wf['run_url']}",
        file=sys.stderr,
    )
    if args.query:
        hits = run_ct_hybrid_search(
            es,
            query=args.query,
            size=args.size,
            hospital=args.hospital or "",
            sysid=args.sysid or "",
            severity=args.severity or "",
            rank_window_size=args.rank_window_size,
            rank_constant=args.rank_constant,
            name=args.name,
        )
        print(json.dumps({
            "search_application": app["name"],
            "endpoint": app["endpoint"],
            "workflow_id": wf["workflow_id"],
            "run_url": wf["run_url"],
            "sample_hits": [
                {
                    "_id": h.get("_id"),
                    "_score": h.get("_score"),
                    **(h.get("_source") or {}),
                }
                for h in ((hits.get("hits") or {}).get("hits") or [])
            ],
        }, indent=2))
    else:
        print(json.dumps({
            "search_application": app["name"],
            "endpoint": app["endpoint"],
            "workflow_id": wf["workflow_id"],
            "run_url": wf["run_url"],
            "workflow_valid": wf["workflow"].get("valid"),
        }))
    return 0


def _cmd_sql2esql(args: argparse.Namespace) -> int:
    es = _elastic_config(args)
    kbn = KibanaConfig.from_env(
        url=args.kibana_url,
        api_key=args.api_key,
        username=args.user,
        password=args.password,
        verify_certs=False if args.insecure else None,
        elastic=es,
    )
    wf = deploy_sql2esql_workflow(
        kbn,
        workflow_directory=Path(args.workflow_dir) if args.workflow_dir else None,
    )
    print(
        f"workflow={wf['workflow_id']} enabled={wf['workflow'].get('enabled')} "
        f"valid={wf['workflow'].get('valid')}\n"
        f"  POST {wf['run_url']}",
        file=sys.stderr,
    )
    payload = {
        "workflow_id": wf["workflow_id"],
        "run_url": wf["run_url"],
        "workflow_valid": wf["workflow"].get("valid"),
    }
    if args.sql:
        run = kibana_request(
            kbn,
            "POST",
            f"/api/workflows/workflow/{SQL2ESQL_WORKFLOW_ID}/run",
            {
                "inputs": {
                    "sql": args.sql,
                    "fetch_size": args.fetch_size,
                    "execute_esql": bool(args.execute_esql),
                }
            },
        )
        payload["workflowExecutionId"] = run.get("workflowExecutionId") or run.get("id")
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_sql2dql(args: argparse.Namespace) -> int:
    es = _elastic_config(args)
    kbn = KibanaConfig.from_env(
        url=args.kibana_url,
        api_key=args.api_key,
        username=args.user,
        password=args.password,
        verify_certs=False if args.insecure else None,
        elastic=es,
    )
    wf = deploy_sql2dql_workflow(
        kbn,
        workflow_directory=Path(args.workflow_dir) if args.workflow_dir else None,
    )
    print(
        f"workflow={wf['workflow_id']} enabled={wf['workflow'].get('enabled')} "
        f"valid={wf['workflow'].get('valid')}\n"
        f"  POST {wf['run_url']}",
        file=sys.stderr,
    )
    payload = {
        "workflow_id": wf["workflow_id"],
        "run_url": wf["run_url"],
        "workflow_valid": wf["workflow"].get("valid"),
    }
    if args.sql:
        run = kibana_request(
            kbn,
            "POST",
            f"/api/workflows/workflow/{SQL2DQL_WORKFLOW_ID}/run",
            {
                "inputs": {
                    "sql": args.sql,
                    "fetch_size": args.fetch_size,
                }
            },
        )
        payload["workflowExecutionId"] = run.get("workflowExecutionId") or run.get("id")
    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="geh_synthetic",
        description="Generate synthetic CT indicator events and detector LPP maps.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    ind = sub.add_parser("indicators", help="Generate session-aware indicator events")
    ind.add_argument("--sessions", type=int, default=1)
    ind.add_argument("--min-exams", type=int, default=1)
    ind.add_argument("--max-exams", type=int, default=3)
    ind.add_argument("--min-collateral", type=int, default=0)
    ind.add_argument("--max-collateral", type=int, default=4)
    ind.add_argument("--error-rate", type=float, default=1.0)
    ind.add_argument(
        "--critical-bias",
        type=float,
        default=1.0,
        help="Boost reli_error_code volume and Critical severity (e.g. 4.0)",
    )
    ind.add_argument(
        "--profile",
        choices=["lab", "fleet"],
        default="lab",
        help="lab = GEHQ sample only (default); fleet = 6 synthetic hospitals",
    )
    ind.add_argument("--sysid", action="append", default=None)
    ind.add_argument(
        "--site",
        action="append",
        default=None,
        help=(
            "Fleet site_id filter (repeatable): gehq, mayo_rst, massgen, cedars, "
            "uhn_tor, charite, cleveland, hopkins, karolinska, sinai_ny, stanford, "
            "gehq_west, ucla, northwestern, duke, toronto_sickkids, ap_hp, gehq_east"
        ),
    )
    ind.add_argument(
        "--machine-type",
        action="append",
        default=None,
        choices=["Internal", "Clinical", "Demo"],
        help="Fleet machine_type filter (repeatable)",
    )
    ind.add_argument("--start", type=str, default=None, help="ISO start timestamp")
    ind.add_argument("--seed", type=int, default=42)
    ind.add_argument(
        "--domain",
        action="store_true",
        help="Emit domain field names instead of ES-style keys",
    )
    ind.add_argument("--out", type=str, default=None, help="Output .ndjson or .json")
    ind.add_argument(
        "--index",
        default=None,
        help=f"Override index (default: doc _index or {DEFAULT_INDICATOR_INDEX})",
    )
    _add_elastic_args(ind)
    ind.set_defaults(func=_cmd_indicators)

    hc = sub.add_parser("honeycomb", help="Generate detector LPP / honeycomb map")
    hc.add_argument("--status", choices=["pass", "fail"], default="fail")
    hc.add_argument("--collimation", default="80")
    hc.add_argument("--bad-modules", type=int, default=None)
    hc.add_argument(
        "--failed-modules",
        type=str,
        default=None,
        help="Comma-separated module ids (e.g. 13,44)",
    )
    hc.add_argument(
        "--sample-like",
        action="store_true",
        help=(
            "Use golden-sample presets (184 bad modules, failed=[13], "
            "empirical pixels/module distribution)"
        ),
    )
    hc.add_argument("--session-id", type=str, default=None)
    hc.add_argument("--seed", type=int, default=42)
    hc.add_argument("--out", type=str, default=None)
    hc.add_argument(
        "--index",
        default=None,
        help=f"Target index (default: {DEFAULT_HONEYCOMB_INDEX})",
    )
    _add_elastic_args(hc)
    hc.set_defaults(func=_cmd_honeycomb)

    hcs = sub.add_parser(
        "honeycomb-samples",
        help="Generate a mixed pass/fail honeycomb sample set (optionally push to Elastic)",
    )
    hcs.add_argument("--count", type=int, default=12)
    hcs.add_argument("--seed", type=int, default=42)
    hcs.add_argument(
        "--pass-ratio",
        type=float,
        default=0.25,
        help="Fraction of PASS maps in the sample set",
    )
    hcs.add_argument(
        "--site",
        action="append",
        default=None,
        help="Optional fleet site_id filter (repeatable)",
    )
    hcs.add_argument(
        "--out-dir",
        type=str,
        default="fixtures/honeycomb_samples",
        help="Directory for sample JSON + manifest",
    )
    hcs.add_argument(
        "--index",
        default=None,
        help=f"Target index (default: {DEFAULT_HONEYCOMB_INDEX})",
    )
    _add_elastic_args(hcs)
    hcs.set_defaults(func=_cmd_honeycomb_samples)

    fix = sub.add_parser("fixtures", help="Write micro/session/load fixture set")
    fix.add_argument("--out-dir", type=str, default="fixtures")
    fix.add_argument("--load-sessions", type=int, default=80)
    fix.add_argument(
        "--tier",
        choices=["micro", "session", "load", "all"],
        default="all",
        help="Which fixture tiers to push when using --to-elastic",
    )
    fix.add_argument(
        "--indicator-index",
        default=None,
        help="Force indicator index for push (else use each doc _index)",
    )
    fix.add_argument(
        "--honeycomb-index",
        default=None,
        help=f"Honeycomb index (default: {DEFAULT_HONEYCOMB_INDEX})",
    )
    _add_elastic_args(fix)
    fix.set_defaults(func=_cmd_fixtures)

    ping_p = sub.add_parser("ping", help="Check Elasticsearch connectivity")
    _add_elastic_args(ping_p)
    ping_p.set_defaults(func=_cmd_ping, to_elastic=True)

    rep = sub.add_parser(
        "repairs",
        help=(
            "Generate synthetic historical repair records for each "
            "sysid/machine_type/sw_version in an indicator index"
        ),
    )
    rep.add_argument(
        "--systems-from",
        choices=["elastic"],
        default="elastic",
        help="Load distinct system keys from Elasticsearch indicator index",
    )
    rep.add_argument(
        "--source-index",
        default=None,
        help=(
            "Indicator index to read system keys from "
            f"(default: {DEFAULT_INDICATOR_SOURCE_MONTH})"
        ),
    )
    rep.add_argument(
        "--index",
        default=None,
        help=f"Target repair index (default: {DEFAULT_REPAIR_INDEX})",
    )
    rep.add_argument("--seed", type=int, default=42)
    rep.add_argument("--min-repairs", type=int, default=2)
    rep.add_argument("--max-repairs", type=int, default=14)
    rep.add_argument(
        "--history-end",
        type=str,
        default=None,
        help="ISO end of history window (default: 2026-07-01)",
    )
    rep.add_argument("--out", type=str, default=None, help="Output .ndjson or .json")
    rep.add_argument(
        "--no-create-index",
        action="store_true",
        help="Do not auto-create the repair index mapping",
    )
    _add_elastic_args(rep)
    rep.set_defaults(func=_cmd_repairs)

    man = sub.add_parser(
        "manuals",
        help=(
            "Generate short device manuals for Revolution CT and "
            "Revolution Apex and optionally index them in Elasticsearch"
        ),
    )
    man.add_argument(
        "--systype",
        action="append",
        default=None,
        help=(
            "Limit to one or more systypes (repeatable). "
            "Default: Revolution CT and Revolution Apex"
        ),
    )
    man.add_argument(
        "--index",
        default=None,
        help=f"Target manual index (default: {DEFAULT_MANUAL_INDEX})",
    )
    man.add_argument("--out", type=str, default=None, help="Output .ndjson or .json")
    man.add_argument(
        "--no-create-index",
        action="store_true",
        help="Do not auto-create the manual index mapping",
    )
    _add_elastic_args(man)
    man.set_defaults(func=_cmd_manuals)

    parts = sub.add_parser(
        "parts",
        help=(
            "Generate machine parts / BOM lists correlated with "
            "sysid, systype, and sw_version from an indicator index"
        ),
    )
    parts.add_argument(
        "--systems-from",
        choices=["elastic"],
        default="elastic",
        help="Load distinct system keys from Elasticsearch indicator index",
    )
    parts.add_argument(
        "--source-index",
        default=None,
        help=(
            "Indicator index to read system keys from "
            f"(default: {DEFAULT_INDICATOR_SOURCE_MONTH})"
        ),
    )
    parts.add_argument(
        "--index",
        default=None,
        help=f"Target parts index (default: {DEFAULT_PARTS_INDEX})",
    )
    parts.add_argument("--out", type=str, default=None, help="Output .ndjson or .json")
    parts.add_argument(
        "--no-create-index",
        action="store_true",
        help="Do not auto-create the parts index mapping",
    )
    _add_elastic_args(parts)
    parts.set_defaults(func=_cmd_parts)

    sem = sub.add_parser(
        "semantic",
        help=(
            "Enable semantic_text on manuals/repairs/parts "
            "(add mapping + backfill semantic_search)"
        ),
    )
    sem.add_argument(
        "--only",
        action="append",
        choices=["manuals", "manuals_lookup", "repairs", "parts"],
        default=None,
        help="Limit to one or more index groups (repeatable)",
    )
    sem.add_argument(
        "--inference-id",
        default=None,
        help=(
            "Inference endpoint for semantic_text "
            f"(default: {DEFAULT_SEMANTIC_INFERENCE_ID})"
        ),
    )
    sem.add_argument(
        "--chunk-size",
        type=int,
        default=10,
        help="Bulk update batch size (default: 10; keep small for inference)",
    )
    sem.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="HTTP timeout seconds for inference-backed writes (default: 180)",
    )
    sem.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned indexes and exit without writing",
    )
    sem.add_argument(
        "--verify",
        action="store_true",
        help="Run sample semantic queries after backfill",
    )
    _add_elastic_args(sem)
    sem.set_defaults(func=_cmd_semantic)

    dash = sub.add_parser(
        "dashboards",
        help=(
            "Upsert GEH Kibana dashboards (fleet overview + hospital detail "
            "with hospital drilldown)"
        ),
    )
    dash.add_argument(
        "--kibana-url",
        default=None,
        help=f"Kibana URL (or KIBANA_URL; default: {DEFAULT_KIBANA_URL})",
    )
    dash.add_argument(
        "--definitions-dir",
        default=None,
        help="Directory containing geh-*.json dashboard definitions",
    )
    _add_elastic_args(dash)
    dash.set_defaults(func=_cmd_dashboards, to_elastic=True)

    alerts = sub.add_parser(
        "alerts",
        help=(
            "Upsert PCD collimation FAIL + Critical-by-sysid alerting rule "
            f"and AI email workflow ({PCD_COLLIMATION_WORKFLOW_ID})"
        ),
    )
    alerts.add_argument(
        "--kibana-url",
        default=None,
        help=f"Kibana URL (or KIBANA_URL; default: {DEFAULT_KIBANA_URL})",
    )
    alerts.add_argument(
        "--workflow-dir",
        default=None,
        help="Directory containing workflow YAML definitions",
    )
    alerts.add_argument(
        "--rule-dir",
        default=None,
        help="Directory containing alerting rule JSON definitions",
    )
    _add_elastic_args(alerts)
    alerts.set_defaults(func=_cmd_alerts, to_elastic=True)

    hybrid = sub.add_parser(
        "hybrid-search-api",
        help=(
            "Upsert CT hybrid search REST endpoint "
            f"(Search Application + workflow `{CT_HYBRID_SEARCH_WORKFLOW_ID}`)"
        ),
    )
    hybrid.add_argument(
        "--name",
        default=CT_HYBRID_SEARCH_APP,
        help=f"Search application / workflow id (default: {CT_HYBRID_SEARCH_APP})",
    )
    hybrid.add_argument(
        "--kibana-url",
        default=None,
        help=f"Kibana URL (or KIBANA_URL; default: {DEFAULT_KIBANA_URL})",
    )
    hybrid.add_argument(
        "--search-app-dir",
        default=None,
        help="Directory containing search application JSON definitions",
    )
    hybrid.add_argument(
        "--workflow-dir",
        default=None,
        help="Directory containing workflow YAML definitions",
    )
    hybrid.add_argument("--query", default=None, help="Optional smoke-test query")
    hybrid.add_argument("--size", type=int, default=5, help="Smoke-test size")
    hybrid.add_argument("--hospital", default="", help="Smoke-test hospital filter")
    hybrid.add_argument("--sysid", default="", help="Smoke-test sysid filter")
    hybrid.add_argument("--severity", default="", help="Smoke-test severity filter")
    hybrid.add_argument("--rank-window-size", type=int, default=100)
    hybrid.add_argument("--rank-constant", type=int, default=60)
    _add_elastic_args(hybrid)
    hybrid.set_defaults(func=_cmd_hybrid_search_api, to_elastic=True)

    sql2 = sub.add_parser(
        "sql2esql",
        help=(
            "Upsert SQL→ES|QL workflow "
            f"(`{SQL2ESQL_WORKFLOW_ID}`; /_sql/translate + ES|QL derivation)"
        ),
    )
    sql2.add_argument(
        "--kibana-url",
        default=None,
        help=f"Kibana URL (or KIBANA_URL; default: {DEFAULT_KIBANA_URL})",
    )
    sql2.add_argument(
        "--workflow-dir",
        default=None,
        help="Directory containing workflow YAML definitions",
    )
    sql2.add_argument(
        "--sql",
        default=None,
        help="Optional SQL to run through the workflow after deploy",
    )
    sql2.add_argument("--fetch-size", type=int, default=10)
    sql2.add_argument(
        "--execute-esql",
        action="store_true",
        help="Ask the workflow to dry-run generated ES|QL",
    )
    _add_elastic_args(sql2)
    sql2.set_defaults(func=_cmd_sql2esql, to_elastic=True)

    sql2d = sub.add_parser(
        "sql2dql",
        help=(
            "Upsert SQL→Query DSL workflow "
            f"(`{SQL2DQL_WORKFLOW_ID}`; /_sql/translate only, no ES|QL)"
        ),
    )
    sql2d.add_argument(
        "--kibana-url",
        default=None,
        help=f"Kibana URL (or KIBANA_URL; default: {DEFAULT_KIBANA_URL})",
    )
    sql2d.add_argument(
        "--workflow-dir",
        default=None,
        help="Directory containing workflow YAML definitions",
    )
    sql2d.add_argument(
        "--sql",
        default=None,
        help="Optional SQL to run through the workflow after deploy",
    )
    sql2d.add_argument("--fetch-size", type=int, default=10)
    _add_elastic_args(sql2d)
    sql2d.set_defaults(func=_cmd_sql2dql, to_elastic=True)

    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
