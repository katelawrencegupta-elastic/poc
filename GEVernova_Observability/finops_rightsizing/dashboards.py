"""Lens/dashboard builders for FinOps demo extras."""
import json

OPTIONS = json.dumps(
    {
        "hidePanelTitles": False,
        "syncColors": False,
        "syncCursor": True,
        "syncTooltips": False,
        "useMargins": True,
    }
)

ALERTS_TEXT = (
    "## How to read this\n"
    "- **Identified** = open + in_progress (hidden excluded). Live Compute Optimizer "
    "from ged-pgog-apm-usw02-stage (`985408759551`).\n"
    "- **Captured** = done only. Never add identified and captured.\n"
    "- Demo recs are tagged `hidden_reason=seeded_sample`. The infeasible EBS stays hidden and is not in Identified.\n"
    "- The EC2 CPU table is **waste evidence** from live metrics, not a Compute Optimizer rec.\n"
    "- AWS/Usage FilterLogEvents is **quota** (5 TPS per account per region), not dollar rightsizing.\n\n"
    "## Existing FinOps spend alerts (account/MTD unchanged)\n"
    "- `gev-finops-alert-dod-spike` — linked-account day-over-day\n"
    "- `gev-finops-alert-calendar-mtd` — $77k calendar MTD\n"
    "- `gev-finops-alert-service-dod-spike` — SERVICE + account 1.5x vs prior days (new)\n\n"
    "CPU evidence ES|QL: paste `cloud.instance.id` into Discover on `metrics-aws.ec2_metrics-*`."
)


def _ref(data_view_id, layer_id):
    return {
        "id": data_view_id,
        "name": f"indexpattern-datasource-layer-{layer_id}",
        "type": "index-pattern",
    }


def lens_metric(layer_id, col_id, source_field, label, kql, data_view_id, op="sum", currency=False):
    col = {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": op,
        "params": {
            "format": {"id": "number", "params": {"compact": False, "decimals": 2}},
            "emptyAsNull": True,
        },
        "scale": "ratio",
        "sourceField": source_field,
    }
    if currency and op != "unique_count":
        col["params"]["format"] = {
            "id": "currency",
            "params": {"currency": "USD", "decimals": 2},
        }
    if op == "unique_count":
        col["params"] = {"emptyAsNull": True}
    if kql:
        col["filter"] = {"language": "kuery", "query": kql}
    return {
        "description": "",
        "references": [_ref(data_view_id, layer_id)],
        "state": {
            "adHocDataViews": {},
            "datasourceStates": {
                "formBased": {
                    "layers": {
                        layer_id: {
                            "columnOrder": [col_id],
                            "columns": {col_id: col},
                            "incompleteColumns": {},
                        }
                    }
                },
                "textBased": {"layers": {}},
            },
            "filters": [],
            "internalReferences": [],
            "query": {"language": "kuery", "query": ""},
            "visualization": {
                "layerId": layer_id,
                "layerType": "data",
                "metricAccessor": col_id,
            },
        },
        "title": "",
        "type": "lens",
        "visualizationType": "lnsMetric",
    }


def _terms(col_id, field, label, order_col, size=10, direction="desc"):
    return {
        "customLabel": True,
        "dataType": "string",
        "isBucketed": True,
        "label": label,
        "operationType": "terms",
        "params": {
            "size": size,
            "orderBy": {"type": "column", "columnId": order_col},
            "orderDirection": direction,
            "otherBucket": False,
            "missingBucket": False,
            "parentFormat": {"id": "terms"},
        },
        "scale": "ordinal",
        "sourceField": field,
    }


def _sum(col_id, field, label, currency=False):
    fmt = (
        {"id": "currency", "params": {"currency": "USD", "decimals": 2}}
        if currency
        else {"id": "number", "params": {"compact": False, "decimals": 2}}
    )
    return {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "sum",
        "params": {"format": fmt, "emptyAsNull": True},
        "scale": "ratio",
        "sourceField": field,
    }


