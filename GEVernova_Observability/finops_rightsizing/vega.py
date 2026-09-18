"""Cut A rightsizing overview: ES|QL charts + Vega-Lite specs.

Kibana 9.6 serverless dashboard API vis types are metric/xy/heatmap/data_table —
not Vega. Same queries drive native bar_horizontal panels that actually render.
Vega-Lite specs stay here and as Visualize saved objects (gev-finops-vega-bar-*).
"""
from __future__ import annotations

import json

DASHBOARD_ID = "finops-rightsizing-overview"

Q_SCATTER = """FROM metrics-aws.ec2_metrics-*
| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend
| STATS cpu_avg = ROUND(AVG(aws.ec2.metrics.CPUUtilization.avg), 2),
        cpu_p95 = ROUND(PERCENTILE(aws.ec2.metrics.CPUUtilization.avg, 95), 2),
        samples = COUNT(*)
    BY instance = cloud.instance.name, account = cloud.account.id, instance_id = cloud.instance.id, machine = cloud.machine.type
| WHERE cpu_avg IS NOT NULL
| SORT cpu_avg ASC
| LIMIT 50
"""

Q_HEAT = """FROM metrics-aws.ec2_metrics-*
| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend
    AND cloud.instance.id IS NOT NULL
| EVAL instance = CONCAT(COALESCE(cloud.instance.name, "ec2"), " ", cloud.instance.id)
| STATS cpu = ROUND(AVG(aws.ec2.metrics.CPUUtilization.avg), 2)
    BY t = BUCKET(@timestamp, 24, ?_tstart, ?_tend), instance
| WHERE cpu IS NOT NULL
| SORT t ASC
| KEEP t, instance, cpu
"""

Q_RDS = """FROM metrics-aws.rds-*
| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend
    AND aws.rds.metrics.DBLoad.avg IS NOT NULL
| STATS dbload_avg = ROUND(AVG(aws.rds.metrics.DBLoad.avg), 4), samples = COUNT(*)
    BY db = aws.dimensions.DBInstanceIdentifier, account = cloud.account.id
| SORT dbload_avg ASC
| LIMIT 20
"""

INTRO = """## How to read this
- **Identified** = open + in_progress (hidden excluded). **Captured** = done only. **Parked** = hidden. Never add identified and captured.
- Scatter and heatmap are **live CloudWatch CPU**, not Compute Optimizer recs. Persistently idle = low avg **and** low p95.
- RDS uses **DBLoad** (CPUUtilization is not ingested here). That is waste evidence, not a rec.
- The queue table is the copy-paste surface for `gev-finops-rightsize-run` (optional ARN).
- Workflow-generated recs (`source: spend_spike_workflow`) land here after a spend-spike classifies **orphaned_idle**. Savings stay **$0** unless Compute Optimizer provided a figure — do not invent USD.
- Time picker drives scatter, heatmap, and RDS. Rec KPIs use the **latest** rec per fingerprint (`finops-rightsizing-latest`).

[Spend vs savings](/s/finops/app/dashboards#/view/finops-spend-vs-savings) · [AWS Billing Overview](/s/finops/app/dashboards#/view/finops-aws-billing-overview-unblended)"""

FOOTNOTE = """## Quota (not dollars)
FilterLogEvents is **5 TPS per account per region** — CloudWatch API hygiene, not a savings rec. ResourceCount is the same story.

## Spend alerts (unchanged)
- `gev-finops-alert-dod-spike` — linked-account day-over-day
- `gev-finops-alert-calendar-mtd` — $77k calendar MTD
- `gev-finops-alert-service-dod-spike` — SERVICE + account 1.5× vs prior days
- `meridian-alert-staging-daily` — account `985408759551` > $2,000/day"""

METRIC_STYLE = {
    "density": "compact",
    "primary": {
        "position": "bottom",
        "labels": {"alignment": "left"},
        "value": {"alignment": "right", "sizing": "auto"},
    },
}

