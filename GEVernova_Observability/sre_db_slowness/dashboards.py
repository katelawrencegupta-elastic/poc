"""ES|QL Lens builders for the SRE DB-slowness walkthrough."""
import importlib.util
import json
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
DASHBOARD_ID = "sre-db-slowness-walkthrough"
METRICS_DV = "metrics-*"
TRACES_DV = "traces-*"
LOGS_DV = "logs-*"
TS = "@timestamp >= ?_tstart AND @timestamp < ?_tend"
PG = '`attributes.span.destination.service.resource` == "postgresql"'
SLOW = "`attributes.span.duration.us` >= 1000000"
RDS = 'COALESCE(`attributes.server.address`, `attributes.net.peer.name`)'
SEARCH_DEPLOY = (
    '`resource.attributes.k8s.deployment.name` == '
    '"apm-classic-meridium-service-search"'
)
WEBAPI_DEPLOY = (
    '`resource.attributes.k8s.deployment.name` == '
    '"apm-classic-meridium-webapi"'
)
NOT_DD = (
    'NOT `resource.attributes.k8s.container.name` == "datadog-agent-injected"'
)
CLASSIC_HOST = "apm-classic-stage.apm.stage.usw02.15.energy"
KB = "https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud"
EXAMPLE_TRACE = "9a51f6833eb9be520f647e3c8111877c"

INTRO = (
    "## Walk this board top to bottom\n"
    "This is the Elastic path from **DB slowness** to the **app**, the **SQL**, "
    "the **trace**, and the **logs**. Default time range is **last 3 days**.\n\n"
    "1. **KPIs** — postgresql client spans lasting **≥1 s**. "
    "If these are empty, the database is not the story.\n"
    "2. **Chart** — which RDS host is producing the slow spans.\n"
    "3. **Apps** — which services called that host.\n"
    "4. **SQL** — `db.query.text` grouped by `FROM` table "
    "(search service is the long tail).\n"
    "5. **Traces** — click `trace.id` to open the APM waterfall. "
    "Parent work is often an ActiveMQ `EntityDeleted` fan-out, not a user HTTP click.\n"
    "6. **Search logs** — same pods, **`EntityDeleted` only** (DEW fan-out), "
    "not Postgres errors. Click `trace.id`.\n"
    "7. **webapi errors** — user-facing API on the same traces "
    "(excludes `DuplicateTriggerTimeout` noise).\n"
    "8. **Ingress** — ALB to `apm-classic-stage` queryengine/search, same `trace.id`.\n"
    "9. **RDS CPU / queue** — `apm-classic-stage-rds`. Host CPU is not what "
    "explains 10–67 minute `SELECT … count(*) over ()` on `MI_EQUIP000`.\n\n"
    "**False lead:** `paf-postgres-dc-test` is a Spring Boot *connector* that "
    "restarted 15 Sep 04:52 UTC (CPU 335% of limit during boot). It is not "
    "the database, and PAF apps are barely traced to it.\n\n"
    f"[Example 67-minute span]({KB}/s/sre/app/apm/link-to/trace/{EXAMPLE_TRACE}) · "
    "[AppHub → Meridium (user hop)](/s/sre/app/dashboards#/view/sre-apphub-meridium-latency) · "
    "[Alerts](/s/sre/app/observability/alerts)"
)


TRACE_ID_URL_FORMAT = {
    "id": "url",
    "params": {
        "type": "a",
        "urlTemplate": f"{KB}/s/sre/app/apm/link-to/trace/{{{{value}}}}",
        "labelTemplate": "{{value}}",
        "openLinkInCurrentTab": True,
    },
}


def _col(column_id, field_name, col_type, label=None, metric=False, url=False):
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
    if url:
        col["params"] = {"format": TRACE_ID_URL_FORMAT}
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


def _pg_from():
    return (
        "FROM traces-generic.otel-default\n"
        f"| WHERE {TS}\n"
        f"| WHERE {PG}\n"
        f"| WHERE {SLOW}\n"
    )


