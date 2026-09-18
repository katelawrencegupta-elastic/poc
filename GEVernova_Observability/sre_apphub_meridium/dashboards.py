"""ES|QL Lens builders for AppHub → Meridium / APM Classic latency."""
import importlib.util
from pathlib import Path

_FINOPS = Path(__file__).resolve().parent.parent / "finops_rightsizing" / "dashboards.py"
_spec = importlib.util.spec_from_file_location("finops_dashboards", _FINOPS)
_fd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fd)
_dash_refs = _fd._dash_refs
_panel = _fd._panel
_saved = _fd._saved
_text_panel = _fd._text_panel

ROOT = Path(__file__).resolve().parent
DASHBOARD_ID = "sre-apphub-meridium-latency"
METRICS_DV = "metrics-*"
TRACES_DV = "traces-*"
TS = "@timestamp >= ?_tstart AND @timestamp < ?_tend"
APPHUB = 'TO_LOWER(`resource.attributes.service.name`) LIKE "*apphub*"'
MERIDIUM_DEST = (
    'TO_LOWER(`attributes.span.destination.service.resource`) LIKE "*classic*"'
    "\n   OR TO_LOWER(`attributes.span.destination.service.resource`) LIKE \"*meridium*\""
)

INTRO = (
    "## AppHub → Meridium latency\n"
    "AppHub proxies HTTPS to APM Classic / Meridium hosts "
    "(`classic-stage`, `classic-dev`, `classic-beta`, `meridium-ui`). "
    "It does **not** call `meridium-webapi` by service name. "
    "Change the **time picker** — line charts and the heatmap re-bucket "
    "automatically (last 15m vs last 3d). Click a **legend** item to isolate a host.\n\n"
    "- **P2** avg ≥ **500 ms**\n"
    "- **P1** fail share ≥ **5%**\n"
    "- **P1** ≥3 client spans lasting **≥30 s**\n\n"
    "[Alerts](/s/sre/app/observability/alerts) · "
    "[Cases](/s/sre/app/observability/cases)"
)


def load_esql(name: str) -> str:
    return (ROOT / "esql" / name).read_text().strip()


def _col(column_id, field_name, col_type, label=None, metric=False):
    col = {
        "columnId": column_id,
        "fieldName": field_name,
        "meta": {"type": col_type},
    }
    if label:
        col["label"] = label
        col["customLabel"] = True
    if metric:
        col["inMetricDimension"] = True
    return col


def _layer(layer_id, query, columns, data_view_id):
    return {
        "index": data_view_id,
        "query": {"esql": query.strip() + "\n"},
        "columns": columns,
        "allColumns": columns,
        "timeField": "@timestamp",
    }


def _esql_lens(layer_id, query, columns, visualization_type, visualization, data_view_id):
    return {
        "title": "",
        "description": "",
        "visualizationType": visualization_type,
        "type": "lens",
        "references": [
            {
                "id": data_view_id,
                "name": f"indexpattern-datasource-layer-{layer_id}",
                "type": "index-pattern",
            }
        ],
        "state": {
            "adHocDataViews": {},
            "internalReferences": [],
            "filters": [],
            "query": {"language": "kuery", "query": ""},
            "datasourceStates": {
                "formBased": {"layers": {}},
                "textBased": {
                    "layers": {layer_id: _layer(layer_id, query, columns, data_view_id)}
                },
            },
            "visualization": visualization,
        },
    }


def lens_esql_metric(layer_id, col_id, query, field_name, label, data_view_id):
    columns = [_col(col_id, field_name, "number", label, metric=True)]
    return _esql_lens(
        layer_id,
        query,
        columns,
        "lnsMetric",
        {"layerId": layer_id, "layerType": "data", "metricAccessor": col_id},
        data_view_id,
    )


def lens_esql_table(layer_id, query, columns, data_view_id, page_size=10):
    return _esql_lens(
        layer_id,
        query,
        columns,
        "lnsDatatable",
        {
            "layerId": layer_id,
            "layerType": "data",
            "columns": [{"columnId": c["columnId"], "isTransposed": False} for c in columns],
            "paging": {"size": page_size, "enabled": True},
            "headerRowHeight": "single",
            "rowHeight": "single",
            "rowHeightLines": 1,
            "headerHeightLines": 1,
        },
        data_view_id,
    )