XY_AXIS = {
    "x": {
        "title": {"text": "", "visible": True},
        "ticks": {"visible": True},
        "grid": {"visible": True},
        "labels": {"orientation": "horizontal"},
        "scale": "linear",
        "domain": {"type": "fit", "rounding": False},
    },
    "y": {
        "title": {"text": "", "visible": True},
        "ticks": {"visible": True},
        "grid": {"visible": True},
        "labels": {"orientation": "horizontal"},
        "scale": "linear",
        "domain": {"type": "full", "rounding": True},
    },
}


def _esql_url(query: str) -> dict:
    return {
        "%type%": "esql",
        "%context%": True,
        "%timefield%": "@timestamp",
        "query": query.strip(),
    }


def spec_scatter() -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Each point is an EC2 instance in the dashboard time range. X is average CPU %, Y is p95 CPU %. Dashed lines are 5% avg and 10% p95 idle thresholds. Size is sample count. Not a Compute Optimizer rec.",
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(Q_SCATTER)},
        "params": [
            {
                "name": "accountSel",
                "select": {"type": "point", "fields": ["account"]},
                "bind": "legend",
            }
        ],
        "layer": [
            {
                "mark": {"type": "circle", "opacity": 0.75, "stroke": "#1a1a1a"},
                "encoding": {
                    "x": {
                        "field": "cpu_avg",
                        "type": "quantitative",
                        "title": "CPU avg %",
                    },
                    "y": {
                        "field": "cpu_p95",
                        "type": "quantitative",
                        "title": "CPU p95 %",
                    },
                    "size": {
                        "field": "samples",
                        "type": "quantitative",
                        "title": "Samples",
                        "scale": {"range": [40, 400]},
                    },
                    "color": {
                        "field": "account",
                        "type": "nominal",
                        "title": "Account",
                    },
                    "opacity": {
                        "condition": {"param": "accountSel", "value": 0.85},
                        "value": 0.15,
                    },
                    "tooltip": [
                        {"field": "instance", "type": "nominal", "title": "Instance"},
                        {"field": "instance_id", "type": "nominal", "title": "Instance id"},
                        {"field": "machine", "type": "nominal", "title": "Type"},
                        {"field": "account", "type": "nominal", "title": "Account"},
                        {"field": "cpu_avg", "type": "quantitative", "title": "CPU avg %"},
                        {"field": "cpu_p95", "type": "quantitative", "title": "CPU p95 %"},
                        {"field": "samples", "type": "quantitative", "title": "Samples"},
                    ],
                },
            },
            {
                "mark": {"type": "rule", "strokeDash": [6, 4], "color": "#BD271E"},
                "data": {"values": [{}]},
                "encoding": {"x": {"datum": 5, "type": "quantitative"}},
            },
            {
                "mark": {"type": "rule", "strokeDash": [6, 4], "color": "#BD271E"},
                "data": {"values": [{}]},
                "encoding": {"y": {"datum": 10, "type": "quantitative"}},
            },
        ],
    }


def spec_heatmap() -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "EC2 CPU avg % by instance id and time. Scale is 0–20% so idle stays visible. Y labels are name + instance id (names are not unique). Time axis is temporal; buckets follow the dashboard time picker.",
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(Q_HEAT)},
        "mark": {"type": "rect", "tooltip": True},
        "encoding": {
            "x": {"field": "t", "type": "temporal", "title": "Time"},
            "y": {
                "field": "instance",
                "type": "nominal",
                "title": "Instance",
                "sort": {"op": "mean", "field": "cpu", "order": "ascending"},
            },
            "color": {
                "field": "cpu",
                "type": "quantitative",
                "title": "CPU avg %",
                "scale": {
                    "scheme": "yelloworangered",
                    "domainMin": 0,
                    "domainMax": 20,
                },
                "legend": {"orient": "right"},
            },
            "tooltip": [
                {"field": "instance", "type": "nominal", "title": "Instance"},
                {"field": "t", "type": "temporal", "title": "Time"},
                {"field": "cpu", "type": "quantitative", "title": "CPU avg %"},
            ],
        },
        "height": 280,
    }