Q_SLOW = _pg_from() + "| STATS slow_spans = COUNT(*)\n"
Q_MAX_S = _pg_from() + (
    "| STATS max_s = ROUND(MAX(`attributes.span.duration.us`) / 1000000.0, 1)\n"
)
Q_APPS_N = _pg_from() + (
    "| STATS apps = COUNT_DISTINCT(`resource.attributes.service.name`)\n"
)
Q_RDS_CPU = f"""FROM metrics-aws.rds-default
| WHERE {TS}
    AND `aws.dimensions.DBInstanceIdentifier` == "apm-classic-stage-rds"
| STATS cpu_pct = ROUND(MAX(`aws.rds.cpu.total.pct`) * 100.0, 1)
"""
Q_XY = f"""FROM traces-generic.otel-default
| WHERE {TS}
    AND {PG}
    AND {SLOW}
| EVAL rds_short = CASE(
     {RDS} LIKE "*classic-stage-rds*", "classic-stage-rds",
     {RDS} LIKE "*perf-db1*", "meridium-perf-db1",
     {RDS} LIKE "*alerts-postgres*", "alerts-postgres",
     {RDS} LIKE "*cases-postgres*", "cases-postgres",
     {RDS} LIKE "*iam-uaa-postgres*", "iam-uaa-postgres",
     {RDS}
   )
| STATS slow = COUNT(*)
    BY t = BUCKET(@timestamp, 60, ?_tstart, ?_tend), rds_short
| KEEP t, rds_short, slow
| SORT t ASC
| LIMIT 2000
"""
Q_APPS = _pg_from() + f"""| STATS slow = COUNT(*),
        p95_ms = ROUND(PERCENTILE(`attributes.span.duration.us`, 95) / 1000.0, 1),
        max_ms = ROUND(MAX(`attributes.span.duration.us`) / 1000.0, 1)
    BY app = `resource.attributes.service.name`,
       rds = {RDS}
| SORT slow DESC
| LIMIT 20
"""
Q_SQL = _pg_from() + """| WHERE `attributes.db.query.text` IS NOT NULL
| EVAL from_at = LOCATE(`attributes.db.query.text`, "FROM ")
| EVAL sql = SUBSTRING(`attributes.db.query.text`, from_at, 72)
| STATS slow = COUNT(*),
        p95_ms = ROUND(PERCENTILE(`attributes.span.duration.us`, 95) / 1000.0, 1),
        max_ms = ROUND(MAX(`attributes.span.duration.us`) / 1000.0, 1)
    BY app = `resource.attributes.service.name`, sql
| SORT max_ms DESC
| LIMIT 15
"""
Q_TRACES = f"""FROM traces-generic.otel-default
| WHERE {TS}
    AND {PG}
    AND `attributes.span.duration.us` >= 5000000
| EVAL dur_s = ROUND(`attributes.span.duration.us` / 1000000.0, 1),
       from_at = LOCATE(COALESCE(`attributes.db.query.text`, ""), "FROM "),
       sql = SUBSTRING(COALESCE(`attributes.db.query.text`, ""), from_at, 64),
       rds = {RDS}
| SORT `attributes.span.duration.us` DESC
| KEEP @timestamp, `resource.attributes.service.name`, rds, dur_s, `trace.id`, sql
| LIMIT 15
"""
Q_LOGS = f"""FROM logs-kubernetes.container_logs.otel-default
| WHERE {TS}
    AND {SEARCH_DEPLOY}
    AND {NOT_DD}
    AND `body.text` LIKE "*EntityDeleted*"
| EVAL msg = SUBSTRING(`body.text`, 1, 180)
| SORT @timestamp DESC
| KEEP @timestamp, `resource.attributes.k8s.pod.name`, `trace.id`, msg
| LIMIT 20
"""
Q_WEBAPI_LOGS = f"""FROM logs-kubernetes.container_logs.otel-default
| WHERE {TS}
    AND {WEBAPI_DEPLOY}
    AND {NOT_DD}
    AND TO_LOWER(`body.text`) RLIKE ".*(error|exception).*"
    AND NOT `body.text` LIKE "*DuplicateTriggerTimeout*"
| EVAL msg = SUBSTRING(`body.text`, 1, 180)
| SORT @timestamp DESC
| KEEP @timestamp, `trace.id`, msg
| LIMIT 15
"""
Q_INGRESS = f"""FROM logs-ingress-default
| WHERE {TS}
    AND url.domain == "{CLASSIC_HOST}"
    AND (
      url.path LIKE "/api/v1/core/queryengine*"
      OR url.path LIKE "/api/v1/search*"
      OR `http.response.status_code` >= 400
    )
| EVAL path = SUBSTRING(url.path, 1, 64)
| SORT @timestamp DESC
| KEEP @timestamp, `http.request.method`, path, `http.response.status_code`, `trace.id`
| LIMIT 20
"""
Q_RDS_ROW = f"""FROM metrics-aws.rds-default
| WHERE {TS}
    AND `aws.dimensions.DBInstanceIdentifier` == "apm-classic-stage-rds"
| STATS cpu_pct_max = ROUND(MAX(`aws.rds.cpu.total.pct`) * 100.0, 1),
        cpu_pct_avg = ROUND(AVG(`aws.rds.cpu.total.pct`) * 100.0, 2),
        max_queue = ROUND(MAX(`aws.rds.disk_queue_depth`), 2),
        max_read_s = ROUND(MAX(`aws.rds.latency.read`), 4),
        max_write_s = ROUND(MAX(`aws.rds.latency.write`), 4)
| KEEP cpu_pct_max, cpu_pct_avg, max_queue, max_read_s, max_write_s
"""

