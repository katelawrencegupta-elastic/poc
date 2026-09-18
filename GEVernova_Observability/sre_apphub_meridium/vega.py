"""Vega-Lite specs for AppHub → Meridium latency (ES|QL, dashboard time picker)."""
from __future__ import annotations

import json

DEST_SHORT = """EVAL dest_short = CASE(
     `attributes.span.destination.service.resource` LIKE "*classic-stage*", "classic-stage",
     `attributes.span.destination.service.resource` LIKE "*classic-dev*", "classic-dev",
     `attributes.span.destination.service.resource` LIKE "*beta-stage*", "classic-beta",
     `attributes.span.destination.service.resource` LIKE "*meridium-ui*", "meridium-ui",
     `attributes.span.destination.service.resource`
   )"""

HOP = """FROM metrics-service_destination.1m.otel-default
| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend
| WHERE TO_LOWER(`resource.attributes.service.name`) LIKE "*apphub*"
| WHERE TO_LOWER(`attributes.span.destination.service.resource`) LIKE "*classic*"
   OR TO_LOWER(`attributes.span.destination.service.resource`) LIKE "*meridium*"
"""

Q_TREND = f"""{HOP}| {DEST_SHORT}
| STATS calls = SUM(`metrics.span.destination.service.response_time.count`),
        sum_us = SUM(`metrics.span.destination.service.response_time.sum.us`),
        fail_calls = SUM(CASE(`attributes.event.outcome` == "failure", `metrics.span.destination.service.response_time.count`, 0))
    BY t = BUCKET(@timestamp, 60, ?_tstart, ?_tend), dest_short
| EVAL avg_ms = ROUND(sum_us / calls / 1000.0, 1),
       fail_pct = ROUND(100.0 * fail_calls / calls, 2)
| WHERE calls > 0
| SORT t ASC
"""

Q_BUBBLE = f"""{HOP}| {DEST_SHORT}
| STATS calls = SUM(`metrics.span.destination.service.response_time.count`),
        sum_us = SUM(`metrics.span.destination.service.response_time.sum.us`),
        fail_calls = SUM(CASE(`attributes.event.outcome` == "failure", `metrics.span.destination.service.response_time.count`, 0))
    BY dest_short
| EVAL avg_ms = ROUND(sum_us / calls / 1000.0, 1),
       fail_pct = ROUND(100.0 * fail_calls / calls, 2)
| WHERE calls > 0
| SORT calls DESC
"""

Q_HEAT = Q_TREND

HOST_SEL = {
    "name": "hostSel",
    "select": {"type": "point", "fields": ["dest_short"]},
    "bind": "legend",
}

TOOLTIP_TREND = [
    {"field": "dest_short", "type": "nominal", "title": "Host"},
    {"field": "t", "type": "temporal", "title": "Time"},
    {"field": "avg_ms", "type": "quantitative", "title": "Avg ms"},
    {"field": "fail_pct", "type": "quantitative", "title": "Fail %"},
    {"field": "calls", "type": "quantitative", "title": "Calls"},
]


def _esql_url(query: str) -> dict:
    return {
        "%type%": "esql",
        "%context%": True,
        "%timefield%": "@timestamp",
        "query": query.strip(),
    }


