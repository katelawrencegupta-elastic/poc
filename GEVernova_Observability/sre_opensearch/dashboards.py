"""Lens builders for SRE OpenSearch Domain / Node dashboards."""
import importlib.util
import json
from pathlib import Path

_FINOPS = Path(__file__).resolve().parent.parent / "finops_rightsizing" / "dashboards.py"
_spec = importlib.util.spec_from_file_location("finops_dashboards", _FINOPS)
_fd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fd)
_dash_refs = _fd._dash_refs
_date_hist = _fd._date_hist
_panel = _fd._panel
_ref = _fd._ref
_saved = _fd._saved
_sum = _fd._sum
_terms = _fd._terms
_text_panel = _fd._text_panel
lens_metric = _fd.lens_metric
lens_table = _fd.lens_table
lens_xy_stacked = _fd.lens_xy_stacked

NS = 'aws.cloudwatch.namespace : "AWS/ES"'
DOMAIN_KQL = NS + " and not aws.dimensions.NodeId : *"
NODE_KQL = NS + " and aws.dimensions.NodeId : *"

F_GREEN = "aws.es.metrics.ClusterStatus_green.max"
F_YELLOW = "aws.es.metrics.ClusterStatus_yellow.max"
F_RED = "sre.es.cluster_red"
F_JVM = "aws.es.metrics.JVMMemoryPressure.max"
F_FREE = "aws.es.metrics.FreeStorageSpace.avg"
F_USED = "aws.es.metrics.ClusterUsedSpace.max"
F_USED_PCT = "sre.es.used_pct"
F_SEARCH = "aws.es.metrics.SearchRate.avg"
F_SLAT = "aws.es.metrics.SearchLatency.avg"
F_INDEX = "sre.es.indexing_rate"
F_ILAT = "aws.es.metrics.IndexingLatency.avg"
F_REJ_S = "aws.es.metrics.ThreadpoolSearchRejected.sum"
F_REJ_W = "aws.es.metrics.ThreadpoolWriteRejected.sum"
F_SNAP = "aws.es.metrics.AutomatedSnapshotFailure.max"
F_CPU = "aws.es.metrics.CPUUtilization.avg"
F_NODES = "sre.es.nodes"
F_DOMAIN = "aws.dimensions.DomainName"
F_NODE = "aws.dimensions.NodeId"
F_ACCT = "cloud.account.id"
F_REGION = "cloud.region"
F_HTTP2 = "aws.es.metrics.2xx.sum"
F_HTTP4 = "aws.es.metrics.4xx.sum"
F_HTTP5 = "sre.es.http_5xx"
F_BLOCKED = "aws.es.metrics.ClusterIndexWritesBlocked.max"
F_SH_ACTIVE = "aws.es.metrics.Shards_active.max"
F_SH_UNASS = "aws.es.metrics.Shards_unassigned.max"
F_SH_INIT = "aws.es.metrics.Shards_initializing.max"
F_MASTER_CPU = "aws.es.metrics.MasterCPUUtilization.max"
F_MASTER_JVM = "aws.es.metrics.MasterJVMMemoryPressure.max"
F_MASTER_REACH = "aws.es.metrics.MasterReachableFromNode.max"
F_KIBANA = "aws.es.metrics.KibanaHealthyNodes.max"

DOMAIN_INTRO = (
    "## OpenSearch Domain (CloudWatch AWS/ES)\n"
    "Domain-level series only (`NodeId` absent). Quote **cluster status** and "
    "**used-space %** from this view, not from the Node dashboard.\n\n"
    "- Free / used storage is CloudWatch **MB**.\n"
    "- Used-space % = `ClusterUsedSpace / (ClusterUsedSpace + FreeStorageSpace)`.\n"
    "- Cluster red and HTTP 5xx are runtime fields from `_source` (unmapped integers).\n"
    "- Yellow / writes-blocked / snapshot page into this view. CPU and write-reject page to Node.\n\n"
    "[Fleet](/s/sre/app/dashboards#/view/sre-opensearch-fleet) · "
    "[Node view](/s/sre/app/dashboards#/view/sre-opensearch-node) · "
    "[K8s OOM / crash](/s/sre/app/dashboards#/view/sre-k8s-oom-crash)"
)