def _uniq(col_id, field, label):
    return {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "unique_count",
        "params": {"emptyAsNull": True},
        "scale": "ratio",
        "sourceField": field,
    }


def _avg(field, label):
    return {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "average",
        "params": {
            "format": {"id": "number", "params": {"compact": False, "decimals": 2}},
            "emptyAsNull": True,
        },
        "scale": "ratio",
        "sourceField": field,
    }


def _percentile(field, label, pct=95):
    return {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "percentile",
        "params": {
            "percentile": pct,
            "format": {"id": "number", "params": {"compact": False, "decimals": 2}},
        },
        "scale": "ratio",
        "sourceField": field,
    }


def lens_table(layer_id, columns, data_view_id, kql=None, filters=None):
    order = list(columns.keys())
    state_filters = filters or []
    query = {"language": "kuery", "query": kql or ""}
    return {
        "description": "",
        "references": [_ref(data_view_id, layer_id)],
        "state": {
            "adHocDataViews": {},
            "datasourceStates": {
                "formBased": {
                    "layers": {
                        layer_id: {
                            "columnOrder": order,
                            "columns": columns,
                            "incompleteColumns": {},
                        }
                    }
                },
                "textBased": {"layers": {}},
            },
            "filters": state_filters,
            "internalReferences": [],
            "query": query,
            "visualization": {
                "layerId": layer_id,
                "layerType": "data",
                "columns": [{"columnId": c, "isTransposed": False} for c in order],
            },
        },
        "title": "",
        "type": "lens",
        "visualizationType": "lnsDatatable",
    }


def lens_status_pie(data_view_id):
    layer_id = "rs-pie-layer"
    term_id = "rs-pie-status"
    count_id = "rs-pie-count"
    return {
        "description": "",
        "references": [_ref(data_view_id, layer_id)],
        "state": {
            "adHocDataViews": {},
            "datasourceStates": {
                "formBased": {
                    "layers": {
                        layer_id: {
                            "columnOrder": [term_id, count_id],
                            "columns": {
                                term_id: _terms(
                                    term_id, "finops.rightsizing.status", "Status", count_id, 5
                                ),
                                count_id: {
                                    "customLabel": True,
                                    "dataType": "number",
                                    "isBucketed": False,
                                    "label": "Recs",
                                    "operationType": "unique_count",
                                    "params": {"emptyAsNull": True},
                                    "scale": "ratio",
                                    "sourceField": "finops.rightsizing.id",
                                },
                            },
                            "incompleteColumns": {},
                        }
                    }
                },
                "textBased": {"layers": {}},
            },
            "filters": [],
            "internalReferences": [],
            "query": {"language": "kuery", "query": ""},
            "visualization": {
                "shape": "pie",
                "layers": [
                    {
                        "layerId": layer_id,
                        "layerType": "data",
                        "primaryGroups": [term_id],
                        "metrics": [count_id],
                        "numberDisplay": "value",
                        "categoryDisplay": "default",
                        "legendDisplay": "show",
                    }
                ],
            },
        },
        "title": "",
        "type": "lens",
        "visualizationType": "lnsPie",
    }


def _panel(panel_id, title, x, y, w, h, attributes):
    return {
        "type": "lens",
        "title": title,
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_id},
        "panelIndex": panel_id,
        "embeddableConfig": {
            "attributes": attributes,
            "enhancements": {},
            "hidePanelTitles": False,
        },
    }


def _text_panel(panel_id, title, text, x, y, w, h):
    return {
        "type": "markdown",
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_id},
        "panelIndex": panel_id,
        "embeddableConfig": {
            "hide_title": False,
            "title": title,
            "content": text,
            "settings": {"open_links_in_new_tab": True},
        },
    }


def _dash_refs(panels, extra=None):
    refs = list(extra or [])
    for pan in panels:
        attrs = (pan.get("embeddableConfig") or {}).get("attributes") or {}
        for r in attrs.get("references") or []:
            refs.append(
                {
                    "id": r["id"],
                    "name": f"{pan['panelIndex']}:{r['name']}",
                    "type": r["type"],
                }
            )
    return refs


