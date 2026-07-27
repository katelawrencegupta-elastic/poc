"""Kibana Dashboards / Rules / Workflows API helpers (Elastic Serverless / 9.4+)."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .elastic import DEFAULT_ELASTIC_URL, ElasticConfig

DEFAULT_KIBANA_URL = (
    "https://klggehpoc-eb6d47.kb.us-central1.gcp.elastic.cloud"
)

OVERVIEW_DASHBOARD_ID = "geh-fleet-overview"
DETAIL_DASHBOARD_ID = "geh-hospital-detail"

PCD_COLLIMATION_WORKFLOW_ID = "pcd-collimation-fail-critical-summary"
PCD_COLLIMATION_RULE_TAG = "geh:pcd-collimation-fail-critical"
CT_HYBRID_SEARCH_WORKFLOW_ID = "ct-hybrid-search-api"

DASHBOARD_DEFINITIONS_DIR = (
    Path(__file__).resolve().parent.parent / "kibana" / "dashboards"
)
WORKFLOW_DEFINITIONS_DIR = (
    Path(__file__).resolve().parent.parent / "kibana" / "workflows"
)
RULE_DEFINITIONS_DIR = (
    Path(__file__).resolve().parent.parent / "kibana" / "rules"
)


@dataclass
class KibanaConfig:
    url: str = DEFAULT_KIBANA_URL
    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    verify_certs: bool = True
    timeout_s: float = 120.0

    @classmethod
    def from_env(
        cls,
        *,
        url: str | None = None,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify_certs: bool | None = None,
        elastic: ElasticConfig | None = None,
    ) -> KibanaConfig:
        es = elastic or ElasticConfig.from_env()
        verify = verify_certs
        if verify is None:
            verify = es.verify_certs
        derived = None
        if ".es." in es.url:
            derived = es.url.replace(".es.", ".kb.").rstrip("/").removesuffix(":443")
        return cls(
            url=(
                url
                or os.environ.get("KIBANA_URL")
                or derived
                or DEFAULT_KIBANA_URL
            ).rstrip("/"),
            api_key=api_key or es.api_key or os.environ.get("ELASTIC_API_KEY"),
            username=username or es.username or os.environ.get("ELASTIC_USER"),
            password=(
                password
                if password is not None
                else (es.password or os.environ.get("ELASTIC_PASSWORD"))
            ),
            verify_certs=verify,
        )

    def auth_headers(self) -> dict[str, str]:
        # Reuse ElasticConfig auth formatting without re-validating URL.
        return ElasticConfig(
            url=DEFAULT_ELASTIC_URL,
            api_key=self.api_key,
            username=self.username,
            password=self.password,
            verify_certs=self.verify_certs,
        ).auth_headers()


def _ssl_context(verify: bool) -> ssl.SSLContext | None:
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def kibana_request(
    cfg: KibanaConfig,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{cfg.url}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "kbn-xsrf": "true",
        "x-elastic-internal-origin": "Kibana",
        **cfg.auth_headers(),
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            req, timeout=cfg.timeout_s, context=_ssl_context(cfg.verify_certs)
        ) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Kibana {method} {path} -> HTTP {exc.code}: {detail}"
        ) from exc


def dashboard_url(cfg: KibanaConfig, dashboard_id: str) -> str:
    return f"{cfg.url}/app/dashboards#/view/{dashboard_id}"


def rule_url(cfg: KibanaConfig, rule_id: str) -> str:
    return f"{cfg.url}/app/management/insightsAndAlerting/triggersActions/rule/{rule_id}"


def workflow_url(cfg: KibanaConfig, workflow_id: str) -> str:
    return f"{cfg.url}/app/workflows/{workflow_id}"


def load_dashboard_definition(name: str, *, directory: Path | None = None) -> dict[str, Any]:
    root = directory or DASHBOARD_DEFINITIONS_DIR
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(f"Dashboard definition not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_dashboard(
    cfg: KibanaConfig,
    dashboard_id: str,
    definition: dict[str, Any],
) -> dict[str, Any]:
    """Create or replace a dashboard via PUT /api/dashboards/{id}."""
    return kibana_request(
        cfg, "PUT", f"/api/dashboards/{dashboard_id}", definition
    )


def deploy_geh_dashboards(
    cfg: KibanaConfig,
    *,
    directory: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Upsert the GEH fleet overview + hospital detail dashboards."""
    root = directory or DASHBOARD_DEFINITIONS_DIR
    results: dict[str, dict[str, Any]] = {}
    for dashboard_id, filename in (
        (DETAIL_DASHBOARD_ID, "geh-hospital-detail.json"),
        (OVERVIEW_DASHBOARD_ID, "geh-fleet-overview.json"),
    ):
        definition = load_dashboard_definition(filename, directory=root)
        results[dashboard_id] = upsert_dashboard(cfg, dashboard_id, definition)
    return results


def load_workflow_yaml(
    name: str,
    *,
    directory: Path | None = None,
) -> str:
    root = directory or WORKFLOW_DEFINITIONS_DIR
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(f"Workflow definition not found: {path}")
    return path.read_text(encoding="utf-8")


