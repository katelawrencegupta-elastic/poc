"""Spend vs savings: Vega-Lite-inspired native charts.

Gallery patterns (https://vega.github.io/vega-lite/examples/):
  stacked area, table heatmap, labeled horizontal bars, bubble scatter.
Serverless dashboards API cannot embed type:vega, so the live panels are
xy/heatmap/waffle driven by the same ES|QL. Vega-Lite specs are Visualize SOs.

Spend = LINKED_ACCOUNT unblended. SERVICE is a slice. Identified = open +
in_progress (monthly). Captured = done/realized. Never add identified+captured.
"""
from __future__ import annotations

from vega import _esql_url, spec_hbar, vis_attributes

SVS_ID = "finops-spend-vs-savings"

ACCT_BILL = """EVAL account = CASE(
    COALESCE(aws.billing.group_by.LINKED_ACCOUNT, cloud.account.id) == "985408759551", "apm-stage",
    COALESCE(aws.billing.group_by.LINKED_ACCOUNT, cloud.account.id) == "041298796264", "monitoring / elastic-integration",
    COALESCE(aws.billing.group_by.LINKED_ACCOUNT, cloud.account.id) == "439106060789", "ESF (439106060789)",
    COALESCE(aws.billing.group_by.LINKED_ACCOUNT, cloud.account.id) == "119672459156", "ESF (119672459156)",
    COALESCE(aws.billing.group_by.LINKED_ACCOUNT, cloud.account.id)
)"""

ACCT_RS = """EVAL account = CASE(
    cloud.account.id == "985408759551", "apm-stage",
    cloud.account.id == "041298796264", "monitoring / elastic-integration",
    cloud.account.id == "439106060789", "ESF (439106060789)",
    cloud.account.id == "119672459156", "ESF (119672459156)",
    cloud.account.id
)"""

Q_SPEND_AREA = f"""FROM metrics-aws.billing-default
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
  AND aws.billing.group_definition.key == "LINKED_ACCOUNT"
| {ACCT_BILL}
| STATS spend = SUM(aws.billing.UnblendedCost.amount) BY day = BUCKET(@timestamp, 1d), account
| SORT day ASC
"""

Q_SPEND_HEAT = f"""FROM metrics-aws.billing-default
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
  AND aws.billing.group_definition.key == "LINKED_ACCOUNT"
| {ACCT_BILL}
| STATS spend = ROUND(SUM(aws.billing.UnblendedCost.amount), 2)
    BY t = BUCKET(@timestamp, 24, ?_tstart, ?_tend), account
| WHERE spend IS NOT NULL
| SORT t ASC
"""

Q_SPEND_ACCT = f"""FROM metrics-aws.billing-default
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
  AND aws.billing.group_definition.key == "LINKED_ACCOUNT"
| {ACCT_BILL}
| STATS spend = ROUND(SUM(aws.billing.UnblendedCost.amount), 2) BY account
| SORT spend DESC
| LIMIT 12
"""

Q_SVC = """FROM metrics-aws.billing-default
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
  AND aws.billing.group_definition.key == "SERVICE"
| STATS spend = ROUND(SUM(aws.billing.UnblendedCost.amount), 2)
    BY service = aws.billing.group_by.SERVICE
| SORT spend DESC
| LIMIT 12
"""

Q_ID_ACCT = f"""FROM finops-rightsizing-latest*
| WHERE finops.rightsizing.status IN ("open", "in_progress")
| {ACCT_RS}
| STATS identified = ROUND(SUM(finops.rightsizing.estimated_monthly_savings), 2), recs = COUNT(*)
    BY account
| SORT identified DESC
| LIMIT 12
"""

Q_ID_ACT = f"""FROM finops-rightsizing-latest*
| WHERE finops.rightsizing.status IN ("open", "in_progress")
| STATS identified = ROUND(SUM(finops.rightsizing.estimated_monthly_savings), 2)
    BY action = finops.rightsizing.action
| SORT identified DESC
| LIMIT 8
"""