def spec_hbar(
    query: str,
    cat: str,
    metric: str,
    cat_title: str,
    metric_title: str,
    *,
    description: str = "",
    sort: str = "-x",
    scheme: str | None = "blues",
    color_field: str | None = None,
    color_title: str | None = None,
    metric_format: str = ",.2f",
    extra_tooltips: list | None = None,
) -> dict:
    """Horizontal Vega-Lite bar with end labels. Category on Y, metric on X."""
    tooltip = [
        {"field": cat, "type": "nominal", "title": cat_title},
        {
            "field": metric,
            "type": "quantitative",
            "title": metric_title,
            "format": metric_format,
        },
    ]
    if extra_tooltips:
        tooltip.extend(extra_tooltips)
    color: dict
    if color_field:
        color = {
            "field": color_field,
            "type": "nominal",
            "title": color_title or color_field,
            "legend": {"orient": "bottom", "columns": 3},
        }
        tooltip.insert(
            1,
            {
                "field": color_field,
                "type": "nominal",
                "title": color_title or color_field,
            },
        )
    else:
        color = {
            "field": metric,
            "type": "quantitative",
            "scale": {"scheme": scheme or "blues"},
            "legend": None,
        }
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": description,
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(query)},
        "encoding": {
            "y": {
                "field": cat,
                "type": "nominal",
                "title": cat_title,
                "sort": sort,
                "axis": {"labelLimit": 220, "labelPadding": 4, "grid": False},
            },
            "x": {
                "field": metric,
                "type": "quantitative",
                "title": metric_title,
                "axis": {"grid": True, "tickCount": 5},
            },
        },
        "layer": [
            {
                "mark": {
                    "type": "bar",
                    "cornerRadiusEnd": 3,
                    "tooltip": True,
                    "height": {"band": 0.72},
                },
                "encoding": {"color": color, "tooltip": tooltip},
            },
            {
                "mark": {
                    "type": "text",
                    "align": "left",
                    "baseline": "middle",
                    "dx": 4,
                    "fontSize": 11,
                    "color": "#343741",
                },
                "encoding": {
                    "text": {
                        "field": metric,
                        "type": "quantitative",
                        "format": metric_format,
                    },
                },
            },
        ],
        "config": {
            "view": {"stroke": None},
            "axis": {"labelFontSize": 11, "titleFontSize": 12, "domain": False},
        },
    }


def spec_rds() -> dict:
    return spec_hbar(
        Q_RDS,
        "db",
        "dbload_avg",
        "DB instance",
        "DBLoad avg",
        description=(
            "Lowest RDS DBLoad averages in the time picker. "
            "CPUUtilization is not ingested; DBLoad is the idle signal. Not a Compute Optimizer rec."
        ),
        sort="x",
        scheme=None,
        color_field="account",
        color_title="Account",
        metric_format=".4f",
        extra_tooltips=[
            {"field": "samples", "type": "quantitative", "title": "Samples"},
        ],
    )


def vis_attributes(title: str, spec: dict, description: str = "") -> dict:
    vis_state = {
        "title": title,
        "type": "vega",
        "aggs": [],
        "params": {"spec": json.dumps(spec)},
    }
    return {
        "title": title,
        "description": description,
        "visState": json.dumps(vis_state),
        "uiStateJSON": "{}",
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps(
                {"query": {"query": "", "language": "kuery"}, "filter": []}
            )
        },
    }


# Live dashboard bar panels → Vega visualization saved objects.
# Queries match the hub / rightsizing ES|QL bars. Do not invent USD.
Q_HUB_SERVICE = """FROM metrics-aws.billing-default
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
  AND aws.billing.group_definition.key == "SERVICE"
| STATS cost = SUM(aws.billing.UnblendedCost.amount) BY service = aws.billing.group_by.SERVICE
| SORT cost DESC
| LIMIT 15
"""

Q_HUB_ITYPE = """FROM metrics-aws.billing-default
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
  AND aws.billing.group_definition.key == "INSTANCE_TYPE"
  AND aws.billing.group_by.INSTANCE_TYPE != "NoInstanceType"
| STATS cost = SUM(aws.billing.UnblendedCost.amount) BY itype = aws.billing.group_by.INSTANCE_TYPE
| SORT cost DESC
| LIMIT 15
"""

