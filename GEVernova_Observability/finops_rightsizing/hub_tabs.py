"""Horizontal FinOps dashboard tabs. Hub is meridian-finops-llm-observability-dynamic-aws.

Sectioned dashboards (the hub) must store the links panel *inside* a section with
dashboard saved-object references. A top-level links sibling is dropped on UI save.
"""

HUB_ID = "meridian-finops-llm-observability-dynamic-aws"
TAB_PANEL_ID = "finops-hub-tabs"
TAB_HEIGHT = 5

# (label, dashboard id, stable link uuid)
FINOPS_TABS = [
    ("Overview", HUB_ID, "0a8f9c82-35e6-46e3-bfd4-73b21bed1183"),
    ("AWS Billing", "finops-aws-billing-overview-unblended", "c78907ba-259e-4520-8a9d-cf2953a98721"),
    ("Spend vs savings", "finops-spend-vs-savings", "22749f3c-44bb-46cd-b732-07db23a6349d"),
    ("Rightsizing", "finops-rightsizing-overview", "bae81827-641b-44b4-b2da-c7a52c9dc995"),
    ("Inference tokens", "ffd600e5-2862-4bf4-8556-2ef8872c5ba5", "d9ed8f78-9e7b-47a3-8243-f9c6c69b285e"),
    ("ESS Billing", "4e3d2263-42f4-43ce-bd12-dd7863f18804", "570478ad-aab4-4a52-894d-87af8fc299e0"),
    ("ESS Credits", "952b4e0a-1a55-4794-8c57-d26b8c6d9086", "a9480eae-91c6-4371-9456-f2eaac263dd3"),
]

ALL_DASHBOARD_IDS = [dest for _, dest, _ in FINOPS_TABS]


def _link_ref_name(uid: str) -> str:
    return f"link_{uid}_dashboard"


def tabs_panel():
    """Dashboards API shape (destination id)."""
    return {
        "id": TAB_PANEL_ID,
        "type": "links",
        "grid": {"x": 0, "y": 0, "w": 48, "h": TAB_HEIGHT},
        "config": {
            "layout": "horizontal",
            "hide_title": False,
            "title": "FinOps dashboards",
            "links": [
                {
                    "label": label,
                    "type": "dashboardLink",
                    "destination": dest,
                    "options": {
                        "open_in_new_tab": False,
                        "use_time_range": True,
                        "use_filters": True,
                    },
                }
                for label, dest, _uid in FINOPS_TABS
            ],
        },
    }


def tabs_so_panel(section_id: str | None = None) -> tuple[dict, list]:
    """Saved-object shape the Kibana UI keeps: destinationRefName + dashboard refs."""
    links = []
    refs = []
    for label, dest, uid in FINOPS_TABS:
        ref_name = _link_ref_name(uid)
        links.append(
            {
                "id": uid,
                "label": label,
                "type": "dashboardLink",
                "destinationRefName": ref_name,
                "options": {
                    "open_in_new_tab": False,
                    "use_time_range": True,
                    "use_filters": True,
                },
            }
        )
        refs.append(
            {
                "name": f"{TAB_PANEL_ID}:{ref_name}",
                "type": "dashboard",
                "id": dest,
            }
        )
    grid = {"x": 0, "y": 0, "w": 48, "h": TAB_HEIGHT, "i": TAB_PANEL_ID}
    if section_id:
        grid["sectionId"] = section_id
    panel = {
        "type": "links",
        "panelIndex": TAB_PANEL_ID,
        "gridData": grid,
        "embeddableConfig": {
            "title": "FinOps dashboards",
            "hide_title": False,
            "layout": "horizontal",
            "links": links,
        },
    }
    return panel, refs


def _first_section_id(attrs: dict) -> str | None:
    sections = attrs.get("sections") or []
    if isinstance(sections, str):
        import json

        sections = json.loads(sections)
    if not sections:
        return None
    first = sections[0]
    return (first.get("gridData") or {}).get("i") or first.get("id")


def inject_tabs_saved_object(attrs: dict, references: list) -> tuple[dict, list]:
    """Put tabs in the first section (or at y=0). Idempotent. Returns attrs, refs."""
    import json

    panels = json.loads(attrs.get("panelsJSON") or "[]")
    already = any(p.get("panelIndex") == TAB_PANEL_ID or p.get("id") == TAB_PANEL_ID for p in panels)
    section_id = _first_section_id(attrs)
    panels = [
        p
        for p in panels
        if p.get("panelIndex") != TAB_PANEL_ID and p.get("id") != TAB_PANEL_ID
    ]
    if not already:
        for p in panels:
            g = p.get("gridData") or {}
            if section_id and g.get("sectionId") != section_id:
                continue
            if "y" in g:
                g["y"] = int(g.get("y") or 0) + TAB_HEIGHT
                p["gridData"] = g
    panel, tab_refs = tabs_so_panel(section_id)
    panels.insert(0, panel)
    attrs = dict(attrs)
    attrs["panelsJSON"] = json.dumps(panels)
    keep = [
        r
        for r in (references or [])
        if not str(r.get("name") or "").startswith(f"{TAB_PANEL_ID}:")
    ]
    return attrs, keep + tab_refs