def upsert_workflow(
    cfg: KibanaConfig,
    workflow_id: str,
    yaml_text: str,
) -> dict[str, Any]:
    """Create or replace a workflow by id via /api/workflows/workflow."""
    try:
        kibana_request(
            cfg,
            "PUT",
            f"/api/workflows/workflow/{workflow_id}",
            {"yaml": yaml_text},
        )
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
        kibana_request(
            cfg,
            "POST",
            "/api/workflows/workflow",
            {"id": workflow_id, "yaml": yaml_text},
        )
    return kibana_request(cfg, "GET", f"/api/workflows/workflow/{workflow_id}")


def load_rule_definition(
    name: str,
    *,
    directory: Path | None = None,
) -> dict[str, Any]:
    root = directory or RULE_DEFINITIONS_DIR
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(f"Rule definition not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def find_rules_by_tag(cfg: KibanaConfig, tag: str) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"per_page": 100, "filter": f'alert.attributes.tags:"{tag}"'})
    payload = kibana_request(cfg, "GET", f"/api/alerting/rules/_find?{q}")
    return list(payload.get("data") or [])


def upsert_alerting_rule(
    cfg: KibanaConfig,
    definition: dict[str, Any],
    *,
    match_tag: str | None = None,
) -> dict[str, Any]:
    """Create or update an Elasticsearch query alerting rule.

    When ``match_tag`` is set, update the first existing rule with that tag;
    otherwise create a new rule.
    """
    existing_id: str | None = None
    tag = match_tag
    if tag is None:
        tags = definition.get("tags") or []
        tag = next((t for t in tags if str(t).startswith("geh:")), None)
    if tag:
        matches = find_rules_by_tag(cfg, tag)
        if matches:
            existing_id = matches[0]["id"]

    body = {
        "name": definition["name"],
        "tags": definition.get("tags") or [],
        "schedule": definition.get("schedule") or {"interval": "1m"},
        "params": definition["params"],
        "actions": [
            {
                "id": a["id"],
                "params": a.get("params") or {},
                **({"group": a["group"]} if a.get("group") else {}),
                **({"uuid": a["uuid"]} if a.get("uuid") else {}),
                **({"frequency": a["frequency"]} if a.get("frequency") else {}),
            }
            for a in (definition.get("actions") or [])
        ],
        "alert_delay": definition.get("alert_delay") or {"active": 1},
    }
    if existing_id:
        update_body = {
            "name": definition["name"],
            "tags": definition.get("tags") or [],
            "schedule": definition.get("schedule") or {"interval": "1m"},
            "params": definition["params"],
            "actions": definition.get("actions") or [],
            "alert_delay": definition.get("alert_delay") or {"active": 1},
        }
        updated = kibana_request(
            cfg, "PUT", f"/api/alerting/rule/{existing_id}", update_body
        )
        if definition.get("enabled") is True and not updated.get("enabled"):
            kibana_request(
                cfg, "POST", f"/api/alerting/rule/{existing_id}/_enable"
            )
            updated["enabled"] = True
        elif definition.get("enabled") is False and updated.get("enabled"):
            kibana_request(
                cfg, "POST", f"/api/alerting/rule/{existing_id}/_disable"
            )
            updated["enabled"] = False
        return updated

    create_body = {
        **body,
        "rule_type_id": definition["rule_type_id"],
        "consumer": definition.get("consumer") or "alerts",
        "enabled": definition.get("enabled", True),
    }
    return kibana_request(cfg, "POST", "/api/alerting/rule", create_body)


def deploy_pcd_collimation_rule_and_workflow(
    cfg: KibanaConfig,
    *,
    workflow_directory: Path | None = None,
    rule_directory: Path | None = None,
) -> dict[str, Any]:
    """Upsert the PCD FAIL + Critical correlation workflow and alerting rule."""
    workflow_yaml = load_workflow_yaml(
        f"{PCD_COLLIMATION_WORKFLOW_ID}.yaml",
        directory=workflow_directory,
    )
    workflow = upsert_workflow(cfg, PCD_COLLIMATION_WORKFLOW_ID, workflow_yaml)
    rule_def = load_rule_definition(
        "pcd-collimation-fail-critical.json",
        directory=rule_directory,
    )
    rule = upsert_alerting_rule(
        cfg, rule_def, match_tag=PCD_COLLIMATION_RULE_TAG
    )
    return {
        "workflow": workflow,
        "rule": rule,
        "workflow_id": PCD_COLLIMATION_WORKFLOW_ID,
        "rule_id": rule.get("id"),
        "workflow_url": workflow_url(cfg, PCD_COLLIMATION_WORKFLOW_ID),
        "rule_url": rule_url(cfg, rule["id"]) if rule.get("id") else None,
    }


def deploy_ct_hybrid_search_workflow(
    cfg: KibanaConfig,
    *,
    workflow_directory: Path | None = None,
) -> dict[str, Any]:
    """Upsert the CT hybrid search manual/API workflow."""
    workflow_yaml = load_workflow_yaml(
        f"{CT_HYBRID_SEARCH_WORKFLOW_ID}.yaml",
        directory=workflow_directory,
    )
    workflow = upsert_workflow(cfg, CT_HYBRID_SEARCH_WORKFLOW_ID, workflow_yaml)
    return {
        "workflow": workflow,
        "workflow_id": CT_HYBRID_SEARCH_WORKFLOW_ID,
        "workflow_url": workflow_url(cfg, CT_HYBRID_SEARCH_WORKFLOW_ID),
        "run_url": f"{cfg.url}/api/workflows/workflow/{CT_HYBRID_SEARCH_WORKFLOW_ID}/run",
    }