Q_HUB_CPU = """FROM metrics-aws.ec2_metrics-default
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
  AND aws.dimensions.InstanceId IS NOT NULL
  AND cloud.machine.type IS NOT NULL
| STATS avg_cpu = AVG(aws.ec2.metrics.CPUUtilization.avg) BY itype = cloud.machine.type
| SORT avg_cpu ASC
| LIMIT 15
"""

Q_HUB_INFER = """FROM .kibana-inference-token-usage
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
| STATS tokens = SUM(token_usage.total_tokens) BY model = model.model_id
| SORT tokens DESC
| LIMIT 12
"""

Q_HUB_GENAI = """FROM traces-agent_builder.otel-default
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
  AND attributes.gen_ai.usage.input_tokens IS NOT NULL
| STATS tokens = SUM(attributes.gen_ai.usage.input_tokens) + SUM(attributes.gen_ai.usage.output_tokens) BY model = attributes.gen_ai.request.model
| SORT tokens DESC
| LIMIT 12
"""

HUB_ID = "meridian-finops-llm-observability-dynamic-aws"

VEGA_BAR_CHARTS = [
    {
        "dashboard": HUB_ID,
        "panel_id": "4331149b-a434-490d-8844-fb61f83905d9",
        "vis_id": "gev-finops-vega-bar-service",
        "title": "AWS cost by service (SERVICE grouping incomplete after Sep 3)",
        "description": "Cost Explorer SERVICE slice. Incomplete after Sep 3. Do not add to LINKED_ACCOUNT.",
        "spec": lambda: spec_hbar(
            Q_HUB_SERVICE,
            "service",
            "cost",
            "Service",
            "Unblended USD",
            description="SERVICE grouping unblended. Incomplete after Sep 3. Do not add to LINKED_ACCOUNT.",
            sort="-x",
            scheme="blues",
            metric_format=",.0f",
        ),
    },
    {
        "dashboard": HUB_ID,
        "panel_id": "f3562f3d-9d07-4203-a0be-8b945a2624d1",
        "vis_id": "gev-finops-vega-bar-itype",
        "title": "Cost by INSTANCE_TYPE (exclude NoInstanceType; grain incomplete)",
        "description": "INSTANCE_TYPE slice only. Not the full bill.",
        "spec": lambda: spec_hbar(
            Q_HUB_ITYPE,
            "itype",
            "cost",
            "Instance type",
            "Unblended USD",
            description="INSTANCE_TYPE Cost Explorer slice. Exclude NoInstanceType. Grain incomplete.",
            sort="-x",
            scheme="blues",
            metric_format=",.0f",
        ),
    },
    {
        "dashboard": HUB_ID,
        "panel_id": "d097722a-724a-4b29-8766-aa0c4523cb2e",
        "vis_id": "gev-finops-vega-bar-cpu",
        "title": "EC2 avg CPU by instance type (evidence, not a recommendation)",
        "description": "Live CloudWatch CPU by machine type. Not a Compute Optimizer rec.",
        "spec": lambda: spec_hbar(
            Q_HUB_CPU,
            "itype",
            "avg_cpu",
            "Instance type",
            "CPU avg %",
            description="Live CloudWatch CPU avg by instance type. Lowest first. Not a rec.",
            sort="x",
            scheme="yelloworangered",
            metric_format=".1f",
        ),
    },
    {
        "dashboard": HUB_ID,
        "panel_id": "ad1f3e69-176b-4b9b-a04c-ab383f61ab14",
        "vis_id": "gev-finops-vega-bar-infer",
        "title": "Inference tokens by model",
        "description": "Kibana inference token usage by model id.",
        "spec": lambda: spec_hbar(
            Q_HUB_INFER,
            "model",
            "tokens",
            "Model",
            "Tokens",
            description="Kibana inference token usage by model.",
            sort="-x",
            scheme="tealblues",
            metric_format=",.0f",
        ),
    },
    {
        "dashboard": HUB_ID,
        "panel_id": "951a31b1-1ed5-43d9-9702-7cafcc453c22",
        "vis_id": "gev-finops-vega-bar-genai",
        "title": "Kibana Agent Builder gen_ai tokens by model (not GE apps)",
        "description": "Agent Builder gen_ai input+output tokens. Not GE application traffic.",
        "spec": lambda: spec_hbar(
            Q_HUB_GENAI,
            "model",
            "tokens",
            "Model",
            "Tokens",
            description="Agent Builder gen_ai tokens by model. Not GE apps.",
            sort="-x",
            scheme="tealblues",
            metric_format=",.0f",
        ),
    },
    {
        "dashboard": DASHBOARD_ID,
        "panel_id": "rs-vega-rds",
        "vis_id": "gev-finops-vega-bar-rds",
        "title": "RDS idle evidence: lowest DBLoad (not CPU; not a rec)",
        "description": "RDS DBLoad idle evidence. Not a Compute Optimizer rec.",
        "spec": spec_rds,
    },
]