Q_ID_HEAT = f"""FROM finops-rightsizing-latest*
| WHERE finops.rightsizing.status IN ("open", "in_progress")
| {ACCT_RS}
| STATS identified = ROUND(SUM(finops.rightsizing.estimated_monthly_savings), 2)
    BY account, action = finops.rightsizing.action
| WHERE identified IS NOT NULL
"""

Q_STATUS = """FROM finops-rightsizing-latest*
| STATS usd = ROUND(SUM(finops.rightsizing.estimated_monthly_savings), 2)
    BY status = finops.rightsizing.status
| SORT usd DESC
"""

INTRO = """## How to read spend vs savings
**Spend** is Cost Explorer **LINKED_ACCOUNT** unblended — the complete bill for the time picker (default 30 days). Do **not** add it to the SERVICE bars; that is the same dollars sliced by product.

**Identified** = open + in progress, **monthly** run-rate. **Captured** = done (`realized_savings`). **Parked** = hidden, not in identified. Never add identified and captured. The waffle is *estimated* $ by status — the captured KPI uses realized.

Charts follow [Vega-Lite](https://vega.github.io/vega-lite/examples/) patterns: stacked area, heatmap, labeled horizontal bars, bubble scatter. Time picker drives spend charts. Rec charts use the latest fingerprint (`finops-rightsizing-latest`).

[Rightsizing queue](#/view/finops-rightsizing-overview) · [AWS Billing Overview](#/view/finops-aws-billing-overview-unblended) · [Elastic Cloud billing](#/view/ess_billing-billingdashboard)"""

LEGEND = {
    "visibility": "visible",
    "placement": "outside",
    "layout": {"type": "grid", "truncate": {"max_lines": 1}},
    "position": "right",
}
LEGEND_OFF = {**LEGEND, "visibility": "hidden"}


def _vis(panel_id, grid, config):
    x, y, w, h = grid
    return {
        "id": panel_id,
        "type": "vis",
        "grid": {"x": x, "y": y, "w": w, "h": h},
        "config": config,
    }


def _axis(x_title="", y_title="", x_scale="ordinal"):
    return {
        "x": {
            "title": {"text": x_title, "visible": True},
            "ticks": {"visible": True},
            "grid": {"visible": True},
            "labels": {"orientation": "horizontal"},
            "scale": x_scale,
            "domain": {"type": "fit", "rounding": False},
        },
        "y": {
            "title": {"text": y_title, "visible": True},
            "ticks": {"visible": True},
            "grid": {"visible": True},
            "labels": {"orientation": "horizontal"},
            "scale": "linear",
            "domain": {"type": "full", "rounding": True},
        },
    }


def area_panel():
    """Vega-Lite stacked area / streamgraph analogue."""
    return _vis(
        "svs-xy",
        (0, 17, 32, 14),
        {
            "type": "xy",
            "title": "Daily unblended spend by account (LINKED_ACCOUNT — stacked area)",
            "hide_title": False,
            "legend": LEGEND,
            "axis": _axis("Day", "Unblended USD"),
            "styling": {
                "overlays": {
                    "partial_buckets": {"visible": False},
                    "current_time_marker": {"visible": False},
                },
                "interpolation": "smooth",
                "points": {"visibility": "auto"},
                "areas": {"fill_opacity": 0.75, "fill": "gradient"},
            },
            "layers": [
                {
                    "sampling": 1,
                    "ignore_global_filters": False,
                    "data_source": {"type": "esql", "query": Q_SPEND_AREA.strip()},
                    "type": "area_stacked",
                    "breakdown_by": {
                        "column": "account",
                        "label": "Account",
                        "color": {
                            "mode": "categorical",
                            "palette": "elastic_line_optimized",
                            "mapping": [],
                        },
                    },
                    "y": [
                        {
                            "column": "spend",
                            "label": "Unblended USD",
                            "axis": "y",
                            "color": {"type": "auto"},
                        }
                    ],
                    "x": {"column": "day", "label": "Day"},
                }
            ],
        },
    )