def lens_esql_xy(
    layer_id,
    query,
    date_id,
    date_field,
    metric_id,
    metric_field,
    metric_label,
    split_id,
    split_field,
    split_label,
    data_view_id,
    series="line",
):
    columns = [
        _col(date_id, date_field, "date", "Time"),
        _col(split_id, split_field, "string", split_label),
        _col(metric_id, metric_field, "number", metric_label, metric=True),
    ]
    return _esql_lens(
        layer_id,
        query,
        columns,
        "lnsXY",
        {
            "legend": {
                "isVisible": True,
                "position": "right",
                "legendSize": "medium",
                "shouldTruncate": True,
                "showSingleSeries": True,
            },
            "valueLabels": "hide",
            "fittingFunction": "None",
            "axisTitlesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
            "tickLabelsVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
            "labelsOrientation": {"x": 0, "yLeft": 0, "yRight": 0},
            "gridlinesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
            "preferredSeriesType": series,
            "layers": [
                {
                    "layerId": layer_id,
                    "seriesType": series,
                    "accessors": [metric_id],
                    "layerType": "data",
                    "xAccessor": date_id,
                    "splitAccessor": split_id,
                }
            ],
        },
        data_view_id,
    )


def _dest_from():
    return (
        "FROM metrics-service_destination.1m.otel-default\n"
        f"| WHERE {TS}\n"
        f"| WHERE {APPHUB}\n"
        f"| WHERE {MERIDIUM_DEST}\n"
    )


def _trace_from():
    return (
        "FROM traces-generic.otel-default\n"
        f"| WHERE {TS}\n"
        f"| WHERE {APPHUB}\n"
        f"| WHERE {MERIDIUM_DEST}\n"
    )


Q_CALLS = _dest_from() + "| STATS calls = SUM(`metrics.span.destination.service.response_time.count`)\n"
Q_AVG_MS = (
    _dest_from()
    + """| STATS calls = SUM(`metrics.span.destination.service.response_time.count`),
        sum_us = SUM(`metrics.span.destination.service.response_time.sum.us`)
| EVAL avg_ms = ROUND(sum_us / calls / 1000.0, 1)
| KEEP avg_ms
"""
)
Q_FAIL_PCT = (
    _dest_from()
    + """| STATS calls = SUM(`metrics.span.destination.service.response_time.count`),
        fail_calls = SUM(CASE(`attributes.event.outcome` == "failure", `metrics.span.destination.service.response_time.count`, 0))
| EVAL fail_pct = ROUND(100.0 * fail_calls / calls, 2)
| KEEP fail_pct
"""
)
Q_P95_MS = (
    _trace_from()
    + """| STATS p95_ms = ROUND(PERCENTILE(`attributes.span.duration.us`, 95) / 1000.0, 1)
"""
)
Q_TIMEOUTS = (
    _trace_from()
    + """| WHERE `attributes.span.duration.us` >= 30000000
| STATS timeouts = COUNT(*)
"""
)
Q_FAILS = (
    _dest_from()
    + """| STATS fail_calls = SUM(CASE(`attributes.event.outcome` == "failure", `metrics.span.destination.service.response_time.count`, 0))
"""
)
Q_AVG_XY = (
    _dest_from()
    + """| EVAL dest_short = CASE(
     `attributes.span.destination.service.resource` LIKE "*classic-stage*", "classic-stage",
     `attributes.span.destination.service.resource` LIKE "*classic-dev*", "classic-dev",
     `attributes.span.destination.service.resource` LIKE "*beta-stage*", "classic-beta",
     `attributes.span.destination.service.resource` LIKE "*meridium-ui*", "meridium-ui",
     `attributes.span.destination.service.resource`
   )
| STATS calls = SUM(`metrics.span.destination.service.response_time.count`),
        sum_us = SUM(`metrics.span.destination.service.response_time.sum.us`)
    BY t = BUCKET(@timestamp, 60, ?_tstart, ?_tend), dest_short
| EVAL avg_ms = ROUND(sum_us / calls / 1000.0, 1)
| KEEP t, dest_short, avg_ms
| SORT t ASC
| LIMIT 2000
"""
)
Q_FAIL_XY = (
    _dest_from()
    + """| EVAL dest_short = CASE(
     `attributes.span.destination.service.resource` LIKE "*classic-stage*", "classic-stage",
     `attributes.span.destination.service.resource` LIKE "*classic-dev*", "classic-dev",
     `attributes.span.destination.service.resource` LIKE "*beta-stage*", "classic-beta",
     `attributes.span.destination.service.resource` LIKE "*meridium-ui*", "meridium-ui",
     `attributes.span.destination.service.resource`
   )
| STATS calls = SUM(`metrics.span.destination.service.response_time.count`),
        fail_calls = SUM(CASE(`attributes.event.outcome` == "failure", `metrics.span.destination.service.response_time.count`, 0))
    BY t = BUCKET(@timestamp, 60, ?_tstart, ?_tend), dest_short
| EVAL fail_pct = ROUND(100.0 * fail_calls / calls, 2)
| KEEP t, dest_short, fail_pct
| SORT t ASC
| LIMIT 2000
"""
)
Q_DEST_TABLE = (
    _dest_from()
    + """| STATS calls = SUM(`metrics.span.destination.service.response_time.count`),
        sum_us = SUM(`metrics.span.destination.service.response_time.sum.us`),
        fail_calls = SUM(CASE(`attributes.event.outcome` == "failure", `metrics.span.destination.service.response_time.count`, 0))
    BY caller = `resource.attributes.service.name`,
       dest = `attributes.span.destination.service.resource`
| EVAL avg_ms = ROUND(sum_us / calls / 1000.0, 1),
       fail_pct = ROUND(100.0 * fail_calls / calls, 2)
| SORT calls DESC
| LIMIT 25
| KEEP caller, dest, calls, avg_ms, fail_calls, fail_pct
"""
)
Q_PATH_TABLE = (
    _trace_from()
    + """| STATS spans = COUNT(*),
        avg_ms = ROUND(AVG(`attributes.span.duration.us`) / 1000.0, 1),
        p95_ms = ROUND(PERCENTILE(`attributes.span.duration.us`, 95) / 1000.0, 1),
        fails = SUM(CASE(`attributes.event.outcome` == "failure", 1, 0))
    BY method = `attributes.http.method`,
       path = `attributes.http.target`,
       host = `attributes.http.host`
| EVAL fail_pct = ROUND(100.0 * fails / spans, 2)
| SORT spans DESC
| LIMIT 25
"""
)
Q_TIMEOUT_TABLE = (
    _trace_from()
    + """| WHERE `attributes.span.duration.us` >= 30000000
| STATS timeouts = COUNT(*),
        p95_ms = ROUND(PERCENTILE(`attributes.span.duration.us`, 95) / 1000.0, 1),
        max_ms = ROUND(MAX(`attributes.span.duration.us`) / 1000.0, 1)
    BY caller = `resource.attributes.service.name`,
       dest = `attributes.span.destination.service.resource`,
       path = `attributes.http.target`
| SORT timeouts DESC
| LIMIT 25
"""
)
Q_STATUS_TABLE = (
    _trace_from()
    + """| STATS spans = COUNT(*),
        avg_ms = ROUND(AVG(`attributes.span.duration.us`) / 1000.0, 1),
        p95_ms = ROUND(PERCENTILE(`attributes.span.duration.us`, 95) / 1000.0, 1)
    BY status = `attributes.http.status_code`,
       outcome = `attributes.event.outcome`
| SORT spans DESC
| LIMIT 20
"""
)