def spec_trend() -> dict:
    """Latency + fail% vs time. Bucket count follows the dashboard time picker."""
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Avg destination latency (ms) and failure rate (%) by host. Time buckets follow the dashboard picker (~60 buckets). Click a legend item to isolate a host. Dashed line is the 500 ms P2 threshold.",
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(Q_TREND)},
        "params": [HOST_SEL],
        "vconcat": [
            {
                "height": 200,
                "layer": [
                    {
                        "mark": {"type": "line", "point": True, "strokeWidth": 2},
                        "encoding": {
                            "x": {
                                "field": "t",
                                "type": "temporal",
                                "title": None,
                                "axis": {"grid": True},
                            },
                            "y": {
                                "field": "avg_ms",
                                "type": "quantitative",
                                "title": "Avg latency (ms)",
                            },
                            "color": {
                                "field": "dest_short",
                                "type": "nominal",
                                "title": "Host",
                            },
                            "opacity": {
                                "condition": {"param": "hostSel", "value": 1},
                                "value": 0.15,
                            },
                            "tooltip": TOOLTIP_TREND,
                        },
                    },
                    {
                        "mark": {
                            "type": "rule",
                            "strokeDash": [6, 4],
                            "color": "#BD271E",
                            "size": 1.5,
                        },
                        "data": {"values": [{}]},
                        "encoding": {
                            "y": {"datum": 500, "type": "quantitative"},
                        },
                    },
                ],
            },
            {
                "height": 120,
                "layer": [
                    {
                        "mark": {
                            "type": "line",
                            "point": True,
                            "strokeDash": [3, 2],
                            "strokeWidth": 2,
                        },
                        "encoding": {
                            "x": {
                                "field": "t",
                                "type": "temporal",
                                "title": "Time",
                            },
                            "y": {
                                "field": "fail_pct",
                                "type": "quantitative",
                                "title": "Fail %",
                            },
                            "color": {
                                "field": "dest_short",
                                "type": "nominal",
                                "legend": None,
                            },
                            "opacity": {
                                "condition": {"param": "hostSel", "value": 1},
                                "value": 0.15,
                            },
                            "tooltip": TOOLTIP_TREND,
                        },
                    },
                    {
                        "mark": {
                            "type": "rule",
                            "strokeDash": [6, 4],
                            "color": "#BD271E",
                            "size": 1.5,
                        },
                        "data": {"values": [{}]},
                        "encoding": {
                            "y": {"datum": 5, "type": "quantitative"},
                        },
                    },
                ],
            },
        ],
        "resolve": {"scale": {"x": "shared", "color": "shared"}},
    }


def spec_bubble() -> dict:
    """Volume vs latency vs error rate for the selected time range."""
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Each bubble is a Classic/Meridium host in the current time range. X is average latency (ms), Y is failure rate (%), size is call volume. Hover for numbers. Vertical line is 500 ms; horizontal is 5% failures.",
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(Q_BUBBLE)},
        "layer": [
            {
                "mark": {"type": "circle", "opacity": 0.75, "stroke": "#1a1a1a"},
                "encoding": {
                    "x": {
                        "field": "avg_ms",
                        "type": "quantitative",
                        "title": "Avg latency (ms)",
                    },
                    "y": {
                        "field": "fail_pct",
                        "type": "quantitative",
                        "title": "Fail %",
                    },
                    "size": {
                        "field": "calls",
                        "type": "quantitative",
                        "title": "Calls",
                        "scale": {"range": [80, 1200]},
                    },
                    "color": {
                        "field": "dest_short",
                        "type": "nominal",
                        "title": "Host",
                    },
                    "tooltip": [
                        {"field": "dest_short", "type": "nominal", "title": "Host"},
                        {"field": "calls", "type": "quantitative", "title": "Calls"},
                        {"field": "avg_ms", "type": "quantitative", "title": "Avg ms"},
                        {"field": "fail_pct", "type": "quantitative", "title": "Fail %"},
                    ],
                },
            },
            {
                "mark": {"type": "rule", "strokeDash": [6, 4], "color": "#BD271E"},
                "data": {"values": [{}]},
                "encoding": {"x": {"datum": 500, "type": "quantitative"}},
            },
            {
                "mark": {"type": "rule", "strokeDash": [6, 4], "color": "#BD271E"},
                "data": {"values": [{}]},
                "encoding": {"y": {"datum": 5, "type": "quantitative"}},
            },
        ],
    }


def spec_heatmap() -> dict:
    """Host × time heatmap of avg latency; buckets follow the time picker."""
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Average destination latency (ms) by host and time. Darker red is slower. Buckets follow the dashboard time picker.",
        "autosize": {"type": "fit", "contains": "padding"},
        "data": {"url": _esql_url(Q_HEAT)},
        "mark": {"type": "rect", "tooltip": True},
        "encoding": {
            "x": {
                "field": "t",
                "type": "temporal",
                "title": "Time",
            },
            "y": {
                "field": "dest_short",
                "type": "nominal",
                "title": "Host",
                "sort": ["classic-stage", "classic-dev", "classic-beta", "meridium-ui"],
            },
            "color": {
                "field": "avg_ms",
                "type": "quantitative",
                "title": "Avg ms",
                "scale": {
                    "scheme": "yelloworangered",
                    "domainMin": 0,
                },
                "legend": {"orient": "right"},
            },
            "tooltip": TOOLTIP_TREND,
        },
        "height": 160,
    }