NODE_INTRO = (
    "## OpenSearch Node (CloudWatch AWS/ES)\n"
    "Same rates split by `NodeId`. Filter Domain first, then Node.\n\n"
    "- CPU / JVM / storage are per-node CloudWatch metrics.\n"
    "- Do not add node free-storage to the domain used-space %.\n"
    "- CPU >90/95 and write-reject page into this view.\n\n"
    "[Fleet](/s/sre/app/dashboards#/view/sre-opensearch-fleet) · "
    "[Domain view](/s/sre/app/dashboards#/view/sre-opensearch-domain) · "
    "[K8s OOM / crash](/s/sre/app/dashboards#/view/sre-k8s-oom-crash)"
)

FLEET_INTRO = (
    "## OpenSearch Fleet\n"
    "One row per domain (no `NodeId`). Use this for standup; page-in views are Domain and Node.\n\n"
    "- Yellow / red / used-space % / writes-blocked / snapshot are domain grain.\n"
    "- CPU on this table is domain-level CloudWatch Average. Node CPU pages separately.\n"
    "- HTTP 5xx is runtime from `_source` (unmapped).\n\n"
    "[Domain](/s/sre/app/dashboards#/view/sre-opensearch-domain) · "
    "[Node](/s/sre/app/dashboards#/view/sre-opensearch-node) · "
    "[K8s OOM / crash](/s/sre/app/dashboards#/view/sre-k8s-oom-crash)"
)


def _max(col_id, field, label, decimals=2):
    return {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "max",
        "params": {
            "format": {"id": "number", "params": {"compact": False, "decimals": decimals}},
            "emptyAsNull": True,
        },
        "scale": "ratio",
        "sourceField": field,
    }


def _avg_col(col_id, field, label, decimals=2):
    return {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "average",
        "params": {
            "format": {"id": "number", "params": {"compact": False, "decimals": decimals}},
            "emptyAsNull": True,
        },
        "scale": "ratio",
        "sourceField": field,
    }


def _min_col(col_id, field, label, decimals=2):
    return {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "min",
        "params": {
            "format": {"id": "number", "params": {"compact": False, "decimals": decimals}},
            "emptyAsNull": True,
        },
        "scale": "ratio",
        "sourceField": field,
    }


def _sum_col(col_id, field, label, decimals=2):
    return {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "sum",
        "params": {
            "format": {"id": "number", "params": {"compact": False, "decimals": decimals}},
            "emptyAsNull": True,
        },
        "scale": "ratio",
        "sourceField": field,
    }


def lens_xy_max(layer_id, date_id, metric_id, split_id, metric_field, metric_label, split_field, split_label, kql, data_view_id, size=8, series="line", decimals=2):
    columns = {
        date_id: _date_hist(date_id),
        split_id: _terms(split_id, split_field, split_label, metric_id, size),
        metric_id: _max(metric_id, metric_field, metric_label, decimals),
    }
    return {
        "description": "",
        "references": [_ref(data_view_id, layer_id)],
        "state": {
            "adHocDataViews": {},
            "datasourceStates": {
                "formBased": {
                    "layers": {
                        layer_id: {
                            "columnOrder": [date_id, split_id, metric_id],
                            "columns": columns,
                            "incompleteColumns": {},
                        }
                    }
                },
                "textBased": {"layers": {}},
            },
            "filters": [],
            "internalReferences": [],
            "query": {"language": "kuery", "query": kql or ""},
            "visualization": {
                "axisTitlesVisibilitySettings": {"x": True, "yLeft": False, "yRight": True},
                "fittingFunction": "None",
                "preferredSeriesType": series,
                "layers": [
                    {
                        "layerId": layer_id,
                        "layerType": "data",
                        "seriesType": series,
                        "xAccessor": date_id,
                        "accessors": [metric_id],
                        "splitAccessor": split_id,
                    }
                ],
                "legend": {
                    "isVisible": True,
                    "position": "right",
                    "legendSize": "medium",
                    "shouldTruncate": True,
                    "showSingleSeries": True,
                },
                "valueLabels": "hide",
            },
        },
        "title": "",
        "type": "lens",
        "visualizationType": "lnsXY",
    }