DEST_COLS = [
    _col("caller", "caller", "string", "Caller"),
    _col("dest", "dest", "string", "Destination"),
]


def build_latency_dashboard():
    panels = [
        _text_panel("am-md", "How to read AppHub → Meridium latency", INTRO, 0, 0, 48, 6),
        _panel(
            "am-kpi-calls",
            "Calls (destination metrics)",
            0, 6, 8, 6,
            lens_esql_metric("am-kpi-calls-l", "calls", Q_CALLS, "calls", "Calls", METRICS_DV),
        ),
        _panel(
            "am-kpi-avg",
            "Avg destination latency (ms)",
            8, 6, 8, 6,
            lens_esql_metric("am-kpi-avg-l", "avg_ms", Q_AVG_MS, "avg_ms", "Avg ms", METRICS_DV),
        ),
        _panel(
            "am-kpi-p95",
            "Trace p95 (ms)",
            16, 6, 8, 6,
            lens_esql_metric("am-kpi-p95-l", "p95_ms", Q_P95_MS, "p95_ms", "p95 ms", TRACES_DV),
        ),
        _panel(
            "am-kpi-failpct",
            "Failure rate (%)",
            24, 6, 8, 6,
            lens_esql_metric(
                "am-kpi-failpct-l", "fail_pct", Q_FAIL_PCT, "fail_pct", "Fail %", METRICS_DV
            ),
        ),
        _panel(
            "am-kpi-fails",
            "Failed calls",
            32, 6, 8, 6,
            lens_esql_metric(
                "am-kpi-fails-l", "fail_calls", Q_FAILS, "fail_calls", "Failures", METRICS_DV
            ),
        ),
        _panel(
            "am-kpi-to",
            "Timeout spans (≥30s)",
            40, 6, 8, 6,
            lens_esql_metric(
                "am-kpi-to-l", "timeouts", Q_TIMEOUTS, "timeouts", "Timeouts", TRACES_DV
            ),
        ),
        _panel(
            "am-xy-avg",
            "Avg destination latency by host (ms)",
            0, 12, 24, 12,
            lens_esql_xy(
                "am-xy-avg-l",
                Q_AVG_XY,
                "t",
                "t",
                "avg_ms",
                "avg_ms",
                "Avg ms",
                "dest_short",
                "dest_short",
                "Host",
                METRICS_DV,
                series="line",
            ),
        ),
        _panel(
            "am-xy-fail",
            "Failure rate by host (%)",
            24, 12, 24, 12,
            lens_esql_xy(
                "am-xy-fail-l",
                Q_FAIL_XY,
                "t",
                "t",
                "fail_pct",
                "fail_pct",
                "Fail %",
                "dest_short",
                "dest_short",
                "Host",
                METRICS_DV,
                series="line",
            ),
        ),
        _panel(
            "am-tbl-dest",
            "Latency by caller → destination (alert grain)",
            0, 24, 48, 12,
            lens_esql_table(
                "am-tbl-dest-l",
                Q_DEST_TABLE,
                DEST_COLS
                + [
                    _col("calls", "calls", "number", "Calls", metric=True),
                    _col("avg_ms", "avg_ms", "number", "Avg ms", metric=True),
                    _col("fail_calls", "fail_calls", "number", "Failures", metric=True),
                    _col("fail_pct", "fail_pct", "number", "Fail %", metric=True),
                ],
                METRICS_DV,
            ),
        ),
        _panel(
            "am-tbl-path",
            "Top HTTP paths (AppHub client spans)",
            0, 36, 48, 14,
            lens_esql_table(
                "am-tbl-path-l",
                Q_PATH_TABLE,
                [
                    _col("method", "method", "string", "Method"),
                    _col("path", "path", "string", "Path"),
                    _col("host", "host", "string", "Host"),
                    _col("spans", "spans", "number", "Spans", metric=True),
                    _col("avg_ms", "avg_ms", "number", "Avg ms", metric=True),
                    _col("p95_ms", "p95_ms", "number", "p95 ms", metric=True),
                    _col("fails", "fails", "number", "Fails", metric=True),
                    _col("fail_pct", "fail_pct", "number", "Fail %", metric=True),
                ],
                TRACES_DV,
                page_size=12,
            ),
        ),
        _panel(
            "am-tbl-to",
            "Timeouts ≥30s by path",
            0, 50, 28, 12,
            lens_esql_table(
                "am-tbl-to-l",
                Q_TIMEOUT_TABLE,
                [
                    _col("caller", "caller", "string", "Caller"),
                    _col("dest", "dest", "string", "Destination"),
                    _col("path", "path", "string", "Path"),
                    _col("timeouts", "timeouts", "number", "Timeouts", metric=True),
                    _col("p95_ms", "p95_ms", "number", "p95 ms", metric=True),
                    _col("max_ms", "max_ms", "number", "Max ms", metric=True),
                ],
                TRACES_DV,
            ),
        ),
        _panel(
            "am-tbl-status",
            "HTTP status on the hop",
            28, 50, 20, 12,
            lens_esql_table(
                "am-tbl-status-l",
                Q_STATUS_TABLE,
                [
                    _col("status", "status", "number", "Status"),
                    _col("outcome", "outcome", "string", "Outcome"),
                    _col("spans", "spans", "number", "Spans", metric=True),
                    _col("avg_ms", "avg_ms", "number", "Avg ms", metric=True),
                    _col("p95_ms", "p95_ms", "number", "p95 ms", metric=True),
                ],
                TRACES_DV,
            ),
        ),
    ]
    return _saved(
        "[SRE] AppHub → Meridium latency",
        "Client-side latency from AppHub to APM Classic / Meridium ingress. "
        "Vega charts auto-bucket with the time picker. Default last 3 days.",
        panels,
        _dash_refs(panels),
        time_from="now-3d",
    )


def verify_query_specs():
    window = "@timestamp >= NOW() - 3 days"

    def swap(q):
        return (
            q.replace(TS, window)
            .replace("?_tstart", "NOW() - 3 days")
            .replace("?_tend", "NOW()")
        )

    return [
        ("dash-calls", swap(Q_CALLS)),
        ("dash-avg", swap(Q_AVG_MS)),
        ("dash-failpct", swap(Q_FAIL_PCT)),
        ("dash-p95", swap(Q_P95_MS)),
        ("dash-timeouts", swap(Q_TIMEOUTS)),
        ("dash-dest-table", swap(Q_DEST_TABLE)),
        ("dash-path-table", swap(Q_PATH_TABLE)),
        ("dash-avg-xy", swap(Q_AVG_XY)),
        ("dash-fail-xy", swap(Q_FAIL_XY)),
    ]