ALLOC_SECTION = "36ed8c3c-901b-40a2-bfc7-7d687c5dd54e"
INFER_SECTION = "438c6380-dee0-45c7-9222-9c80f780b2ca"

# Dashboard API layout for native bar_horizontal (serverless cannot embed type:vega).
HBAR_LAYOUT = {
    "4331149b-a434-490d-8844-fb61f83905d9": {
        "section_id": ALLOC_SECTION,
        "grid": (0, 0, 28, 16),
        "query": Q_HUB_SERVICE,
        "cat": "service",
        "metric": "cost",
        "cat_title": "Service",
        "metric_title": "Unblended USD",
    },
    "f3562f3d-9d07-4203-a0be-8b945a2624d1": {
        "section_id": ALLOC_SECTION,
        "grid": (0, 72, 24, 14),
        "query": Q_HUB_ITYPE,
        "cat": "itype",
        "metric": "cost",
        "cat_title": "Instance type",
        "metric_title": "Unblended USD",
    },
    "d097722a-724a-4b29-8766-aa0c4523cb2e": {
        "section_id": ALLOC_SECTION,
        "grid": (24, 72, 24, 14),
        "query": Q_HUB_CPU,
        "cat": "itype",
        "metric": "avg_cpu",
        "cat_title": "Instance type",
        "metric_title": "CPU avg %",
    },
    "ad1f3e69-176b-4b9b-a04c-ab383f61ab14": {
        "section_id": INFER_SECTION,
        "grid": (0, 6, 24, 14),
        "query": Q_HUB_INFER,
        "cat": "model",
        "metric": "tokens",
        "cat_title": "Model",
        "metric_title": "Tokens",
    },
    "951a31b1-1ed5-43d9-9702-7cafcc453c22": {
        "section_id": INFER_SECTION,
        "grid": (0, 20, 48, 12),
        "query": Q_HUB_GENAI,
        "cat": "model",
        "metric": "tokens",
        "cat_title": "Model",
        "metric_title": "Tokens",
    },
    "rs-vega-rds": {
        "section_id": None,
        "grid": (0, 74, 24, 12),
        "query": Q_RDS,
        "cat": "db",
        "metric": "dbload_avg",
        "cat_title": "DB instance",
        "metric_title": "DBLoad avg",
    },
}


def native_hbar_panel(item: dict) -> dict:
    """xy bar_horizontal with data labels — what serverless Kibana actually renders."""
    layout = HBAR_LAYOUT[item["panel_id"]]
    x, y, w, h = layout["grid"]
    return {
        "id": item["panel_id"],
        "type": "vis",
        "grid": {"x": x, "y": y, "w": w, "h": h},
        "config": {
            "type": "xy",
            "title": item["title"],
            "hide_title": False,
            "legend": {
                "visibility": "hidden",
                "placement": "outside",
                "layout": {"type": "grid", "truncate": {"max_lines": 1}},
                "position": "right",
            },
            "axis": {
                "x": {
                    "title": {"text": layout["cat_title"], "visible": True},
                    "ticks": {"visible": True},
                    "grid": {"visible": True},
                    "labels": {"orientation": "horizontal"},
                    "scale": "ordinal",
                    "domain": {"type": "fit", "rounding": False},
                },
                "y": {
                    "title": {"text": layout["metric_title"], "visible": True},
                    "ticks": {"visible": True},
                    "grid": {"visible": True},
                    "labels": {"orientation": "horizontal"},
                    "scale": "linear",
                    "domain": {"type": "full", "rounding": True},
                },
            },
            "styling": {
                "overlays": {
                    "partial_buckets": {"visible": False},
                    "current_time_marker": {"visible": False},
                },
                "interpolation": "linear",
                "bars": {"minimum_height": 1, "data_labels": {"visible": True}},
            },
            "layers": [
                {
                    "sampling": 1,
                    "ignore_global_filters": False,
                    "data_source": {"type": "esql", "query": layout["query"].strip()},
                    "type": "bar_horizontal",
                    "y": [
                        {
                            "column": layout["metric"],
                            "label": layout["metric_title"],
                            "axis": "y",
                            "color": {"type": "auto"},
                        }
                    ],
                    "x": {
                        "column": layout["cat"],
                        "label": layout["cat_title"],
                    },
                }
            ],
        },
    }