def waffle_panel():
    """Isotype / unit-chart analogue (Vega-Lite community unit charts)."""
    return _vis(
        "svs-pie",
        (32, 17, 16, 14),
        {
            "type": "waffle",
            "title": "Savings pipeline $ by status (estimated; captured KPI uses realized)",
            "hide_title": False,
            "sampling": 1,
            "ignore_global_filters": False,
            "data_source": {"type": "esql", "query": Q_STATUS.strip()},
            "legend": {
                "truncate_after_lines": 1,
                "visibility": "visible",
                "position": "right",
            },
            "styling": {
                "values": {"visible": True, "mode": "percentage", "percent_decimals": 0}
            },
            "metrics": [{"column": "usd", "color": {"type": "auto"}}],
            "group_by": [
                {
                    "column": "status",
                    "color": {
                        "mode": "categorical",
                        "palette": "default",
                        "mapping": [],
                    },
                }
            ],
        },
    )


def heat_spend_panel():
    """Vega-Lite table heatmap / lasagna analogue."""
    return _vis(
        "svs-heat",
        (0, 31, 48, 14),
        {
            "type": "heatmap",
            "title": "Spend heatmap: account × time (LINKED_ACCOUNT unblended)",
            "hide_title": False,
            "sampling": 1,
            "ignore_global_filters": False,
            "legend": {
                "truncate_after_lines": 1,
                "visibility": "visible",
                "position": "right",
            },
            "axis": {
                "x": {
                    "title": {"text": "Time", "visible": True},
                    "labels": {"visible": True, "orientation": "angled"},
                    "scale": "temporal",
                },
                "y": {
                    "title": {"text": "Account", "visible": True},
                    "labels": {"visible": True},
                },
            },
            "x": {"column": "t", "label": "Time"},
            "y": {"column": "account", "label": "Account"},
            "data_source": {"type": "esql", "query": Q_SPEND_HEAT.strip()},
            "styling": {"cells": {"labels": {"visible": False}}},
            "metric": {
                "column": "spend",
                "label": "Unblended USD",
                "color": {"type": "auto"},
            },
        },
    )


def hbar_panel(panel_id, title, query, cat, metric, cat_title, metric_title, grid):
    """Vega-Lite labeled horizontal bar analogue."""
    x, y, w, h = grid
    return _vis(
        panel_id,
        (x, y, w, h),
        {
            "type": "xy",
            "title": title,
            "hide_title": False,
            "legend": LEGEND_OFF,
            "axis": _axis(cat_title, metric_title),
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
                    "data_source": {"type": "esql", "query": query.strip()},
                    "type": "bar_horizontal",
                    "y": [
                        {
                            "column": metric,
                            "label": metric_title,
                            "axis": "y",
                            "color": {"type": "auto"},
                        }
                    ],
                    "x": {"column": cat, "label": cat_title},
                }
            ],
        },
    )


def scatter_panel():
    """Vega-Lite bubble plot analogue: identified $ vs open rec count."""
    return _vis(
        "svs-scatter",
        (0, 73, 24, 14),
        {
            "type": "xy",
            "title": "Bubble: identified USD / mo vs open recs (not trailing spend)",
            "hide_title": False,
            "legend": LEGEND,
            "axis": _axis("Identified USD / mo", "Open recs", x_scale="linear"),
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
                    "data_source": {"type": "esql", "query": Q_ID_ACCT.strip()},
                    "type": "line",
                    "breakdown_by": {
                        "column": "account",
                        "label": "Account",
                        "color": {
                            "mode": "categorical",
                            "palette": "elastic_line_optimized",
                            "mapping": [],
                        },
                    },
                    "y": [
                        {
                            "column": "recs",
                            "label": "Open recs",
                            "axis": "y",
                            "color": {"type": "auto"},
                        }
                    ],
                    "x": {"column": "identified", "label": "Identified USD / mo"},
                }
            ],
        },
    )