def lens_xy_sum(layer_id, date_id, metric_id, split_id, metric_field, metric_label, split_field, split_label, kql, data_view_id, size=8, series="bar_stacked"):
    columns = {
        date_id: _date_hist(date_id),
        split_id: _terms(split_id, split_field, split_label, metric_id, size),
        metric_id: _sum_col(metric_id, metric_field, metric_label, 0),
    }
    return {
        "description": "",
        "references": [_ref(data_view_id, layer_id)],
        "state": {
            "adHocDataViews": {},
            "datasourceStates": {
                "formBased": {
                    "layers": {
                        layer_id: {
                            "columnOrder": [date_id, split_id, metric_id],
                            "columns": columns,
                            "incompleteColumns": {},
                        }
                    }
                },
                "textBased": {"layers": {}},
            },
            "filters": [],
            "internalReferences": [],
            "query": {"language": "kuery", "query": kql or ""},
            "visualization": {
                "axisTitlesVisibilitySettings": {"x": True, "yLeft": False, "yRight": True},
                "fittingFunction": "None",
                "preferredSeriesType": series,
                "layers": [
                    {
                        "layerId": layer_id,
                        "layerType": "data",
                        "seriesType": series,
                        "xAccessor": date_id,
                        "accessors": [metric_id],
                        "splitAccessor": split_id,
                    }
                ],
                "legend": {
                    "isVisible": True,
                    "position": "right",
                    "legendSize": "medium",
                    "shouldTruncate": True,
                    "showSingleSeries": True,
                },
                "valueLabels": "hide",
            },
        },
        "title": "",
        "type": "lens",
        "visualizationType": "lnsXY",
    }


def _controls(data_view_id, fields):
    panels = {}
    refs = []
    for i, (field, title) in enumerate(fields):
        cid = f"ctrl-{i}-{field.replace('.', '-')}"
        panels[cid] = {
            "type": "optionsListControl",
            "order": i,
            "grow": False,
            "width": "medium",
            "explicitInput": {
                "id": cid,
                "dataViewId": data_view_id,
                "exclude": False,
                "existsSelected": False,
                "fieldName": field,
                "searchTechnique": "wildcard",
                "selectedOptions": [],
                "singleSelect": False,
                "sort": {"by": "_count", "direction": "desc"},
                "title": title,
                "enhancements": {},
            },
        }
        refs.append(
            {
                "id": data_view_id,
                "name": f"controlGroup_{cid}:optionsListDataView",
                "type": "index-pattern",
            }
        )
    extra_attrs = {
        "controlGroupInput": {
            "chainingSystem": "HIERARCHICAL",
            "controlStyle": "oneLine",
            "ignoreParentSettingsJSON": json.dumps(
                {
                    "ignoreFilters": False,
                    "ignoreQuery": False,
                    "ignoreTimerange": False,
                    "ignoreValidations": False,
                }
            ),
            "showApplySelections": False,
            "panelsJSON": json.dumps(panels),
        }
    }
    return extra_attrs, refs