def _vis(panel_id, grid, config):
    return {
        "id": panel_id,
        "type": "vis",
        "grid": {"x": grid[0], "y": grid[1], "w": grid[2], "h": grid[3]},
        "config": config,
    }


def _markdown(panel_id, title, content, grid):
    x, y, w, h = grid
    return {
        "id": panel_id,
        "type": "markdown",
        "grid": {"x": x, "y": y, "w": w, "h": h},
        "config": {
            "hide_title": False,
            "title": title,
            "content": content,
            "settings": {"open_links_in_new_tab": True},
        },
    }


def _metric(panel_id, title, grid, data_view_id, field, label, operation, kql=None):
    metric = {
        "format": {"type": "number", "decimals": 2, "compact": False},
        "label": label,
        "field": field,
        "empty_as_null": True,
        "operation": operation,
        "type": "primary",
        "color": {"type": "auto"},
    }
    if kql:
        metric["filter"] = {"language": "kql", "expression": kql}
    if operation == "unique_count":
        metric.pop("format", None)
    return _vis(
        panel_id,
        grid,
        {
            "type": "metric",
            "title": title,
            "sampling": 1,
            "ignore_global_filters": False,
            "data_source": {"type": "data_view_reference", "ref_id": data_view_id},
            "styling": METRIC_STYLE,
            "metrics": [metric],
            "hide_title": False,
        },
    )


def _terms_row(label, field, limit, direction="desc"):
    return {
        "operation": "terms",
        "label": label,
        "fields": [field],
        "limit": limit,
        "rank_by": {"type": "metric", "metric_index": 0, "direction": direction},
        "visible": True,
        "alignment": "left",
        "color": {"type": "auto"},
        "click_filter": False,
    }


def _metric_col(label, field, operation, percentile=None):
    col = {
        "format": {"type": "number", "decimals": 2, "compact": False},
        "label": label,
        "field": field,
        "operation": operation,
        "visible": True,
        "color": {"type": "auto"},
        "alignment": "right",
    }
    if operation == "sum":
        col["empty_as_null"] = True
    if percentile is not None:
        col["percentile"] = percentile
    return col


def scatter_panel():
    axis = json.loads(json.dumps(XY_AXIS))
    axis["x"]["title"]["text"] = "CPU avg %"
    axis["y"]["title"]["text"] = "CPU p95 %"
    return _vis(
        "rs-vega-scatter",
        (0, 10, 48, 16),
        {
            "type": "xy",
            "title": "Waste scatter: EC2 CPU avg vs p95 (live metrics, not a rec)",
            "hide_title": False,
            "legend": {
                "visibility": "hidden",
                "placement": "outside",
                "layout": {
                    "type": "grid",
                    "truncate": {"max_lines": 1, "enabled": True},
                },
                "position": "right",
                "size": "m",
            },
            "axis": axis,
            "styling": {
                "overlays": {
                    "partial_buckets": {"visible": False},
                    "current_time_marker": {"visible": False},
                },
                "fitting": {"type": "none"},
                "interpolation": "linear",
                "points": {"visibility": "visible"},
            },
            "layers": [
                {
                    "sampling": 1,
                    "ignore_global_filters": False,
                    "data_source": {"type": "esql", "query": Q_SCATTER.strip()},
                    "type": "line",
                    "breakdown_by": {
                        "column": "instance",
                        "label": "Instance",
                        "color": {
                            "mode": "categorical",
                            "palette": "elastic_line_optimized",
                            "mapping": [],
                        },
                    },
                    "y": [
                        {
                            "column": "cpu_p95",
                            "label": "CPU p95 %",
                            "axis": "y",
                            "color": {"type": "auto"},
                        }
                    ],
                    "x": {"column": "cpu_avg", "label": "CPU avg %"},
                }
            ],
        },
    )


