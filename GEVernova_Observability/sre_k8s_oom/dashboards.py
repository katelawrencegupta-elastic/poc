"""ES|QL Lens builders for the SRE K8s OOM / crash dashboard."""
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
DASHBOARD_ID = "sre-k8s-oom-crash"
LOGS_DV = "logs-*"
METRICS_DV = "metrics-*"
TS = "@timestamp >= ?_tstart AND @timestamp < ?_tend"
OOM_QSTR = (
    'QSTR("body.text:\\"Out of memory.\\" OR body.text:\\"Out of memory\\" '
    'OR body.text:\\"OutOfMemoryError\\" OR body.text:\\"java.lang.OutOfMemoryError\\" '
    'OR body.text:OOMKilled OR body.text:\\"OutOfMemoryException\\"")'
)
NOT_DATADOG = '`resource.attributes.k8s.container.name` != "datadog-agent-injected"'
HAS_DEPLOYMENT = "`resource.attributes.k8s.deployment.name` IS NOT NULL"

INTRO = (
    "## K8s OOM / crash\n"
    "Anomalous pod crashes should be rare. This view tracks **OOM phrases**, "
    "**multi-pod restart Δ**, and **memory-limit saturation** in the Kibana **sre** "
    "space. The time picker drives every panel (default last 3 days so sparse OOM "
    "logs still show).\n\n"
    "- **OOM phrase** — container logs matching `Out of memory` / `OutOfMemoryError` "
    "/ `OOMKilled`. P1; classic alert auto-starts the case workflow.\n"
    "- **Restart burst** — ≥2 pods in the same deployment each gained ≥1 restart. "
    "This is a **delta**, not a lifetime restart counter. P2; agent / v2 detect "
    "(classic companion does not auto-case).\n"
    "- **Memory limit ≥95%** — kubelet `memory_limit_utilization`. Pair with "
    "restarts for `oom.likely`. P2; auto-starts the workflow.\n"
    "- **OOMKilled status.reason** — needs OTel Wave 0; the field is not in the "
    "cluster yet, so it is omitted here. Phrase + restart + memory still work.\n\n"
    "Fargate often has null kubelet memory — then lean on OOM phrases and restart Δ. "
    "Do not change live memory limits from this view; HITL on the case records the "
    "decision.\n\n"
    "[OpenSearch Fleet](/s/sre/app/dashboards#/view/sre-opensearch-fleet) · "
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
    series="bar_stacked",
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


def _oom_from():
    return (
        "FROM logs-kubernetes.container_logs.otel-default\n"
        f"| WHERE {TS}\n"
        f"| WHERE {OOM_QSTR}\n"
    )


Q_OOM_HITS = _oom_from() + "| STATS oom_hits = COUNT(*)\n"
Q_OOM_DEPLOYMENTS = (
    _oom_from()
    + "| STATS deployments = COUNT_DISTINCT(`resource.attributes.k8s.deployment.name`)\n"
)
Q_OOM_PODS = (
    _oom_from() + "| STATS pods = COUNT_DISTINCT(`resource.attributes.k8s.pod.name`)\n"
)
Q_BURST_DEPLOYMENTS = (
    load_esql("restart-burst.esql") + "\n| STATS burst_deployments = COUNT(*)\n"
)
Q_MEM_SATURATING = (
    load_esql("mem-limit-saturate.esql") + "\n| STATS saturating = COUNT(*)\n"
)
Q_CRASHING_PODS = f"""
FROM metrics-k8sclusterreceiver.otel-default
| WHERE {TS}
| WHERE `metrics.k8s.container.restarts` IS NOT NULL
| WHERE {NOT_DATADOG}
| WHERE {HAS_DEPLOYMENT}
| STATS max_r = MAX(`metrics.k8s.container.restarts`),
        min_r = MIN(`metrics.k8s.container.restarts`)
    BY `resource.attributes.k8s.pod.name`
| EVAL delta = max_r - min_r
| WHERE delta >= 1
| STATS crashing_pods = COUNT_DISTINCT(`resource.attributes.k8s.pod.name`)
"""
Q_RESTART_XY = f"""
FROM metrics-k8sclusterreceiver.otel-default
| WHERE {TS}
| WHERE `metrics.k8s.container.restarts` IS NOT NULL
| WHERE {NOT_DATADOG}
| WHERE {HAS_DEPLOYMENT}
| EVAL t = DATE_TRUNC(30 minutes, @timestamp)
| STATS max_r = MAX(`metrics.k8s.container.restarts`),
        min_r = MIN(`metrics.k8s.container.restarts`)
    BY t, `resource.attributes.k8s.deployment.name`, `resource.attributes.k8s.pod.name`
| EVAL delta = max_r - min_r
| WHERE delta >= 1
| STATS crashing_pods = COUNT_DISTINCT(`resource.attributes.k8s.pod.name`),
        total_delta = SUM(delta)
    BY t, deployment = `resource.attributes.k8s.deployment.name`
| WHERE crashing_pods >= 2
| KEEP t, deployment, total_delta
| SORT t ASC
| LIMIT 3000
"""
Q_MEM_XY = f"""
FROM metrics-kubeletstatsreceiver.otel-default
| WHERE {TS}
| WHERE `metrics.k8s.container.memory_limit_utilization` >= 0.95
| WHERE {NOT_DATADOG}
| WHERE {HAS_DEPLOYMENT}
| EVAL t = DATE_TRUNC(30 minutes, @timestamp)
| STATS max_util = MAX(`metrics.k8s.container.memory_limit_utilization`)
    BY t, deployment = `resource.attributes.k8s.deployment.name`
| KEEP t, deployment, max_util
| SORT t ASC
| LIMIT 3000
"""
Q_OOM_XY = (
    _oom_from()
    + """| EVAL t = DATE_TRUNC(15 minutes, @timestamp)
| STATS hits = COUNT(*) BY t, deployment = `resource.attributes.k8s.deployment.name`
| KEEP t, deployment, hits
| SORT t ASC
| LIMIT 500
"""
)
Q_OOM_LOGS = (
    _oom_from()
    + """| RENAME body.text AS message,
         `resource.attributes.k8s.cluster.name` AS cluster,
         `resource.attributes.k8s.namespace.name` AS namespace,
         `resource.attributes.k8s.deployment.name` AS deployment,
         `resource.attributes.k8s.pod.name` AS pod
| KEEP @timestamp, cluster, namespace, deployment, pod, message
| SORT @timestamp DESC
| LIMIT 25
"""
)
Q_BURST_TABLE = (
    load_esql("restart-burst.esql")
    + """
| SORT total_delta DESC
| LIMIT 25
| RENAME `resource.attributes.k8s.cluster.name` AS cluster,
         `resource.attributes.k8s.namespace.name` AS namespace,
         `resource.attributes.k8s.deployment.name` AS deployment,
         `resource.attributes.k8s.container.name` AS container
"""
)
Q_OOM_TABLE = (
    load_esql("oom-phrase.esql")
    + """
| SORT hits DESC
| LIMIT 25
| RENAME `resource.attributes.k8s.cluster.name` AS cluster,
         `resource.attributes.k8s.namespace.name` AS namespace,
         `resource.attributes.k8s.deployment.name` AS deployment,
         `resource.attributes.k8s.container.name` AS container
"""
)
Q_MEM_TABLE = (
    load_esql("mem-limit-saturate.esql")
    + """
| SORT max_util DESC
| LIMIT 25
| RENAME `resource.attributes.k8s.cluster.name` AS cluster,
         `resource.attributes.k8s.namespace.name` AS namespace,
         `resource.attributes.k8s.deployment.name` AS deployment,
         `resource.attributes.k8s.container.name` AS container
"""
)

WORKLOAD_COLS = [
    _col("cluster", "cluster", "string", "Cluster"),
    _col("namespace", "namespace", "string", "Namespace"),
    _col("deployment", "deployment", "string", "Deployment"),
    _col("container", "container", "string", "Container"),
]


def build_oom_crash_dashboard():
    panels = [
        _text_panel("oom-md", "How to read OOM / crash", INTRO, 0, 0, 48, 8),
        _panel(
            "oom-kpi-hits",
            "OOM phrase hits",
            0, 8, 8, 6,
            lens_esql_metric("oom-kpi-hits-l", "oom_hits", Q_OOM_HITS, "oom_hits", "OOM hits", LOGS_DV),
        ),
        _panel(
            "oom-kpi-deploys",
            "Deployments with OOM phrase",
            8, 8, 8, 6,
            lens_esql_metric(
                "oom-kpi-deploys-l", "deployments", Q_OOM_DEPLOYMENTS, "deployments", "Deployments", LOGS_DV
            ),
        ),
        _panel(
            "oom-kpi-pods",
            "Pods with OOM phrase",
            16, 8, 8, 6,
            lens_esql_metric("oom-kpi-pods-l", "pods", Q_OOM_PODS, "pods", "Pods", LOGS_DV),
        ),
        _panel(
            "oom-kpi-burst",
            "Restart-burst deployments",
            24, 8, 8, 6,
            lens_esql_metric(
                "oom-kpi-burst-l",
                "burst_deployments",
                Q_BURST_DEPLOYMENTS,
                "burst_deployments",
                "Bursts",
                METRICS_DV,
            ),
        ),
        _panel(
            "oom-kpi-mem",
            "Memory limit ≥95% containers",
            32, 8, 8, 6,
            lens_esql_metric(
                "oom-kpi-mem-l", "saturating", Q_MEM_SATURATING, "saturating", "Saturating", METRICS_DV
            ),
        ),
        _panel(
            "oom-kpi-crash",
            "Pods with restart Δ ≥1",
            40, 8, 8, 6,
            lens_esql_metric(
                "oom-kpi-crash-l", "crashing_pods", Q_CRASHING_PODS, "crashing_pods", "Crashing pods", METRICS_DV
            ),
        ),
        _panel(
            "oom-xy-burst",
            "Multi-pod restart Δ by deployment",
            0, 14, 24, 12,
            lens_esql_xy(
                "oom-xy-burst-l",
                Q_RESTART_XY,
                "t",
                "t",
                "total_delta",
                "total_delta",
                "Restart Δ",
                "deployment",
                "deployment",
                "Deployment",
                METRICS_DV,
                series="bar_stacked",
            ),
        ),
        _panel(
            "oom-xy-mem",
            "Memory limit util ≥95% by deployment",
            24, 14, 24, 12,
            lens_esql_xy(
                "oom-xy-mem-l",
                Q_MEM_XY,
                "t",
                "t",
                "max_util",
                "max_util",
                "Max util",
                "deployment",
                "deployment",
                "Deployment",
                METRICS_DV,
                series="line",
            ),
        ),
        _panel(
            "oom-xy-phrase",
            "OOM phrase hits by deployment",
            0, 26, 24, 12,
            lens_esql_xy(
                "oom-xy-phrase-l",
                Q_OOM_XY,
                "t",
                "t",
                "hits",
                "hits",
                "Hits",
                "deployment",
                "deployment",
                "Deployment",
                LOGS_DV,
                series="bar_stacked",
            ),
        ),
        _panel(
            "oom-logs",
            "Recent OOM log lines",
            24, 26, 24, 12,
            lens_esql_table(
                "oom-logs-l",
                Q_OOM_LOGS,
                [
                    _col("ts", "@timestamp", "date", "@timestamp"),
                    _col("cluster", "cluster", "string", "Cluster"),
                    _col("namespace", "namespace", "string", "Namespace"),
                    _col("deployment", "deployment", "string", "Deployment"),
                    _col("pod", "pod", "string", "Pod"),
                    _col("message", "message", "string", "Message"),
                ],
                LOGS_DV,
                page_size=8,
            ),
        ),
        _panel(
            "oom-tbl-burst",
            "Restart bursts (alert grain: ≥2 pods, Δ≥1)",
            0, 38, 48, 12,
            lens_esql_table(
                "oom-tbl-burst-l",
                Q_BURST_TABLE,
                WORKLOAD_COLS
                + [
                    _col("crashing_pods", "crashing_pods", "number", "Crashing pods", metric=True),
                    _col("total_delta", "total_delta", "number", "Total Δ", metric=True),
                    _col("max_pod_delta", "max_pod_delta", "number", "Max pod Δ", metric=True),
                ],
                METRICS_DV,
            ),
        ),
        _panel(
            "oom-tbl-phrase",
            "OOM phrases by workload",
            0, 50, 24, 12,
            lens_esql_table(
                "oom-tbl-phrase-l",
                Q_OOM_TABLE,
                WORKLOAD_COLS
                + [
                    _col("hits", "hits", "number", "Hits", metric=True),
                    _col("pods", "pods", "number", "Pods", metric=True),
                ],
                LOGS_DV,
            ),
        ),
        _panel(
            "oom-tbl-mem",
            "Memory limit ≥95% (alert grain: ≥5 samples)",
            24, 50, 24, 12,
            lens_esql_table(
                "oom-tbl-mem-l",
                Q_MEM_TABLE,
                WORKLOAD_COLS
                + [
                    _col("max_util", "max_util", "number", "Max util", metric=True),
                    _col("samples", "samples", "number", "Samples", metric=True),
                ],
                METRICS_DV,
            ),
        ),
    ]
    return _saved(
        "[SRE] K8s OOM / crash",
        "Track Kubernetes OOM phrases, multi-pod restart bursts, and memory-limit saturation. Default last 3 days.",
        panels,
        _dash_refs(panels),
        time_from="now-3d",
    )


def verify_query_specs():
    """NOW()-relative copies of dashboard queries for apply.py verify."""
    window = "@timestamp >= NOW() - 3 days"

    def swap(q):
        return q.replace(TS, window)

    return [
        ("dash-oom-hits", swap(Q_OOM_HITS)),
        ("dash-burst-kpi", swap(Q_BURST_DEPLOYMENTS)),
        ("dash-mem-kpi", swap(Q_MEM_SATURATING)),
        ("dash-crash-pods", swap(Q_CRASHING_PODS)),
        ("dash-burst-table", swap(Q_BURST_TABLE)),
        ("dash-oom-table", swap(Q_OOM_TABLE)),
        ("dash-mem-table", swap(Q_MEM_TABLE)),
        ("dash-restart-xy", swap(Q_RESTART_XY)),
        ("dash-mem-xy", swap(Q_MEM_XY)),
        ("dash-oom-logs", swap(Q_OOM_LOGS)),
    ]