def _saved(title, description, panels, references, time_from="now-14d", extra_attrs=None):
    attrs = {
        "title": title,
        "description": description,
        "panelsJSON": json.dumps(panels),
        "optionsJSON": OPTIONS,
        "timeRestore": True,
        "timeFrom": time_from,
        "timeTo": "now",
        "version": 1,
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps(
                {"filter": [], "query": {"language": "kuery", "query": ""}}
            )
        },
    }
    if extra_attrs:
        attrs.update(extra_attrs)
    return attrs, references


def build_rightsizing_dashboard(rs_id, ec2_id, cw_id):
    identified_kql = 'finops.rightsizing.status : ("open" or "in_progress")'
    captured_kql = "finops.rightsizing.status : done"
    queue_cols = {
        "rs-col-arn": _terms(
            "rs-col-arn", "finops.rightsizing.resource_name", "Resource", "rs-col-savings", 25
        ),
        "rs-col-action": _terms(
            "rs-col-action", "finops.rightsizing.action", "Action", "rs-col-savings"
        ),
        "rs-col-from": _terms(
            "rs-col-from", "finops.rightsizing.current_type", "Current", "rs-col-savings"
        ),
        "rs-col-to": _terms(
            "rs-col-to", "finops.rightsizing.recommended_type", "Recommended", "rs-col-savings"
        ),
        "rs-col-savings": _sum(
            "rs-col-savings",
            "finops.rightsizing.estimated_monthly_savings",
            "Est. monthly USD",
        ),
    }
    queue_filters = [
        {
            "meta": {
                "alias": None,
                "disabled": False,
                "key": "finops.rightsizing.status",
                "negate": False,
                "params": ["open", "in_progress"],
                "type": "phrases",
            },
            "query": {
                "bool": {
                    "minimum_should_match": 1,
                    "should": [
                        {"match_phrase": {"finops.rightsizing.status": "open"}},
                        {"match_phrase": {"finops.rightsizing.status": "in_progress"}},
                    ],
                }
            },
        }
    ]
    cpu_cols = {
        "cpu-name": _terms(
            "cpu-name", "cloud.instance.name", "Instance name", "cpu-avg", 15, "asc"
        ),
        "cpu-id": _terms(
            "cpu-id", "cloud.instance.id", "Instance id", "cpu-avg", 15, "asc"
        ),
        "cpu-acct": _terms(
            "cpu-acct", "cloud.account.id", "Account", "cpu-avg", 10, "asc"
        ),
        "cpu-avg": _avg("aws.ec2.metrics.CPUUtilization.avg", "CPU avg %"),
        "cpu-p95": _percentile("aws.ec2.metrics.CPUUtilization.avg", "CPU p95 %"),
    }
    usage_call_cols = {
        "ufl-acct": _terms("ufl-acct", "cloud.account.id", "Account", "ufl-calls", 10),
        "ufl-calls": _sum("ufl-calls", "aws.usage.metrics.CallCount.sum", "FilterLogEvents calls"),
    }
    usage_res_cols = {
        "ur-svc": _terms("ur-svc", "aws.dimensions.Service", "Service", "ur-cnt", 15),
        "ur-res": _terms("ur-res", "aws.dimensions.Resource", "Resource", "ur-cnt", 15),
        "ur-acct": _terms("ur-acct", "cloud.account.id", "Account", "ur-cnt", 10),
        "ur-cnt": {
            "customLabel": True,
            "dataType": "number",
            "isBucketed": False,
            "label": "ResourceCount max",
            "operationType": "max",
            "params": {"emptyAsNull": True},
            "scale": "ratio",
            "sourceField": "aws.usage.metrics.ResourceCount.max",
        },
    }
    panels = [
        _panel(
            "rs-m-identified",
            "Identified monthly savings (open + in progress)",
            0, 0, 16, 6,
            lens_metric(
                "rs-id-layer", "rs-id-col",
                "finops.rightsizing.estimated_monthly_savings",
                "Identified USD / mo", identified_kql, rs_id,
            ),
        ),
        _panel(
            "rs-m-captured",
            "Captured savings (done only — do not add to identified)",
            16, 0, 16, 6,
            lens_metric(
                "rs-cap-layer", "rs-cap-col",
                "finops.rightsizing.realized_savings",
                "Captured USD / mo", captured_kql, rs_id,
            ),
        ),
        _panel("rs-pie", "Recommendations by status", 32, 0, 16, 6, lens_status_pie(rs_id)),
        _panel(
            "rs-table",
            "Recommended actions (visible queue)",
            0, 6, 48, 12,
            lens_table("rs-table-layer", queue_cols, rs_id, filters=queue_filters),
        ),
        _panel(
            "rs-cpu",
            "Waste evidence: lowest CPU instances (live metrics, not a rec)",
            0, 18, 48, 12,
            lens_table(
                "rs-cpu-layer",
                cpu_cols,
                ec2_id,
                kql="",
            ),
        ),
        _panel(
            "rs-ufl",
            "Usage/quota: FilterLogEvents CallCount (5 TPS per account per region)",
            0, 30, 24, 8,
            lens_table(
                "rs-ufl-layer",
                usage_call_cols,
                cw_id,
                kql='aws.cloudwatch.namespace : "AWS/Usage" and aws.dimensions.Resource : "FilterLogEvents"',
            ),
        ),
        _panel(
            "rs-ures",
            "Usage/quota: ResourceCount (not dollar rightsizing)",
            24, 30, 24, 8,
            lens_table(
                "rs-ures-layer",
                usage_res_cols,
                cw_id,
                kql='aws.cloudwatch.namespace : "AWS/Usage" and aws.dimensions.Type : "Resource"',
            ),
        ),
        _text_panel(
            "rs-notes",
            "How to read this + existing alerts",
            ALERTS_TEXT,
            0, 38, 48, 6,
        ),
    ]
    return _saved(
        "[FinOps] Rightsizing queue",
        "Live Compute Optimizer recs from ged-pgog-apm-usw02-stage (985408759551). "
        "Identified = open + in_progress (hidden excluded). Captured = done. Never add the two. "
        "Low-CPU table is live CloudWatch evidence.",
        panels,
        _dash_refs(panels),
    )