DISCOVER_SEARCH_ID = "gev-sre-db-slowness-esql"

# Discover tab label == dashboard panel title, numbered like the intro steps.
DISCOVER_TABS = [
    ("db-kpi-slow", "1. Slow postgresql spans (≥1s)", Q_SLOW),
    ("db-kpi-max", "1. Longest DB span (seconds)", Q_MAX_S),
    ("db-kpi-apps", "1. Apps with a slow DB span", Q_APPS_N),
    ("db-kpi-cpu", "1. classic-stage-rds CPU % max", Q_RDS_CPU),
    ("db-xy", "2. Slow postgresql spans (≥1s) by RDS host", Q_XY),
    ("db-tbl-apps", "3. Apps calling postgresql (slow spans)", Q_APPS),
    ("db-tbl-sql", "4. Slow SQL (FROM table excerpt from db.query.text)", Q_SQL),
    ("db-tbl-tr", "5. Longest traces (≥5s) — click trace.id", Q_TRACES),
    ("db-tbl-logs", "6. Search EntityDeleted logs (DEW fan-out) — click trace.id", Q_LOGS),
    ("db-tbl-webapi", "7. meridium-webapi errors — click trace.id", Q_WEBAPI_LOGS),
    ("db-tbl-ing", "8. classic-stage ingress (queryengine/search) — click trace.id", Q_INGRESS),
    (
        "db-tbl-rds",
        "9. apm-classic-stage-rds CloudWatch (CPU is 0–100 from cpu.total.pct)",
        Q_RDS_ROW,
    ),
]


def build_discover_search():
    """One Discover saved search with a named ES|QL tab per dashboard panel."""
    tabs = []
    for tab_id, label, query in DISCOVER_TABS:
        tabs.append(
            {
                "id": tab_id,
                "label": label,
                "attributes": {
                    "columns": [],
                    "sort": [],
                    "kibanaSavedObjectMeta": {
                        "searchSourceJSON": json.dumps(
                            {
                                "query": {"esql": query.strip()},
                                "filter": [],
                            }
                        )
                    },
                    "isTextBasedQuery": True,
                },
            }
        )
    return {
        "title": "[SRE] DB slowness walkthrough ES|QL",
        "description": (
            "Discover tabs for the DB slowness walkthrough dashboard. "
            "Each tab is named after the panel title and runs that panel's ES|QL. "
            "Time picker default last 3 days (?_tstart / ?_tend)."
        ),
        "tabs": tabs,
    }