def heat_action_panel():
    """Trellis / heatmap analogue: account × action identified $."""
    return _vis(
        "svs-act-heat",
        (24, 73, 24, 14),
        {
            "type": "heatmap",
            "title": "Identified heatmap: account × action (open + in progress)",
            "hide_title": False,
            "sampling": 1,
            "ignore_global_filters": False,
            "legend": {
                "truncate_after_lines": 1,
                "visibility": "visible",
                "position": "right",
            },
            "axis": {
                "x": {
                    "title": {"text": "Action", "visible": True},
                    "labels": {"visible": True, "orientation": "horizontal"},
                    "scale": "ordinal",
                },
                "y": {
                    "title": {"text": "Account", "visible": True},
                    "labels": {"visible": True},
                },
            },
            "x": {"column": "action", "label": "Action"},
            "y": {"column": "account", "label": "Account"},
            "data_source": {"type": "esql", "query": Q_ID_HEAT.strip()},
            "styling": {"cells": {"labels": {"visible": True}}},
            "metric": {
                "column": "identified",
                "label": "Identified USD / mo",
                "color": {"type": "auto"},
            },
        },
    )


def markdown_panel():
    return {
        "id": "svs-md",
        "type": "markdown",
        "grid": {"x": 0, "y": 5, "w": 48, "h": 6},
        "config": {
            "hide_title": False,
            "title": "How to read this",
            "content": INTRO,
            "settings": {"open_links_in_new_tab": True},
        },
    }


def chart_panels():
    return [
        markdown_panel(),
        area_panel(),
        waffle_panel(),
        heat_spend_panel(),
        hbar_panel(
            "svs-spend-acct",
            "Spend by account (LINKED_ACCOUNT — same grain as the KPI)",
            Q_SPEND_ACCT,
            "account",
            "spend",
            "Account",
            "Unblended USD",
            (0, 45, 24, 14),
        ),
        hbar_panel(
            "svs-id-acct",
            "Identified savings by account (open + in progress, monthly)",
            Q_ID_ACCT,
            "account",
            "identified",
            "Account",
            "Identified USD / mo",
            (24, 45, 24, 14),
        ),
        hbar_panel(
            "svs-svc",
            "Top AWS services (SERVICE grain — do not add to LINKED_ACCOUNT)",
            Q_SVC,
            "service",
            "spend",
            "Service",
            "Unblended USD",
            (0, 59, 24, 14),
        ),
        hbar_panel(
            "svs-act",
            "Identified savings by action (open + in progress)",
            Q_ID_ACT,
            "action",
            "identified",
            "Action",
            "Identified USD / mo",
            (24, 59, 24, 14),
        ),
        scatter_panel(),
        heat_action_panel(),
    ]


def spec_area() -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "LINKED_ACCOUNT unblended by day and account. Stacked area (Vega-Lite stacked area analogue). Not a SERVICE total.",
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(Q_SPEND_AREA)},
        "mark": {"type": "area", "opacity": 0.75, "tooltip": True},
        "encoding": {
            "x": {"field": "day", "type": "temporal", "title": "Day"},
            "y": {
                "field": "spend",
                "type": "quantitative",
                "stack": "zero",
                "title": "Unblended USD",
            },
            "color": {"field": "account", "type": "nominal", "title": "Account"},
        },
    }


def spec_heat() -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "LINKED_ACCOUNT unblended heatmap. Account × time. Vega-Lite table heatmap analogue.",
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(Q_SPEND_HEAT)},
        "mark": {"type": "rect", "tooltip": True},
        "encoding": {
            "x": {"field": "t", "type": "temporal", "title": "Time"},
            "y": {"field": "account", "type": "nominal", "title": "Account"},
            "color": {
                "field": "spend",
                "type": "quantitative",
                "title": "Unblended USD",
                "scale": {"scheme": "yelloworangered"},
            },
        },
        "height": 220,
    }