SVS_INTRO = (
    "## How to read spend vs savings\n"
    "**Spend** is Cost Explorer **LINKED_ACCOUNT** unblended — the complete bill for the "
    "time picker (default 30 days). Do **not** add it to the SERVICE table; that is the "
    "same dollars sliced by product and is incomplete when a line has no service.\n\n"
    "**Identified** = open + in progress, **monthly** run-rate. **Captured** = done "
    "(`realized_savings`). **Parked** = hidden, not in identified. Never add identified "
    "and captured. Opportunity ≈ identified ÷ trailing spend. The waffle is estimated $ "
    "by status; captured KPI uses realized.\n\n"
    "Spend charts: stacked area, heatmap, labeled bars (LINKED_ACCOUNT). SERVICE bars "
    "are a slice. Rec charts use the latest fingerprint.\n\n"
    "[Rightsizing queue](#/view/finops-rightsizing-overview) · "
    "[AWS Billing Overview](#/view/finops-aws-billing-overview-unblended) · "
    "[Elastic Cloud billing](#/view/ess_billing-billingdashboard)"
)


def build_spend_vs_savings(rs_id, billing_id, ess_id):
    linked = 'aws.billing.group_definition.key : "LINKED_ACCOUNT"'
    svc = 'aws.billing.group_definition.key : "SERVICE"'
    identified_kql = 'finops.rightsizing.status : ("open" or "in_progress")'
    captured_kql = "finops.rightsizing.status : done"
    parked_kql = "finops.rightsizing.status : hidden"
    ess_kql = 'data_stream.dataset : "ess_billing.billing"'
    unb = "aws.billing.UnblendedCost.amount"
    est = "finops.rightsizing.estimated_monthly_savings"
    realized = "finops.rightsizing.realized_savings"
    ctrl_id = "svs-acct-ctrl"

    spend_acct_cols = {
        "sa-acct": _terms("sa-acct", "cloud.account.id", "Account", "sa-usd", 10),
        "sa-usd": _sum("sa-usd", unb, "Unblended USD", currency=True),
    }
    id_acct_cols = {
        "ia-acct": _terms("ia-acct", "cloud.account.id", "Account", "ia-usd", 10),
        "ia-recs": _uniq("ia-recs", "finops.rightsizing.id", "Open recs"),
        "ia-usd": _sum("ia-usd", est, "Identified USD / mo", currency=True),
    }
    svc_cols = {
        "svc-name": _terms("svc-name", "aws.billing.group_by.SERVICE", "Service", "svc-cost", 12),
        "svc-cost": _sum("svc-cost", unb, "Unblended USD", currency=True),
    }
    ess_cols = {
        "ess-name": _terms("ess-name", "ess.billing.name", "Line item", "ess-ecu", 12),
        "ess-type": _terms("ess-type", "ess.billing.type", "Type", "ess-ecu", 8),
        "ess-ecu": _sum("ess-ecu", "ess.billing.total_ecu", "ECU"),
    }

    panels = [
        _text_panel("svs-md", "How to read this", SVS_INTRO, 0, 0, 48, 6),
        _panel(
            "svs-bill",
            "AWS unblended spend (LINKED_ACCOUNT — complete bill, time picker)",
            0, 6, 12, 6,
            lens_metric(
                "svs-bill-layer", "svs-bill-col", unb, "Trailing spend",
                linked, billing_id, currency=True,
            ),
        ),
        _panel(
            "svs-id",
            "Identified monthly savings (open + in progress)",
            12, 6, 12, 6,
            lens_metric(
                "svs-id-layer", "svs-id-col", est, "Identified / mo",
                identified_kql, rs_id, currency=True,
            ),
        ),
        _panel(
            "svs-cap",
            "Captured monthly savings (done only — do not add to identified)",
            24, 6, 12, 6,
            lens_metric(
                "svs-cap-layer", "svs-cap-col", realized, "Captured / mo",
                captured_kql, rs_id, currency=True,
            ),
        ),
        _panel(
            "svs-park",
            "Parked / hidden (not in identified)",
            36, 6, 12, 6,
            lens_metric(
                "svs-park-layer", "svs-park-col", est, "Parked / mo",
                parked_kql, rs_id, currency=True,
            ),
        ),
        _panel(
            "svs-xy",
            "Daily unblended spend by account (LINKED_ACCOUNT)",
            0, 12, 32, 14,
            lens_xy_stacked(
                "svs-xy-layer", "svs-xy-date", "svs-xy-usd", "svs-xy-acct",
                unb, "cloud.account.id", "Account", linked, billing_id, 8,
            ),
        ),
        _panel(
            "svs-pie",
            "Savings pipeline $ by status (estimated; captured KPI uses realized)",
            32, 12, 16, 14,
            lens_pie(
                "svs-pie-layer", "svs-pie-status", "svs-pie-usd",
                "finops.rightsizing.status", "Status", est, "USD / mo",
                "", rs_id, 5,
            ),
        ),
        _panel(
            "svs-spend-acct",
            "Spend by account (LINKED_ACCOUNT — same grain as the KPI)",
            0, 26, 24, 12,
            lens_table("svs-spend-acct-layer", spend_acct_cols, billing_id, kql=linked),
        ),
        _panel(
            "svs-id-acct",
            "Identified savings by account (open + in progress)",
            24, 26, 24, 12,
            lens_table("svs-id-acct-layer", id_acct_cols, rs_id, kql=identified_kql),
        ),
        _panel(
            "svs-svc",
            "Top AWS services (SERVICE grain — do not add to LINKED_ACCOUNT total)",
            0, 38, 24, 12,
            lens_table("svs-svc-layer", svc_cols, billing_id, kql=svc),
        ),
        _panel(
            "svs-act",
            "Identified savings by action (open + in progress)",
            24, 38, 24, 12,
            lens_bar(
                "svs-act-layer", "svs-act-term", "svs-act-usd",
                "finops.rightsizing.action", "Action", est, "Identified USD / mo",
                identified_kql, rs_id, size=8, horizontal=True, currency=True,
            ),
        ),
        _panel(
            "svs-ess-kpi",
            "Elastic Cloud ECU (time picker)",
            0, 50, 12, 6,
            lens_metric(
                "svs-ess-kpi-layer", "svs-ess-kpi-col",
                "ess.billing.total_ecu", "ECU", ess_kql, ess_id,
            ),
        ),
        _panel(
            "svs-ess",
            "Elastic Cloud line items (deployment_name is often blank — use name)",
            12, 50, 36, 12,
            lens_table("svs-ess-layer", ess_cols, ess_id, kql=ess_kql),
        ),
    ]
    extra_refs = [
        {
            "id": billing_id,
            "name": f"controlGroup_{ctrl_id}:optionsListDataView",
            "type": "index-pattern",
        }
    ]
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
            "panelsJSON": json.dumps(
                {
                    ctrl_id: {
                        "type": "optionsListControl",
                        "order": 0,
                        "grow": False,
                        "width": "medium",
                        "explicitInput": {
                            "id": ctrl_id,
                            "fieldName": "cloud.account.id",
                            "title": "Account ID",
                            "enhancements": {},
                            "selectedOptions": [],
                        },
                    }
                }
            ),
        }
    }
    return _saved(
        "[FinOps] Spend vs savings",
        "Complete AWS bill (LINKED_ACCOUNT unblended) vs identified, captured, and parked monthly savings. SERVICE table is a slice, not a second total. Never add identified and captured. Default last 30 days.",
        panels,
        _dash_refs(panels, extra_refs),
        time_from="now-30d",
        extra_attrs=extra_attrs,
    )