def heatmap_panel():
    return _vis(
        "rs-vega-heat",
        (0, 26, 48, 20),
        {
            "type": "heatmap",
            "legend": {
                "truncate_after_lines": 1,
                "visibility": "visible",
                "position": "right",
            },
            "title": "EC2 CPU heatmap (idle is persistent low color; follows time picker)",
            "sampling": 1,
            "ignore_global_filters": False,
            "axis": {
                "x": {
                    "title": {"text": "Time", "visible": True},
                    "labels": {"visible": True, "orientation": "angled"},
                    "scale": "temporal",
                },
                "y": {
                    "title": {"text": "Instance", "visible": True},
                    "labels": {"visible": True},
                },
            },
            "x": {"column": "t", "label": "Time"},
            "y": {"column": "instance", "label": "Instance"},
            "data_source": {"type": "esql", "query": Q_HEAT.strip()},
            "styling": {"cells": {"labels": {"visible": False}}},
            "metric": {
                "column": "cpu",
                "label": "CPU avg %",
                "color": {"type": "auto"},
            },
            "hide_title": False,
        },
    )


def rds_bar_panel():
    axis = json.loads(json.dumps(XY_AXIS))
    axis["x"]["scale"] = "ordinal"
    axis["x"]["title"]["text"] = "DB instance"
    axis["y"]["title"]["text"] = "DBLoad avg"
    return _vis(
        "rs-vega-rds",
        (0, 58, 24, 12),
        {
            "type": "xy",
            "title": "RDS idle evidence: lowest DBLoad (not CPU; not a rec)",
            "hide_title": False,
            "legend": {
                "visibility": "hidden",
                "placement": "outside",
                "layout": {"type": "grid", "truncate": {"max_lines": 1}},
                "position": "right",
            },
            "axis": axis,
            "styling": {
                "overlays": {
                    "partial_buckets": {"visible": False},
                    "current_time_marker": {"visible": False},
                },
                "interpolation": "linear",
                "bars": {"minimum_height": 1, "data_labels": {"visible": True}},
            },
            "layers": [
                {
                    "sampling": 1,
                    "ignore_global_filters": False,
                    "data_source": {"type": "esql", "query": Q_RDS.strip()},
                    "type": "bar_horizontal",
                    "y": [
                        {
                            "column": "dbload_avg",
                            "label": "DBLoad avg",
                            "axis": "y",
                            "color": {"type": "auto"},
                        }
                    ],
                    "x": {"column": "db", "label": "DB instance"},
                }
            ],
        },
    )