VEGA_VIS = [
    {
        "id": "gev-sre-apphub-meridium-vega-trend",
        "title": "[SRE] AppHub → Meridium latency & errors over time",
        "spec": spec_trend,
        "panel_id": "am-vega-trend",
        "panel_title": "Latency & errors over time (follows time picker)",
        "grid": (0, 12, 48, 16),
    },
    {
        "id": "gev-sre-apphub-meridium-vega-bubble",
        "title": "[SRE] AppHub → Meridium volume vs latency vs errors",
        "spec": spec_bubble,
        "panel_id": "am-vega-bubble",
        "panel_title": "Volume vs latency vs errors",
        "grid": (0, 28, 24, 14),
    },
    {
        "id": "gev-sre-apphub-meridium-vega-heat",
        "title": "[SRE] AppHub → Meridium latency heatmap",
        "spec": spec_heatmap,
        "panel_id": "am-vega-heat",
        "panel_title": "Latency heatmap by host",
        "grid": (24, 28, 24, 14),
    },
]


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


def vis_so_payload(item: dict) -> dict:
    spec = item["spec"]() if callable(item["spec"]) else item["spec"]
    return {
        "attributes": vis_attributes(
            item["title"],
            spec,
            "AppHub → Meridium. ES|QL buckets follow the dashboard time picker.",
        ),
        "references": [],
    }


def dash_vis_panel(item: dict) -> dict:
    x, y, w, h = item["grid"]
    return {
        "id": item["panel_id"],
        "type": "vis",
        "grid": {"x": x, "y": y, "w": w, "h": h},
        "config": {
            "ref_id": item["id"],
            "title": item["panel_title"],
            "hide_title": False,
        },
    }


def inline_chart_panels() -> list[dict]:
    """Heatmap + host bars live inline so the dashboard does not depend on saved vis IDs."""
    return [
        {
            "id": "am-heat",
            "type": "vis",
            "grid": {"x": 0, "y": 24, "w": 24, "h": 14},
            "config": {
                "type": "heatmap",
                "title": "Latency heatmap by host",
                "hide_title": False,
                "data_source": {"type": "esql", "query": Q_TREND.strip()},
                "x": {"column": "t", "label": "Time"},
                "y": {"column": "dest_short", "label": "Host"},
                "metric": {"column": "avg_ms", "label": "Avg ms"},
            },
        },
        {
            "id": "am-host-bar",
            "type": "vis",
            "grid": {"x": 24, "y": 24, "w": 24, "h": 14},
            "config": {
                "type": "xy",
                "title": "Latency vs errors by host",
                "hide_title": False,
                "layers": [
                    {
                        "type": "bar",
                        "data_source": {"type": "esql", "query": Q_BUBBLE.strip()},
                        "x": {"column": "dest_short", "label": "Host"},
                        "y": [
                            {"column": "avg_ms", "label": "Avg ms", "axis": "y"},
                            {"column": "fail_pct", "label": "Fail %", "axis": "y2"},
                        ],
                    }
                ],
            },
        },
    ]


TABLE_GRIDS = {
    "am-md": {"x": 0, "y": 0, "w": 48, "h": 6},
    "am-kpi-calls": {"x": 0, "y": 6, "w": 8, "h": 6},
    "am-kpi-avg": {"x": 8, "y": 6, "w": 8, "h": 6},
    "am-kpi-p95": {"x": 16, "y": 6, "w": 8, "h": 6},
    "am-kpi-failpct": {"x": 24, "y": 6, "w": 8, "h": 6},
    "am-kpi-fails": {"x": 32, "y": 6, "w": 8, "h": 6},
    "am-kpi-to": {"x": 40, "y": 6, "w": 8, "h": 6},
    "am-xy-avg": {"x": 0, "y": 12, "w": 24, "h": 12},
    "am-xy-fail": {"x": 24, "y": 12, "w": 24, "h": 12},
    "am-tbl-dest": {"x": 0, "y": 38, "w": 48, "h": 12},
    "am-tbl-path": {"x": 0, "y": 50, "w": 48, "h": 14},
    "am-tbl-to": {"x": 0, "y": 64, "w": 28, "h": 12},
    "am-tbl-status": {"x": 28, "y": 64, "w": 20, "h": 12},
}


def verify_vega_queries():
    def swap(q: str) -> str:
        return (
            q.replace("?_tstart", "NOW() - 3 days").replace("?_tend", "NOW()")
        )

    return [
        ("vega-trend", swap(Q_TREND)),
        ("vega-bubble", swap(Q_BUBBLE)),
    ]