def _date_hist(col_id):
    return {
        "dataType": "date",
        "isBucketed": True,
        "label": "@timestamp",
        "operationType": "date_histogram",
        "params": {"dropPartials": False, "includeEmptyRows": False, "interval": "d"},
        "scale": "interval",
        "sourceField": "@timestamp",
    }


def lens_xy_stacked(layer_id, date_id, metric_id, split_id, metric_field, split_field, split_label, kql, data_view_id, size=10):
    columns = {
        date_id: _date_hist(date_id),
        split_id: _terms(split_id, split_field, split_label, metric_id, size),
        metric_id: _sum(metric_id, metric_field, "Unblended USD", currency=True),
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
                "gridlinesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
                "labelsOrientation": {"x": 0, "yLeft": 0, "yRight": 0},
                "preferredSeriesType": "bar_stacked",
                "layers": [
                    {
                        "layerId": layer_id,
                        "layerType": "data",
                        "seriesType": "bar_stacked",
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
                "tickLabelsVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
            },
        },
        "title": "",
        "type": "lens",
        "visualizationType": "lnsXY",
    }


def lens_bar(
    layer_id,
    term_id,
    metric_id,
    term_field,
    term_label,
    metric_field,
    metric_label,
    kql,
    data_view_id,
    size=8,
    horizontal=True,
    currency=False,
):
    series = "bar_horizontal" if horizontal else "bar"
    columns = {
        term_id: _terms(term_id, term_field, term_label, metric_id, size),
        metric_id: _sum(metric_id, metric_field, metric_label, currency=currency),
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
                            "columnOrder": [term_id, metric_id],
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
                "preferredSeriesType": series,
                "layers": [
                    {
                        "layerId": layer_id,
                        "layerType": "data",
                        "seriesType": series,
                        "xAccessor": term_id,
                        "accessors": [metric_id],
                    }
                ],
                "legend": {"isVisible": False, "position": "right"},
                "valueLabels": "show",
                "yLeftScale": "linear",
                "fittingFunction": "None",
            },
        },
        "title": "",
        "type": "lens",
        "visualizationType": "lnsXY",
    }