def overview_payload(rs_id: str, _ec2_id: str, rds_id: str) -> dict:
    identified = 'finops.rightsizing.status : ("open" or "in_progress")'
    captured = "finops.rightsizing.status : done"
    parked = "finops.rightsizing.status : hidden"
    panels = [
        {
            "id": "rs-acct",
            "type": "options_list_control",
            "grid": {"x": 0, "y": 0, "w": 12, "h": 3},
            "config": {
                "title": "Account ID",
                "field_name": "cloud.account.id",
                "data_view_id": rs_id,
            },
        },
        _markdown("rs-md", "How to read this", INTRO, (0, 0, 48, 4)),
        _metric(
            "rs-m-identified",
            "Identified monthly savings (open + in progress)",
            (0, 4, 12, 6),
            rs_id,
            "finops.rightsizing.estimated_monthly_savings",
            "Identified USD / mo",
            "sum",
            identified,
        ),
        _metric(
            "rs-m-captured",
            "Captured savings (done only — do not add to identified)",
            (12, 4, 12, 6),
            rs_id,
            "finops.rightsizing.realized_savings",
            "Captured USD / mo",
            "sum",
            captured,
        ),
        _metric(
            "rs-m-parked",
            "Parked / hidden (not in identified)",
            (24, 4, 12, 6),
            rs_id,
            "finops.rightsizing.estimated_monthly_savings",
            "Parked USD / mo",
            "sum",
            parked,
        ),
        _metric(
            "rs-m-recs",
            "Recs in snapshot",
            (36, 4, 12, 6),
            rs_id,
            "finops.rightsizing.id",
            "Recs",
            "unique_count",
        ),
        scatter_panel(),
        heatmap_panel(),
        _vis(
            "rs-table",
            (0, 46, 48, 12),
            {
                "type": "data_table",
                "title": "Recommended actions (visible queue — copy ARN into gev-finops-rightsize-run)",
                "filters": [
                    {
                        "disabled": False,
                        "type": "condition",
                        "condition": {
                            "field": "finops.rightsizing.status",
                            "operator": "is_one_of",
                            "value": ["open", "in_progress"],
                        },
                    }
                ],
                "sampling": 1,
                "ignore_global_filters": False,
                "data_source": {"type": "data_view_reference", "ref_id": rs_id},
                "metrics": [
                    _metric_col(
                        "Est. monthly USD",
                        "finops.rightsizing.estimated_monthly_savings",
                        "sum",
                    )
                ],
                "rows": [
                    _terms_row("Resource", "finops.rightsizing.resource_name", 25),
                    _terms_row("Action", "finops.rightsizing.action", 10),
                    _terms_row("Current", "finops.rightsizing.current_type", 10),
                    _terms_row("Recommended", "finops.rightsizing.recommended_type", 10),
                    _terms_row("ARN", "finops.rightsizing.resource_arn", 25),
                ],
                "hide_title": False,
            },
        ),
        rds_bar_panel(),
        _vis(
            "rs-rds-table",
            (24, 58, 24, 12),
            {
                "type": "data_table",
                "title": "RDS DBLoad table (same evidence, copy-paste ids)",
                "sampling": 1,
                "ignore_global_filters": False,
                "data_source": {"type": "data_view_reference", "ref_id": rds_id},
                "metrics": [
                    _metric_col(
                        "DBLoad avg",
                        "aws.rds.metrics.DBLoad.avg",
                        "average",
                    )
                ],
                "rows": [
                    _terms_row(
                        "DB instance",
                        "aws.dimensions.DBInstanceIdentifier",
                        20,
                        "asc",
                    ),
                    _terms_row("Account", "cloud.account.id", 10, "asc"),
                ],
                "hide_title": False,
            },
        ),
        _markdown("rs-notes", "Quota + alerts", FOOTNOTE, (0, 70, 48, 6)),
    ]
    return {
        "title": "[FinOps] Rightsizing queue",
        "description": (
            "Identified = open + in_progress (hidden excluded). Captured = done. "
            "Never add the two. Scatter/heatmap/RDS are live CloudWatch evidence, not Compute Optimizer recs."
        ),
        "time_range": {"from": "now-14d", "to": "now"},
        "query": {"language": "kql", "expression": ""},
        "filters": [],
        "tags": ["finops", "ge-vernova"],
        "options": {
            "hide_panel_titles": False,
            "use_margins": True,
            "sync_colors": False,
            "sync_tooltips": False,
            "sync_cursor": True,
        },
        "panels": panels,
    }


def verify_vega_queries():
    def swap(q: str) -> str:
        return q.replace("?_tstart", "NOW() - 14 days").replace("?_tend", "NOW()")

    return [
        ("vega-scatter", swap(Q_SCATTER)),
        ("vega-heat", swap(Q_HEAT)),
        ("vega-rds", swap(Q_RDS)),
        ("vega-hub-service", swap(Q_HUB_SERVICE)),
        ("vega-hub-itype", swap(Q_HUB_ITYPE)),
        ("vega-hub-cpu", swap(Q_HUB_CPU)),
        ("vega-hub-infer", swap(Q_HUB_INFER)),
        ("vega-hub-genai", swap(Q_HUB_GENAI)),
    ]