def build_walkthrough_dashboard():
    panels = [
        _text_panel("db-md", "How to walk DB slowness", INTRO, 0, 0, 48, 12),
        _panel(
            "db-kpi-slow",
            "1. Slow postgresql spans (≥1s)",
            0, 12, 12, 6,
            lens_esql_metric(
                "db-kpi-slow-l", "slow_spans", Q_SLOW, "slow_spans", "Slow spans", TRACES_DV
            ),
        ),
        _panel(
            "db-kpi-max",
            "1. Longest DB span (seconds)",
            12, 12, 12, 6,
            lens_esql_metric("db-kpi-max-l", "max_s", Q_MAX_S, "max_s", "Max s", TRACES_DV),
        ),
        _panel(
            "db-kpi-apps",
            "1. Apps with a slow DB span",
            24, 12, 12, 6,
            lens_esql_metric("db-kpi-apps-l", "apps", Q_APPS_N, "apps", "Apps", TRACES_DV),
        ),
        _panel(
            "db-kpi-cpu",
            "1. classic-stage-rds CPU % max",
            36, 12, 12, 6,
            lens_esql_metric(
                "db-kpi-cpu-l", "cpu_pct", Q_RDS_CPU, "cpu_pct", "CPU %", METRICS_DV
            ),
        ),
        _panel(
            "db-xy",
            "2. Slow postgresql spans (≥1s) by RDS host",
            0, 18, 48, 12,
            lens_esql_xy(
                "db-xy-l",
                Q_XY,
                "t",
                "t",
                "slow",
                "slow",
                "Slow spans",
                "rds_short",
                "rds_short",
                "RDS",
                TRACES_DV,
                series="line",
            ),
        ),
        _panel(
            "db-tbl-apps",
            "3. Apps calling postgresql (slow spans)",
            0, 30, 48, 12,
            lens_esql_table(
                "db-tbl-apps-l",
                Q_APPS,
                [
                    _col("app", "app", "string", "App"),
                    _col("rds", "rds", "string", "RDS host"),
                    _col("slow", "slow", "number", "Slow ≥1s", metric=True),
                    _col("p95_ms", "p95_ms", "number", "p95 ms", metric=True),
                    _col("max_ms", "max_ms", "number", "Max ms", metric=True),
                ],
                TRACES_DV,
                page_size=12,
            ),
        ),
        _panel(
            "db-tbl-sql",
            "4. Slow SQL (FROM table excerpt from db.query.text)",
            0, 42, 48, 12,
            lens_esql_table(
                "db-tbl-sql-l",
                Q_SQL,
                [
                    _col("app", "app", "string", "App"),
                    _col("sql", "sql", "string", "SQL FROM…"),
                    _col("slow", "slow", "number", "Slow ≥1s", metric=True),
                    _col("p95_ms", "p95_ms", "number", "p95 ms", metric=True),
                    _col("max_ms", "max_ms", "number", "Max ms", metric=True),
                ],
                TRACES_DV,
                page_size=10,
            ),
        ),
        _panel(
            "db-tbl-tr",
            "5. Longest traces (≥5s) — click trace.id",
            0, 54, 48, 12,
            lens_esql_table(
                "db-tbl-tr-l",
                Q_TRACES,
                [
                    _col("@timestamp", "@timestamp", "date", "Time"),
                    _col(
                        "resource.attributes.service.name",
                        "resource.attributes.service.name",
                        "string",
                        "App",
                    ),
                    _col("rds", "rds", "string", "RDS host"),
                    _col("dur_s", "dur_s", "number", "Seconds", metric=True),
                    _col("trace.id", "trace.id", "string", "trace.id", url=True),
                    _col("sql", "sql", "string", "SQL FROM…"),
                ],
                TRACES_DV,
                page_size=10,
            ),
        ),
        _panel(
            "db-tbl-logs",
            "6. Search EntityDeleted logs (DEW fan-out) — click trace.id",
            0, 66, 48, 12,
            lens_esql_table(
                "db-tbl-logs-l",
                Q_LOGS,
                [
                    _col("@timestamp", "@timestamp", "date", "Time"),
                    _col(
                        "resource.attributes.k8s.pod.name",
                        "resource.attributes.k8s.pod.name",
                        "string",
                        "Pod",
                    ),
                    _col("trace.id", "trace.id", "string", "trace.id", url=True),
                    _col("msg", "msg", "string", "Log"),
                ],
                LOGS_DV,
                page_size=10,
            ),
        ),
        _panel(
            "db-tbl-webapi",
            "7. meridium-webapi errors — click trace.id",
            0, 78, 24, 12,
            lens_esql_table(
                "db-tbl-webapi-l",
                Q_WEBAPI_LOGS,
                [
                    _col("@timestamp", "@timestamp", "date", "Time"),
                    _col("trace.id", "trace.id", "string", "trace.id", url=True),
                    _col("msg", "msg", "string", "Log"),
                ],
                LOGS_DV,
                page_size=10,
            ),
        ),
        _panel(
            "db-tbl-ing",
            "8. classic-stage ingress (queryengine/search) — click trace.id",
            24, 78, 24, 12,
            lens_esql_table(
                "db-tbl-ing-l",
                Q_INGRESS,
                [
                    _col("@timestamp", "@timestamp", "date", "Time"),
                    _col("http.request.method", "http.request.method", "string", "Method"),
                    _col("path", "path", "string", "Path"),
                    _col(
                        "http.response.status_code",
                        "http.response.status_code",
                        "number",
                        "Status",
                        metric=True,
                    ),
                    _col("trace.id", "trace.id", "string", "trace.id", url=True),
                ],
                LOGS_DV,
                page_size=10,
            ),
        ),
        _panel(
            "db-tbl-rds",
            "9. apm-classic-stage-rds CloudWatch (CPU is 0–100 from cpu.total.pct)",
            0, 90, 48, 6,
            lens_esql_table(
                "db-tbl-rds-l",
                Q_RDS_ROW,
                [
                    _col("cpu_pct_max", "cpu_pct_max", "number", "CPU % max", metric=True),
                    _col("cpu_pct_avg", "cpu_pct_avg", "number", "CPU % avg", metric=True),
                    _col("max_queue", "max_queue", "number", "Disk queue max", metric=True),
                    _col("max_read_s", "max_read_s", "number", "Read lat s", metric=True),
                    _col("max_write_s", "max_write_s", "number", "Write lat s", metric=True),
                ],
                METRICS_DV,
                page_size=5,
            ),
        ),
    ]
    return _saved(
        "[SRE] DB slowness walkthrough",
        "Trace postgresql slowness through apps, SQL, APM traces, search EntityDeleted "
        "logs, webapi errors, and classic-stage ingress. Default last 3 days. "
        "Start at the KPIs, click a trace.id, then read the logs.",
        panels,
        _dash_refs(panels),
        time_from="now-3d",
    )


def verify_query_specs():
    window = "@timestamp >= NOW() - 3 days AND @timestamp < NOW()"

    def swap(q):
        return (
            q.replace(TS, window)
            .replace("?_tstart", "NOW() - 3 days")
            .replace("?_tend", "NOW()")
        )

    return [
        ("dash-slow", swap(Q_SLOW)),
        ("dash-max", swap(Q_MAX_S)),
        ("dash-apps-n", swap(Q_APPS_N)),
        ("dash-rds-cpu", swap(Q_RDS_CPU)),
        ("dash-xy", swap(Q_XY)),
        ("dash-apps", swap(Q_APPS)),
        ("dash-sql", swap(Q_SQL)),
        ("dash-traces", swap(Q_TRACES)),
        ("dash-logs", swap(Q_LOGS)),
        ("dash-webapi-logs", swap(Q_WEBAPI_LOGS)),
        ("dash-ingress", swap(Q_INGRESS)),
        ("dash-rds-row", swap(Q_RDS_ROW)),
    ]