def lens_pie(layer_id, term_id, metric_id, term_field, term_label, metric_field, metric_label, kql, data_view_id, size=8):
    return {
        "description": "",
        "references": [_ref(data_view_id, layer_id)],
        "state": {
            "adHocDataViews": {},
            "datasourceStates": {
                "formBased": {
                    "layers": {
                        layer_id: {
                            "columnOrder": [term_id, metric_id],
                            "columns": {
                                term_id: _terms(term_id, term_field, term_label, metric_id, size),
                                metric_id: _sum(metric_id, metric_field, metric_label),
                            },
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
                "shape": "pie",
                "layers": [
                    {
                        "layerId": layer_id,
                        "layerType": "data",
                        "primaryGroups": [term_id],
                        "metrics": [metric_id],
                        "numberDisplay": "value",
                        "categoryDisplay": "default",
                        "legendDisplay": "show",
                    }
                ],
            },
        },
        "title": "",
        "type": "lens",
        "visualizationType": "lnsPie",
    }


BILLING_INTRO = (
    "## Cost Explorer unblended spend\n"
    "Each Cost Explorer grouping is the **same dollars sliced differently**. "
    "Do **not** add SERVICE + LINKED_ACCOUNT + INSTANCE_TYPE + AZ totals together.\n\n"
    "- **SERVICE / account** panels use `group_definition.key: SERVICE` — this is the total to quote.\n"
    "- **Linked account** uses `LINKED_ACCOUNT`.\n"
    "- **AZ** uses `AZ` (regional/zonal grain).\n"
    "- **Instance type** uses `INSTANCE_TYPE` (compute grain only; many line items have no type).\n"
    "- Amortized includes Savings Plans / RI; unblended is cash-like.\n"
    "- Use the **Account ID** control and the time picker (default last 30 days).\n\n"
    "[Spend vs savings](/s/finops/app/dashboards#/view/finops-spend-vs-savings) · "
    "[Rightsizing queue](/s/finops/app/dashboards#/view/finops-rightsizing-overview)"
)


def build_billing_overview(billing_id):
    ds = 'data_stream.dataset : "aws.billing"'
    svc = ds + ' and aws.billing.group_definition.key : "SERVICE"'
    linked = ds + ' and aws.billing.group_definition.key : "LINKED_ACCOUNT"'
    itype = (
        ds
        + ' and aws.billing.group_definition.key : "INSTANCE_TYPE"'
        + " and aws.billing.group_by.INSTANCE_TYPE : *"
    )
    az = ds + ' and aws.billing.group_definition.key : "AZ"'
    unb = "aws.billing.UnblendedCost.amount"
    amz = "aws.billing.AmortizedCost.amount"
    ctrl_id = "bill-acct-ctrl"
    panels = [
        _text_panel("bill-md", "How to read Cost Explorer", BILLING_INTRO, 0, 0, 48, 6),
        _panel(
            "bill-unb",
            "Unblended (SERVICE grouping)",
            0, 6, 16, 6,
            lens_metric("bill-unb-layer", "bill-unb-col", unb, "Unblended USD", svc, billing_id),
        ),
        _panel(
            "bill-amz",
            "Amortized (SERVICE grouping — includes SP/RI)",
            16, 6, 16, 6,
            lens_metric("bill-amz-layer", "bill-amz-col", amz, "Amortized USD", svc, billing_id),
        ),
        _panel(
            "bill-accts",
            "Accounts with SERVICE spend",
            32, 6, 16, 6,
            lens_metric(
                "bill-accts-layer", "bill-accts-col",
                "cloud.account.id", "Accounts", svc, billing_id, op="unique_count",
            ),
        ),
        _panel(
            "bill-xy",
            "Daily unblended by service (stacked)",
            0, 12, 32, 14,
            lens_xy_stacked(
                "bill-xy-layer", "bill-xy-date", "bill-xy-usd", "bill-xy-svc",
                unb, "aws.billing.group_by.SERVICE", "Service", svc, billing_id, 10,
            ),
        ),
        _panel(
            "bill-acct-tbl",
            "Unblended by account (SERVICE grouping)",
            32, 12, 16, 14,
            lens_table(
                "bill-acct-layer",
                {
                    "ba-acct": _terms("ba-acct", "cloud.account.id", "Account", "ba-usd", 15),
                    "ba-usd": _sum("ba-usd", unb, "Unblended USD"),
                },
                billing_id,
                kql=svc,
            ),
        ),
        _panel(
            "bill-svc-tbl",
            "Top services × account (SERVICE grouping)",
            0, 26, 28, 12,
            lens_table(
                "bill-svc-layer",
                {
                    "bs-svc": _terms("bs-svc", "aws.billing.group_by.SERVICE", "Service", "bs-usd", 15),
                    "bs-acct": _terms("bs-acct", "cloud.account.id", "Account", "bs-usd", 10),
                    "bs-usd": _sum("bs-usd", unb, "Unblended USD"),
                },
                billing_id,
                kql=svc,
            ),
        ),
        _panel(
            "bill-pie",
            "Share by service",
            28, 26, 20, 12,
            lens_pie(
                "bill-pie-layer", "bill-pie-svc", "bill-pie-usd",
                "aws.billing.group_by.SERVICE", "Service", unb, "Unblended USD",
                svc, billing_id, 8,
            ),
        ),
        _panel(
            "bill-itype",
            "Instance type (INSTANCE_TYPE — do not add to SERVICE total)",
            0, 38, 16, 12,
            lens_table(
                "bill-itype-layer",
                {
                    "bi-type": _terms("bi-type", "aws.billing.group_by.INSTANCE_TYPE", "Instance type", "bi-usd", 15),
                    "bi-usd": _sum("bi-usd", unb, "Unblended USD"),
                },
                billing_id,
                kql=itype,
            ),
        ),
        _panel(
            "bill-linked",
            "Linked account (LINKED_ACCOUNT — do not add to SERVICE total)",
            16, 38, 16, 12,
            lens_table(
                "bill-linked-layer",
                {
                    "bl-acct": _terms("bl-acct", "aws.billing.group_by.LINKED_ACCOUNT", "Linked account", "bl-usd", 15),
                    "bl-usd": _sum("bl-usd", unb, "Unblended USD"),
                },
                billing_id,
                kql=linked,
            ),
        ),
        _panel(
            "bill-az",
            "Availability Zone (AZ — do not add to SERVICE total)",
            32, 38, 16, 12,
            lens_table(
                "bill-az-layer",
                {
                    "bz-az": _terms("bz-az", "aws.billing.group_by.AZ", "AZ", "bz-usd", 15),
                    "bz-usd": _sum("bz-usd", unb, "Unblended USD"),
                },
                billing_id,
                kql=az,
            ),
        ),
    ]
    extra_refs = [
        {
            "id": billing_id,
            "name": f"controlGroup_{ctrl_id}:optionsListDataView",
            "type": "index-pattern",
        }
    ]
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
            "panelsJSON": json.dumps(
                {
                    ctrl_id: {
                        "type": "optionsListControl",
                        "order": 0,
                        "grow": False,
                        "width": "medium",
                        "explicitInput": {
                            "id": ctrl_id,
                            "dataViewId": billing_id,
                            "exclude": False,
                            "existsSelected": False,
                            "fieldName": "cloud.account.id",
                            "searchTechnique": "wildcard",
                            "selectedOptions": [],
                            "singleSelect": False,
                            "sort": {"by": "_count", "direction": "desc"},
                            "title": "Account ID",
                            "enhancements": {},
                        },
                    }
                }
            ),
        }
    }
    return _saved(
        "[FinOps] AWS Billing Overview (Cost Explorer)",
        "Cost Explorer unblended and amortized spend. SERVICE, LINKED_ACCOUNT, INSTANCE_TYPE, and AZ are different grains of the same dollars — never add those totals together. Default Last 30 days. Filter by account ID in the control.",
        panels,
        _dash_refs(panels, extra_refs),
        time_from="now-30d",
        extra_attrs=extra_attrs,
    )