def spec_bubble() -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Each bubble is an account. X is identified monthly USD (open+in_progress). Y is rec count. Size is identified. Not trailing spend.",
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(Q_ID_ACCT)},
        "mark": {"type": "circle", "opacity": 0.8, "stroke": "#1a1a1a", "tooltip": True},
        "encoding": {
            "x": {
                "field": "identified",
                "type": "quantitative",
                "title": "Identified USD / mo",
            },
            "y": {"field": "recs", "type": "quantitative", "title": "Open recs"},
            "size": {
                "field": "identified",
                "type": "quantitative",
                "title": "Identified USD / mo",
                "scale": {"range": [80, 400]},
            },
            "color": {"field": "account", "type": "nominal", "title": "Account"},
        },
    }


VEGA_VIS = [
    {
        "vis_id": "gev-finops-vega-svs-area",
        "title": "[FinOps] Daily spend stacked area (LINKED_ACCOUNT)",
        "spec": spec_area,
        "description": "Vega-Lite stacked area. LINKED_ACCOUNT unblended.",
    },
    {
        "vis_id": "gev-finops-vega-svs-heat",
        "title": "[FinOps] Spend heatmap account × time",
        "spec": spec_heat,
        "description": "Vega-Lite table heatmap. LINKED_ACCOUNT unblended.",
    },
    {
        "vis_id": "gev-finops-vega-svs-spend-acct",
        "title": "[FinOps] Spend by account (labeled bars)",
        "spec": lambda: spec_hbar(
            Q_SPEND_ACCT,
            "account",
            "spend",
            "Account",
            "Unblended USD",
            description="LINKED_ACCOUNT unblended by account. Vega-Lite labeled horizontal bar.",
            metric_format=",.0f",
        ),
        "description": "Vega-Lite labeled horizontal bar. LINKED_ACCOUNT.",
    },
    {
        "vis_id": "gev-finops-vega-svs-id-acct",
        "title": "[FinOps] Identified by account (labeled bars)",
        "spec": lambda: spec_hbar(
            Q_ID_ACCT,
            "account",
            "identified",
            "Account",
            "Identified USD / mo",
            description="Open + in_progress monthly identified. Not trailing spend.",
            metric_format=",.0f",
        ),
        "description": "Identified monthly by account. Open + in progress.",
    },
    {
        "vis_id": "gev-finops-vega-svs-svc",
        "title": "[FinOps] Top services (SERVICE slice)",
        "spec": lambda: spec_hbar(
            Q_SVC,
            "service",
            "spend",
            "Service",
            "Unblended USD",
            description="SERVICE slice. Do not add to LINKED_ACCOUNT.",
            metric_format=",.0f",
        ),
        "description": "SERVICE Cost Explorer slice.",
    },
    {
        "vis_id": "gev-finops-vega-svs-act",
        "title": "[FinOps] Identified by action (labeled bars)",
        "spec": lambda: spec_hbar(
            Q_ID_ACT,
            "action",
            "identified",
            "Action",
            "Identified USD / mo",
            description="Open + in_progress identified by action.",
            metric_format=",.0f",
        ),
        "description": "Identified monthly by action.",
    },
    {
        "vis_id": "gev-finops-vega-svs-bubble",
        "title": "[FinOps] Identified vs recs bubble",
        "spec": spec_bubble,
        "description": "Vega-Lite bubble plot. Identified monthly vs open recs.",
    },
]


def vis_so_payload(item: dict) -> dict:
    spec = item["spec"]() if callable(item["spec"]) else item["spec"]
    return {
        "attributes": vis_attributes(
            item["title"], spec, item.get("description") or ""
        ),
        "references": [],
    }


def verify_svs_queries():
    def swap(q: str) -> str:
        return q.replace("?_tstart", "NOW() - 30 days").replace("?_tend", "NOW()")

    return [
        ("svs-area", swap(Q_SPEND_AREA)),
        ("svs-heat", swap(Q_SPEND_HEAT)),
        ("svs-spend-acct", swap(Q_SPEND_ACCT)),
        ("svs-svc", swap(Q_SVC)),
        ("svs-id-acct", swap(Q_ID_ACCT)),
        ("svs-act", swap(Q_ID_ACT)),
        ("svs-id-heat", swap(Q_ID_HEAT)),
        ("svs-status", swap(Q_STATUS)),
    ]