def build_domain_dashboard(dv_id):
    extra_attrs, extra_refs = _controls(
        dv_id,
        [(F_ACCT, "Account"), (F_REGION, "Region"), (F_DOMAIN, "DomainName")],
    )
    panels = [
        _text_panel("os-md", "How to read Domain", DOMAIN_INTRO, 0, 0, 48, 6),
        _panel("os-red", "Cluster red", 0, 6, 8, 6, lens_metric("os-red-l", "os-red-c", F_RED, "Red", DOMAIN_KQL, dv_id, op="max")),
        _panel("os-yel", "Cluster yellow", 8, 6, 8, 6, lens_metric("os-yel-l", "os-yel-c", F_YELLOW, "Yellow", DOMAIN_KQL, dv_id, op="max")),
        _panel("os-grn", "Cluster green", 16, 6, 8, 6, lens_metric("os-grn-l", "os-grn-c", F_GREEN, "Green", DOMAIN_KQL, dv_id, op="max")),
        _panel("os-nodes", "Nodes", 24, 6, 8, 6, lens_metric("os-nodes-l", "os-nodes-c", F_NODES, "Nodes", DOMAIN_KQL, dv_id, op="max")),
        _panel("os-jvm", "JVM pressure max %", 32, 6, 8, 6, lens_metric("os-jvm-l", "os-jvm-c", F_JVM, "JVM %", DOMAIN_KQL, dv_id, op="max")),
        _panel("os-snap", "Snapshot failures", 40, 6, 8, 6, lens_metric("os-snap-l", "os-snap-c", F_SNAP, "Failures", DOMAIN_KQL, dv_id, op="max")),
        _panel("os-http2", "HTTP 2xx sum", 0, 12, 8, 6, lens_metric("os-http2-l", "os-http2-c", F_HTTP2, "2xx", DOMAIN_KQL, dv_id, op="sum")),
        _panel("os-http4", "HTTP 4xx sum", 8, 12, 8, 6, lens_metric("os-http4-l", "os-http4-c", F_HTTP4, "4xx", DOMAIN_KQL, dv_id, op="sum")),
        _panel("os-http5", "HTTP 5xx sum (page)", 16, 12, 8, 6, lens_metric("os-http5-l", "os-http5-c", F_HTTP5, "5xx", DOMAIN_KQL, dv_id, op="sum")),
        _panel("os-block", "Writes blocked (page >0)", 24, 12, 8, 6, lens_metric("os-block-l", "os-block-c", F_BLOCKED, "Blocked", DOMAIN_KQL, dv_id, op="max")),
        _panel("os-unass", "Shards unassigned", 32, 12, 8, 6, lens_metric("os-unass-l", "os-unass-c", F_SH_UNASS, "Unassigned", DOMAIN_KQL, dv_id, op="max")),
        _panel("os-reach", "Master reachable min", 40, 12, 8, 6, lens_metric("os-reach-l", "os-reach-c", F_MASTER_REACH, "Reachable", DOMAIN_KQL, dv_id, op="min")),
        _panel(
            "os-http5-xy",
            "HTTP 5xx by domain",
            0, 18, 24, 12,
            lens_xy_sum("os-http5-xy-l", "os-http5-xy-d", "os-http5-xy-m", "os-http5-xy-s", F_HTTP5, "5xx", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-shard-xy",
            "Unassigned shards by domain",
            24, 18, 24, 12,
            lens_xy_max("os-shard-xy-l", "os-shard-xy-d", "os-shard-xy-m", "os-shard-xy-s", F_SH_UNASS, "Unassigned", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id, decimals=0),
        ),
        _panel(
            "os-mcpu-xy",
            "Master CPU % by domain",
            0, 30, 16, 12,
            lens_xy_max("os-mcpu-xy-l", "os-mcpu-xy-d", "os-mcpu-xy-m", "os-mcpu-xy-s", F_MASTER_CPU, "Master CPU %", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-mjvm-xy",
            "Master JVM pressure % by domain",
            16, 30, 16, 12,
            lens_xy_max("os-mjvm-xy-l", "os-mjvm-xy-d", "os-mjvm-xy-m", "os-mjvm-xy-s", F_MASTER_JVM, "Master JVM %", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-shard-tbl",
            "Shards / master / HTTP by domain",
            32, 30, 16, 12,
            lens_table(
                "os-shard-tbl-l",
                {
                    "os-sh-dom": _terms("os-sh-dom", F_DOMAIN, "Domain", "os-sh-un", 15),
                    "os-sh-act": _max("os-sh-act", F_SH_ACTIVE, "Active", 0),
                    "os-sh-un": _max("os-sh-un", F_SH_UNASS, "Unassigned", 0),
                    "os-sh-in": _max("os-sh-in", F_SH_INIT, "Initializing", 0),
                    "os-sh-reach": _min_col("os-sh-reach", F_MASTER_REACH, "Master reachable", 0),
                    "os-sh-kb": _max("os-sh-kb", F_KIBANA, "Kibana healthy", 0),
                    "os-sh-5xx": _sum_col("os-sh-5xx", F_HTTP5, "5xx", 0),
                },
                dv_id,
                kql=DOMAIN_KQL,
            ),
        ),
        _panel(
            "os-free",
            "Free storage MB (domain)",
            0, 42, 8, 6,
            lens_metric("os-free-l", "os-free-c", F_FREE, "Free MB", DOMAIN_KQL, dv_id, op="average"),
        ),
        _panel(
            "os-usedpct",
            "Used-space % (page >85 / >90)",
            8, 42, 8, 6,
            lens_metric("os-usedpct-l", "os-usedpct-c", F_USED_PCT, "Used %", DOMAIN_KQL, dv_id, op="max"),
        ),
        _panel(
            "os-jvm-xy",
            "JVM memory pressure % by domain",
            16, 42, 32, 12,
            lens_xy_max("os-jvm-xy-l", "os-jvm-xy-d", "os-jvm-xy-m", "os-jvm-xy-s", F_JVM, "JVM %", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-stor-xy",
            "Free storage MB by domain",
            0, 54, 24, 12,
            lens_xy_max("os-stor-xy-l", "os-stor-xy-d", "os-stor-xy-m", "os-stor-xy-s", F_FREE, "Free MB", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-used-xy",
            "Used-space % by domain",
            24, 54, 24, 12,
            lens_xy_max("os-used-xy-l", "os-used-xy-d", "os-used-xy-m", "os-used-xy-s", F_USED_PCT, "Used %", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-search-xy",
            "Search rate by domain",
            0, 66, 24, 12,
            lens_xy_max("os-search-xy-l", "os-search-xy-d", "os-search-xy-m", "os-search-xy-s", F_SEARCH, "Search/s", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-slat-xy",
            "Search latency by domain",
            24, 66, 24, 12,
            lens_xy_max("os-slat-xy-l", "os-slat-xy-d", "os-slat-xy-m", "os-slat-xy-s", F_SLAT, "Search latency", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-idx-xy",
            "Index rate by domain",
            0, 78, 24, 12,
            lens_xy_max("os-idx-xy-l", "os-idx-xy-d", "os-idx-xy-m", "os-idx-xy-s", F_INDEX, "Index/s", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-ilat-xy",
            "Index latency by domain",
            24, 78, 24, 12,
            lens_xy_max("os-ilat-xy-l", "os-ilat-xy-d", "os-ilat-xy-m", "os-ilat-xy-s", F_ILAT, "Index latency", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
        _panel(
            "os-rej",
            "Rejected threadpools (search / write sum)",
            0, 90, 24, 12,
            lens_table(
                "os-rej-l",
                {
                    "os-rej-dom": _terms("os-rej-dom", F_DOMAIN, "Domain", "os-rej-s", 15),
                    "os-rej-s": _sum("os-rej-s", F_REJ_S, "Search rejected"),
                    "os-rej-w": _sum("os-rej-w", F_REJ_W, "Write rejected"),
                },
                dv_id,
                kql=DOMAIN_KQL,
            ),
        ),
        _panel(
            "os-snap-tbl",
            "Snapshot failures by domain",
            24, 90, 24, 12,
            lens_table(
                "os-snap-tbl-l",
                {
                    "os-st-dom": _terms("os-st-dom", F_DOMAIN, "Domain", "os-st-snap", 15),
                    "os-st-snap": _max("os-st-snap", F_SNAP, "Snapshot failures", 0),
                    "os-st-jvm": _max("os-st-jvm", F_JVM, "JVM %"),
                    "os-st-used": _max("os-st-used", F_USED_PCT, "Used %"),
                    "os-st-blk": _max("os-st-blk", F_BLOCKED, "Writes blocked", 0),
                },
                dv_id,
                kql=DOMAIN_KQL,
            ),
        ),
        _panel(
            "os-rej-xy",
            "Search rejected (stacked) by domain",
            0, 102, 24, 12,
            lens_xy_stacked(
                "os-rej-xy-l", "os-rej-xy-d", "os-rej-xy-m", "os-rej-xy-s",
                F_REJ_S, F_DOMAIN, "Domain", DOMAIN_KQL, dv_id, 8,
            ),
        ),
        _panel(
            "os-wrej-xy",
            "Write rejected (stacked) by domain",
            24, 102, 24, 12,
            lens_xy_sum("os-wrej-xy-l", "os-wrej-xy-d", "os-wrej-xy-m", "os-wrej-xy-s", F_REJ_W, "Write rejected", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
    ]
    return _saved(
        "[SRE] OpenSearch Domain",
        "CloudWatch AWS/ES domain grain. Cluster red/yellow, used-space %, writes-blocked, snapshot, HTTP 5xx, shards, and master page into this view. Default last 6 hours.",
        panels,
        _dash_refs(panels, extra_refs),
        time_from="now-6h",
        extra_attrs=extra_attrs,
    )


def build_node_dashboard(dv_id):
    extra_attrs, extra_refs = _controls(
        dv_id,
        [
            (F_ACCT, "Account"),
            (F_REGION, "Region"),
            (F_DOMAIN, "DomainName"),
            (F_NODE, "NodeId"),
        ],
    )
    panels = [
        _text_panel("on-md", "How to read Node", NODE_INTRO, 0, 0, 48, 5),
        _panel("on-cpu", "CPU % max", 0, 5, 12, 6, lens_metric("on-cpu-l", "on-cpu-c", F_CPU, "CPU %", NODE_KQL, dv_id, op="max")),
        _panel("on-jvm", "JVM pressure max %", 12, 5, 12, 6, lens_metric("on-jvm-l", "on-jvm-c", F_JVM, "JVM %", NODE_KQL, dv_id, op="max")),
        _panel("on-free", "Free storage MB avg", 24, 5, 12, 6, lens_metric("on-free-l", "on-free-c", F_FREE, "Free MB", NODE_KQL, dv_id, op="average")),
        _panel("on-rej", "Search rejected sum", 36, 5, 12, 6, lens_metric("on-rej-l", "on-rej-c", F_REJ_S, "Search rejected", NODE_KQL, dv_id, op="sum")),
        _panel(
            "on-cpu-xy",
            "CPU % by NodeId",
            0, 11, 24, 12,
            lens_xy_max("on-cpu-xy-l", "on-cpu-xy-d", "on-cpu-xy-m", "on-cpu-xy-s", F_CPU, "CPU %", F_NODE, "NodeId", NODE_KQL, dv_id),
        ),
        _panel(
            "on-jvm-xy",
            "JVM pressure % by NodeId",
            24, 11, 24, 12,
            lens_xy_max("on-jvm-xy-l", "on-jvm-xy-d", "on-jvm-xy-m", "on-jvm-xy-s", F_JVM, "JVM %", F_NODE, "NodeId", NODE_KQL, dv_id),
        ),
        _panel(
            "on-stor-xy",
            "Free storage MB by NodeId",
            0, 23, 24, 12,
            lens_xy_max("on-stor-xy-l", "on-stor-xy-d", "on-stor-xy-m", "on-stor-xy-s", F_FREE, "Free MB", F_NODE, "NodeId", NODE_KQL, dv_id),
        ),
        _panel(
            "on-search-xy",
            "Search rate by NodeId",
            24, 23, 24, 12,
            lens_xy_max("on-search-xy-l", "on-search-xy-d", "on-search-xy-m", "on-search-xy-s", F_SEARCH, "Search/s", F_NODE, "NodeId", NODE_KQL, dv_id),
        ),
        _panel(
            "on-slat-xy",
            "Search latency by NodeId",
            0, 35, 24, 12,
            lens_xy_max("on-slat-xy-l", "on-slat-xy-d", "on-slat-xy-m", "on-slat-xy-s", F_SLAT, "Search latency", F_NODE, "NodeId", NODE_KQL, dv_id),
        ),
        _panel(
            "on-idx-xy",
            "Index rate by NodeId",
            24, 35, 24, 12,
            lens_xy_max("on-idx-xy-l", "on-idx-xy-d", "on-idx-xy-m", "on-idx-xy-s", F_INDEX, "Index/s", F_NODE, "NodeId", NODE_KQL, dv_id),
        ),
        _panel(
            "on-tbl",
            "Nodes: CPU / JVM / storage / rejects",
            0, 47, 48, 14,
            lens_table(
                "on-tbl-l",
                {
                    "on-t-dom": _terms("on-t-dom", F_DOMAIN, "Domain", "on-t-jvm", 15),
                    "on-t-node": _terms("on-t-node", F_NODE, "NodeId", "on-t-jvm", 15),
                    "on-t-cpu": _max("on-t-cpu", F_CPU, "CPU %"),
                    "on-t-jvm": _max("on-t-jvm", F_JVM, "JVM %"),
                    "on-t-free": _avg_col("on-t-free", F_FREE, "Free MB"),
                    "on-t-rej": _sum("on-t-rej", F_REJ_S, "Search rejected"),
                    "on-t-wrj": _sum("on-t-wrj", F_REJ_W, "Write rejected"),
                },
                dv_id,
                kql=NODE_KQL,
            ),
        ),
    ]
    return _saved(
        "[SRE] OpenSearch Node",
        "CloudWatch AWS/ES node grain (NodeId present). CPU, JVM, storage, search/index rates split by NodeId. Default last 6 hours.",
        panels,
        _dash_refs(panels, extra_refs),
        time_from="now-6h",
        extra_attrs=extra_attrs,
    )


def build_fleet_dashboard(dv_id):
    extra_attrs, extra_refs = _controls(
        dv_id,
        [(F_ACCT, "Account"), (F_REGION, "Region"), (F_DOMAIN, "DomainName")],
    )
    panels = [
        _text_panel("of-md", "How to read Fleet", FLEET_INTRO, 0, 0, 48, 6),
        _panel(
            "of-doms",
            "Domains",
            0, 6, 8, 6,
            lens_metric("of-doms-l", "of-doms-c", F_DOMAIN, "Domains", DOMAIN_KQL, dv_id, op="unique_count"),
        ),
        _panel("of-red", "Cluster red max", 8, 6, 8, 6, lens_metric("of-red-l", "of-red-c", F_RED, "Red", DOMAIN_KQL, dv_id, op="max")),
        _panel("of-yel", "Cluster yellow max", 16, 6, 8, 6, lens_metric("of-yel-l", "of-yel-c", F_YELLOW, "Yellow", DOMAIN_KQL, dv_id, op="max")),
        _panel("of-http5", "HTTP 5xx sum", 24, 6, 8, 6, lens_metric("of-http5-l", "of-http5-c", F_HTTP5, "5xx", DOMAIN_KQL, dv_id, op="sum")),
        _panel("of-block", "Writes blocked max", 32, 6, 8, 6, lens_metric("of-block-l", "of-block-c", F_BLOCKED, "Blocked", DOMAIN_KQL, dv_id, op="max")),
        _panel("of-snap", "Snapshot failures max", 40, 6, 8, 6, lens_metric("of-snap-l", "of-snap-c", F_SNAP, "Failures", DOMAIN_KQL, dv_id, op="max")),
        _panel(
            "of-tbl",
            "Fleet: status / storage / JVM / CPU / rejects / 5xx / shards",
            0, 12, 48, 16,
            lens_table(
                "of-tbl-l",
                {
                    "of-t-dom": _terms("of-t-dom", F_DOMAIN, "Domain", "of-t-yel", 20),
                    "of-t-acct": _terms("of-t-acct", F_ACCT, "Account", "of-t-yel", 20),
                    "of-t-red": _max("of-t-red", F_RED, "Red", 0),
                    "of-t-yel": _max("of-t-yel", F_YELLOW, "Yellow", 0),
                    "of-t-used": _max("of-t-used", F_USED_PCT, "Used %"),
                    "of-t-jvm": _max("of-t-jvm", F_JVM, "JVM %"),
                    "of-t-cpu": _max("of-t-cpu", F_CPU, "CPU %"),
                    "of-t-srj": _sum("of-t-srj", F_REJ_S, "Search rejected"),
                    "of-t-wrj": _sum("of-t-wrj", F_REJ_W, "Write rejected"),
                    "of-t-5xx": _sum_col("of-t-5xx", F_HTTP5, "5xx", 0),
                    "of-t-un": _max("of-t-un", F_SH_UNASS, "Unassigned", 0),
                    "of-t-blk": _max("of-t-blk", F_BLOCKED, "Writes blocked", 0),
                    "of-t-snap": _max("of-t-snap", F_SNAP, "Snapshot", 0),
                    "of-t-reach": _min_col("of-t-reach", F_MASTER_REACH, "Master reachable", 0),
                },
                dv_id,
                kql=DOMAIN_KQL,
            ),
        ),
        _panel(
            "of-yel-xy",
            "Cluster yellow by domain",
            0, 28, 24, 12,
            lens_xy_max("of-yel-xy-l", "of-yel-xy-d", "of-yel-xy-m", "of-yel-xy-s", F_YELLOW, "Yellow", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id, decimals=0),
        ),
        _panel(
            "of-http5-xy",
            "HTTP 5xx by domain",
            24, 28, 24, 12,
            lens_xy_sum("of-http5-xy-l", "of-http5-xy-d", "of-http5-xy-m", "of-http5-xy-s", F_HTTP5, "5xx", F_DOMAIN, "Domain", DOMAIN_KQL, dv_id),
        ),
    ]
    return _saved(
        "[SRE] OpenSearch Fleet",
        "Domain-grain fleet table for standup. Yellow/red, used-space %, JVM, CPU, rejects, HTTP 5xx, unassigned shards, writes-blocked, snapshot. Default last 6 hours.",
        panels,
        _dash_refs(panels, extra_refs),
        time_from="now-6h",
        extra_attrs=extra_attrs,
    )
