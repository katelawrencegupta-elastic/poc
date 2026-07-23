"""Elasticsearch bulk ingest for synthetic GEH telemetry."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence


DEFAULT_ELASTIC_URL = (
    "https://klggehpoc-eb6d47.es.us-central1.gcp.elastic.cloud:443"
)

DEFAULT_INDICATOR_INDEX = "ct_sitedata_ext2_indicator_events_m"
DEFAULT_HONEYCOMB_INDEX = "pcd_detector_lpp_honeycomb"
DEFAULT_REPAIR_INDEX = "ct_system_repair_history"
DEFAULT_MANUAL_INDEX = "ct_device_manuals"
DEFAULT_PARTS_INDEX = "ct_machine_parts"
DEFAULT_INDICATOR_SOURCE_MONTH = "ct_sitedata_ext2_indicator_events_m-2026.07.01"


@dataclass
class ElasticConfig:
    url: str = DEFAULT_ELASTIC_URL
    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    verify_certs: bool = True
    timeout_s: float = 60.0

    @classmethod
    def from_env(
        cls,
        *,
        url: str | None = None,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify_certs: bool | None = None,
    ) -> ElasticConfig:
        verify = verify_certs
        if verify is None:
            verify = os.environ.get("ELASTIC_VERIFY_CERTS", "true").lower() not in {
                "0",
                "false",
                "no",
            }
        return cls(
            url=(url or os.environ.get("ELASTIC_URL") or DEFAULT_ELASTIC_URL).rstrip(
                "/"
            ),
            api_key=api_key or os.environ.get("ELASTIC_API_KEY"),
            username=username or os.environ.get("ELASTIC_USER"),
            password=password
            if password is not None
            else os.environ.get("ELASTIC_PASSWORD"),
            verify_certs=verify,
        )

    def auth_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"ApiKey {self.api_key}"}
        if self.username and self.password is not None:
            import base64

            token = base64.b64encode(
                f"{self.username}:{self.password}".encode("utf-8")
            ).decode("ascii")
            return {"Authorization": f"Basic {token}"}
        raise ValueError(
            "Elasticsearch credentials required: set ELASTIC_API_KEY "
            "or ELASTIC_USER + ELASTIC_PASSWORD (or pass --api-key / --user --password)"
        )


@dataclass
class BulkResult:
    indexed: int
    errors: int
    items: list[dict[str, Any]]


def _ssl_context(verify: bool) -> ssl.SSLContext | None:
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def request_json(
    cfg: ElasticConfig,
    method: str,
    path: str,
    body: bytes | None = None,
) -> dict[str, Any]:
    url = f"{cfg.url}{path}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **cfg.auth_headers(),
    }
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            req, timeout=cfg.timeout_s, context=_ssl_context(cfg.verify_certs)
        ) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Elasticsearch {method} {path} -> HTTP {exc.code}: {detail}") from exc


def ping(cfg: ElasticConfig) -> dict[str, Any]:
    return request_json(cfg, "GET", "/")


def bulk(
    cfg: ElasticConfig,
    lines: Sequence[str],
    *,
    refresh: bool = False,
) -> BulkResult:
    if not lines:
        return BulkResult(indexed=0, errors=0, items=[])
    path = "/_bulk"
    if refresh:
        path += "?refresh=true"
    body = ("\n".join(lines) + "\n").encode("utf-8")
    # NDJSON content-type for bulk
    url = f"{cfg.url}{path}"
    headers = {
        "Content-Type": "application/x-ndjson",
        "Accept": "application/json",
        **cfg.auth_headers(),
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(
            req, timeout=cfg.timeout_s, context=_ssl_context(cfg.verify_certs)
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Elasticsearch bulk -> HTTP {exc.code}: {detail}") from exc

    items = payload.get("items") or []
    errors = 0
    indexed = 0
    for item in items:
        action = next(iter(item.values()), {})
        if action.get("error"):
            errors += 1
        else:
            indexed += 1
    return BulkResult(indexed=indexed, errors=errors, items=items)


def _strip_meta(doc: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any]]:
    body = dict(doc)
    doc_id = body.pop("_id", None) or body.pop("id", None)
    index = body.pop("_index", None) or body.pop("index", None)
    body.pop("_score", None)
    body.pop("score", None)
    return (
        str(doc_id) if doc_id else None,
        str(index) if index else None,
        body,
    )


def index_indicator_events(
    cfg: ElasticConfig,
    docs: Iterable[dict[str, Any]],
    *,
    index: str | None = None,
    chunk_size: int = 200,
    refresh: bool = False,
) -> BulkResult:
    """Bulk-index indicator events. Uses each doc's `_index` when present."""
    default_index = index or os.environ.get(
        "ELASTIC_INDICATOR_INDEX", DEFAULT_INDICATOR_INDEX
    )
    pending = list(docs)
    total = BulkResult(indexed=0, errors=0, items=[])
    for i in range(0, len(pending), chunk_size):
        chunk = pending[i : i + chunk_size]
        lines: list[str] = []
        for doc in chunk:
            doc_id, doc_index, body = _strip_meta(doc)
            target = doc_index or default_index
            # Prefer data-stream / monthly style from factory; if factory stored
            # full monthly name keep it, else use configured default.
            action: dict[str, Any] = {"index": {"_index": target}}
            if doc_id:
                action["index"]["_id"] = doc_id
            lines.append(json.dumps(action, separators=(",", ":")))
            lines.append(json.dumps(body, separators=(",", ":")))
        result = bulk(cfg, lines, refresh=refresh)
        total.indexed += result.indexed
        total.errors += result.errors
        total.items.extend(result.items)
    return total


def _honeycomb_session_context(
    payload: dict[str, Any],
    *,
    timestamp: datetime | None = None,
    meta: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[str, list[int]], list[int]]:
    """Parse nested honeycomb payload → (session_id, shared fields, is_bad, failed)."""
    session_keys = [k for k in payload if k not in ("specid", "status")]
    if len(session_keys) != 1:
        raise ValueError("honeycomb payload must have exactly one session UUID key")
    session_id = session_keys[0]
    node = payload[session_id]
    m = node["map"]
    is_bad_raw = m.get("is_bad") or {}
    is_bad: dict[str, list[int]] = {
        str(k): list(v) for k, v in is_bad_raw.items()
    }
    collimation = str(m.get("collimation", "80"))
    mm_key = f"{collimation}mm"
    mm = node.get(mm_key, {})
    failed = list(mm.get("failed_modules") or [])
    when = timestamp or datetime.now(timezone.utc)
    shared: dict[str, Any] = {
        "@timestamp": when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "session_id": session_id,
        "specid": payload.get("specid"),
        "status": payload.get("status"),
        "collimation": collimation,
        "collimation_status": mm.get("status"),
        "failed_modules": failed,
        "dataset": m.get("dataset"),
        "vector_type": m.get("vector_type"),
        "is_bad_count": m.get("is_bad_count", sum(len(v) for v in is_bad.values())),
        "module_count": len(is_bad),
    }
    if meta:
        shared.update(meta)
    return session_id, shared, is_bad, failed


def honeycomb_to_documents(
    payload: dict[str, Any],
    *,
    timestamp: datetime | None = None,
    meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Expand one honeycomb payload into multiple ES documents (one per module).

    Each module document carries denormalized session context plus:
    ``module_id``, ``pixel_ids``, ``pixel_count``, ``is_failed_module``.

    PASS / empty ``is_bad`` emits a single ``record_type=session`` stub so the
    calibration remains searchable.
    """
    session_id, shared, is_bad, failed = _honeycomb_session_context(
        payload, timestamp=timestamp, meta=meta
    )
    failed_set = {int(x) for x in failed}
    docs: list[dict[str, Any]] = []

    if not is_bad:
        docs.append(
            {
                **shared,
                "_id": f"{session_id}:session",
                "record_type": "session",
                "module_id": None,
                "pixel_ids": [],
                "pixel_count": 0,
                "is_failed_module": False,
            }
        )
        return docs

    for mod_key in sorted(is_bad.keys(), key=lambda x: int(x)):
        module_id = int(mod_key)
        pixels = list(is_bad[mod_key])
        docs.append(
            {
                **shared,
                "_id": f"{session_id}:{module_id}",
                "record_type": "module",
                "module_id": module_id,
                "pixel_ids": pixels,
                "pixel_count": len(pixels),
                "is_failed_module": module_id in failed_set,
            }
        )
    return docs


def honeycomb_to_document(
    payload: dict[str, Any],
    *,
    timestamp: datetime | None = None,
    meta: dict[str, Any] | None = None,
    include_raw_is_bad: bool = False,
) -> dict[str, Any]:
    """Deprecated: single-doc summary. Prefer ``honeycomb_to_documents`` for ingest."""
    session_id, shared, is_bad, _failed = _honeycomb_session_context(
        payload, timestamp=timestamp, meta=meta
    )
    doc: dict[str, Any] = {
        **shared,
        "_id": f"{session_id}:session",
        "record_type": "session",
        "module_ids": sorted(int(k) for k in is_bad.keys()),
    }
    if include_raw_is_bad:
        doc["is_bad"] = is_bad
    return doc


def _bulk_index_docs(
    cfg: ElasticConfig,
    docs: Sequence[dict[str, Any]],
    *,
    index: str,
    chunk_size: int = 200,
    refresh: bool = False,
) -> BulkResult:
    total = BulkResult(indexed=0, errors=0, items=[])
    pending = list(docs)
    for i in range(0, len(pending), chunk_size):
        chunk = pending[i : i + chunk_size]
        lines: list[str] = []
        for doc in chunk:
            doc_id, doc_index, body = _strip_meta(doc)
            target = doc_index or index
            action: dict[str, Any] = {"index": {"_index": target}}
            if doc_id:
                action["index"]["_id"] = doc_id
            lines.append(json.dumps(action, separators=(",", ":")))
            lines.append(json.dumps(body, separators=(",", ":")))
        result = bulk(cfg, lines, refresh=refresh)
        total.indexed += result.indexed
        total.errors += result.errors
        total.items.extend(result.items)
    return total


def index_honeycomb(
    cfg: ElasticConfig,
    payload: dict[str, Any],
    *,
    index: str | None = None,
    doc_id: str | None = None,
    refresh: bool = False,
    meta: dict[str, Any] | None = None,
    chunk_size: int = 200,
) -> BulkResult:
    """Bulk-index one honeycomb payload as multiple module documents."""
    target = index or os.environ.get(
        "ELASTIC_HONEYCOMB_INDEX", DEFAULT_HONEYCOMB_INDEX
    )
    docs = honeycomb_to_documents(payload, meta=meta)
    if doc_id and len(docs) == 1:
        docs[0]["_id"] = doc_id
    return _bulk_index_docs(
        cfg, docs, index=target, chunk_size=chunk_size, refresh=refresh
    )


def index_honeycomb_samples(
    cfg: ElasticConfig,
    samples: Sequence[Any],
    *,
    index: str | None = None,
    refresh: bool = False,
    chunk_size: int = 200,
) -> BulkResult:
    """Bulk-index honeycomb samples (each expands to one doc per module)."""
    target = index or os.environ.get(
        "ELASTIC_HONEYCOMB_INDEX", DEFAULT_HONEYCOMB_INDEX
    )
    docs: list[dict[str, Any]] = []
    for sample in samples:
        if hasattr(sample, "payload"):
            docs.extend(
                honeycomb_to_documents(sample.payload, meta=sample.meta)
            )
        else:
            docs.extend(honeycomb_to_documents(sample))

    return _bulk_index_docs(
        cfg, docs, index=target, chunk_size=chunk_size, refresh=refresh
    )


def _field_or_keyword(name: str, *, keyword: bool) -> str:
    return f"{name}.keyword" if keyword else name


def fetch_indicator_system_keys(
    cfg: ElasticConfig,
    *,
    index: str | None = None,
    size: int = 500,
) -> list[Any]:
    """Return SystemKey rows for distinct sysid × machine_type × sw_version.

    Reads from the monthly indicator index (default ``…-2026.07.01``).
    """
    from .repairs import SystemKey

    target = index or os.environ.get(
        "ELASTIC_INDICATOR_SOURCE_INDEX", DEFAULT_INDICATOR_SOURCE_MONTH
    )
    source_fields = [
        "sysid",
        "machine_type",
        "sw_version",
        "hospital",
        "customer",
        "city",
        "state",
        "country",
        "region",
        "zone",
        "zipcode",
        "latitude",
        "longitude",
        "location",
        "productName",
        "systype",
        "installDate",
        "application_sw_release_id",
        "log_type",
    ]

    def _body(keyword: bool) -> dict[str, Any]:
        return {
            "size": 0,
            "aggs": {
                "sysids": {
                    "terms": {
                        "field": _field_or_keyword("sysid", keyword=keyword),
                        "size": size,
                    },
                    "aggs": {
                        "machine_types": {
                            "terms": {
                                "field": _field_or_keyword(
                                    "machine_type", keyword=keyword
                                ),
                                "size": 20,
                            },
                            "aggs": {
                                "sw_versions": {
                                    "terms": {
                                        "field": _field_or_keyword(
                                            "sw_version", keyword=keyword
                                        ),
                                        "size": 50,
                                    },
                                    "aggs": {
                                        "top": {
                                            "top_hits": {
                                                "size": 1,
                                                "_source": source_fields,
                                            }
                                        }
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }

    try:
        payload = request_json(
            cfg, "POST", f"/{target}/_search", json.dumps(_body(True)).encode("utf-8")
        )
    except RuntimeError:
        payload = request_json(
            cfg, "POST", f"/{target}/_search", json.dumps(_body(False)).encode("utf-8")
        )

    keys: list[SystemKey] = []
    for sys_bucket in payload["aggregations"]["sysids"]["buckets"]:
        for mt_bucket in sys_bucket["machine_types"]["buckets"]:
            for sw_bucket in mt_bucket["sw_versions"]["buckets"]:
                hit = sw_bucket["top"]["hits"]["hits"][0]["_source"]
                keys.append(
                    SystemKey.from_context(hit, doc_count=int(sw_bucket["doc_count"]))
                )
    keys.sort(key=lambda k: (k.sysid, k.machine_type, k.sw_version))
    return keys


REPAIR_INDEX_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "opened_at": {"type": "date"},
            "closed_at": {"type": "date"},
            "es_load_ts": {"type": "date"},
            "installDate": {"type": "date", "ignore_malformed": True},
            "duration_hours": {"type": "float"},
            "labor_hours": {"type": "float"},
            "history_span_days": {"type": "integer"},
            "repair_sequence": {"type": "integer"},
            "repair_count_for_system": {"type": "integer"},
            "source_indicator_doc_count": {"type": "integer"},
            "synthetic": {"type": "boolean"},
            "warranty_covered": {"type": "boolean"},
            "travel_required": {"type": "boolean"},
            "location": {"type": "keyword"},
            "parts_replaced": {
                "type": "nested",
                "properties": {
                    "part_number": {"type": "keyword"},
                    "description": {"type": "text"},
                    "quantity": {"type": "integer"},
                    "unit_cost_usd": {"type": "float"},
                    "warranty_covered": {"type": "boolean"},
                },
            },
            "follow_ups": {
                "type": "nested",
                "properties": {
                    "type": {"type": "keyword"},
                    "due_days": {"type": "integer"},
                    "owner": {"type": "keyword"},
                },
            },
            "qa_checks": {
                "properties": {
                    "detector_lpp": {"type": "keyword"},
                    "air_kerma": {"type": "keyword"},
                    "collimation": {"type": "keyword"},
                    "safety_interlocks": {"type": "keyword"},
                }
            },
            "sysid": {"type": "keyword"},
            "machine_type": {"type": "keyword"},
            "sw_version": {"type": "keyword"},
            "work_order_id": {"type": "keyword"},
            "failure_code": {"type": "keyword"},
            "subsystem": {"type": "keyword"},
            "status": {"type": "keyword"},
            "priority": {"type": "keyword"},
            "detail_level": {"type": "keyword"},
            "visit_type": {"type": "keyword"},
            "record_type": {"type": "keyword"},
            "productName": {"type": "keyword"},
            "systype": {"type": "keyword"},
            "hospital": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "customer": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "symptom": {"type": "text"},
            "resolution": {"type": "text"},
            "notes": {"type": "text"},
            "root_cause": {"type": "text"},
            "customer_impact": {"type": "text"},
            "field_engineer": {"type": "keyword"},
            "source_indicator_index": {"type": "keyword"},
            "related_case_id": {"type": "keyword"},
            "region": {"type": "keyword"},
            "zone": {"type": "keyword"},
            "country": {"type": "keyword"},
            "state": {"type": "keyword"},
            "city": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "zipcode": {"type": "keyword"},
            "latitude": {"type": "keyword"},
            "longitude": {"type": "keyword"},
            "log_type": {"type": "keyword"},
            "application_sw_release_id": {"type": "keyword"},
            # Populated at ingest; inference_id applied via put_semantic_mapping
            # / enable_semantic_processing for live indexes.
            "semantic_search": {"type": "semantic_text"},
        }
    },
}


def ensure_repair_index(
    cfg: ElasticConfig,
    *,
    index: str | None = None,
) -> str:
    """Create the repair index with mappings if it does not already exist."""
    target = index or os.environ.get("ELASTIC_REPAIR_INDEX", DEFAULT_REPAIR_INDEX)
    try:
        request_json(cfg, "GET", f"/{target}")
        return target
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
    body = json.dumps(REPAIR_INDEX_MAPPING).encode("utf-8")
    request_json(cfg, "PUT", f"/{target}", body)
    return target


def index_repairs(
    cfg: ElasticConfig,
    docs: Iterable[dict[str, Any]],
    *,
    index: str | None = None,
    chunk_size: int = 200,
    refresh: bool = False,
    ensure_index: bool = True,
) -> BulkResult:
    """Bulk-index synthetic repair history documents."""
    target = index or os.environ.get("ELASTIC_REPAIR_INDEX", DEFAULT_REPAIR_INDEX)
    if ensure_index:
        ensure_repair_index(cfg, index=target)
    return _bulk_index_docs(
        cfg, list(docs), index=target, chunk_size=chunk_size, refresh=refresh
    )


MANUAL_INDEX_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "es_load_ts": {"type": "date"},
            "synthetic": {"type": "boolean"},
            "record_type": {"type": "keyword"},
            "doc_type": {"type": "keyword"},
            "manual_id": {"type": "keyword"},
            "version": {"type": "keyword"},
            "systype": {"type": "keyword"},
            "productName": {"type": "keyword"},
            "machine_family": {"type": "keyword"},
            "audience": {"type": "keyword"},
            "log_type": {"type": "keyword"},
            "sw_baselines": {"type": "keyword"},
            "subsystems": {"type": "keyword"},
            "failure_codes": {"type": "keyword"},
            "daily_checks": {"type": "text"},
            "title": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "overview": {"type": "text"},
            "safety": {"type": "text"},
            "escalation": {"type": "text"},
            "content": {"type": "text"},
            "sections": {
                "type": "nested",
                "properties": {
                    "heading": {"type": "keyword"},
                    "subsystem": {"type": "keyword"},
                    "body": {"type": "text"},
                },
            },
            "common_faults": {
                "type": "nested",
                "properties": {
                    "failure_code": {"type": "keyword"},
                    "symptom": {"type": "text"},
                    "first_actions": {"type": "text"},
                },
            },
            "semantic_search": {"type": "semantic_text"},
        }
    },
}


def ensure_manual_index(
    cfg: ElasticConfig,
    *,
    index: str | None = None,
) -> str:
    """Create the device-manual index with mappings if it does not already exist."""
    target = index or os.environ.get("ELASTIC_MANUAL_INDEX", DEFAULT_MANUAL_INDEX)
    try:
        request_json(cfg, "GET", f"/{target}")
        return target
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
    body = json.dumps(MANUAL_INDEX_MAPPING).encode("utf-8")
    request_json(cfg, "PUT", f"/{target}", body)
    return target


def index_manuals(
    cfg: ElasticConfig,
    docs: Iterable[dict[str, Any]],
    *,
    index: str | None = None,
    chunk_size: int = 200,
    refresh: bool = False,
    ensure_index: bool = True,
) -> BulkResult:
    """Bulk-index short device manual documents."""
    target = index or os.environ.get("ELASTIC_MANUAL_INDEX", DEFAULT_MANUAL_INDEX)
    if ensure_index:
        ensure_manual_index(cfg, index=target)
    return _bulk_index_docs(
        cfg, list(docs), index=target, chunk_size=chunk_size, refresh=refresh
    )


PARTS_INDEX_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "es_load_ts": {"type": "date"},
            "installDate": {"type": "date", "ignore_malformed": True},
            "synthetic": {"type": "boolean"},
            "parts_count": {"type": "integer"},
            "source_indicator_doc_count": {"type": "integer"},
            "record_type": {"type": "keyword"},
            "bom_version": {"type": "keyword"},
            "source_catalog": {"type": "keyword"},
            "source_indicator_index": {"type": "keyword"},
            "sysid": {"type": "keyword"},
            "machine_type": {"type": "keyword"},
            "sw_version": {"type": "keyword"},
            "application_sw_release_id": {"type": "keyword"},
            "systype": {"type": "keyword"},
            "productName": {"type": "keyword"},
            "log_type": {"type": "keyword"},
            "region": {"type": "keyword"},
            "zone": {"type": "keyword"},
            "country": {"type": "keyword"},
            "state": {"type": "keyword"},
            "zipcode": {"type": "keyword"},
            "latitude": {"type": "keyword"},
            "longitude": {"type": "keyword"},
            "location": {"type": "keyword"},
            "subsystems": {"type": "keyword"},
            "failure_codes": {"type": "keyword"},
            "hospital": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "customer": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "city": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "parts": {
                "type": "nested",
                "properties": {
                    "part_number": {"type": "keyword"},
                    "description": {"type": "text"},
                    "subsystem": {"type": "keyword"},
                    "role": {"type": "keyword"},
                    "default_qty": {"type": "integer"},
                    "failure_codes": {"type": "keyword"},
                    "systype_scope": {"type": "keyword"},
                },
            },
            "semantic_search": {"type": "semantic_text"},
        }
    },
}


def ensure_parts_index(
    cfg: ElasticConfig,
    *,
    index: str | None = None,
) -> str:
    """Create the machine-parts index with mappings if it does not already exist."""
    target = index or os.environ.get("ELASTIC_PARTS_INDEX", DEFAULT_PARTS_INDEX)
    try:
        request_json(cfg, "GET", f"/{target}")
        return target
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
    body = json.dumps(PARTS_INDEX_MAPPING).encode("utf-8")
    request_json(cfg, "PUT", f"/{target}", body)
    return target


def index_parts(
    cfg: ElasticConfig,
    docs: Iterable[dict[str, Any]],
    *,
    index: str | None = None,
    chunk_size: int = 200,
    refresh: bool = False,
    ensure_index: bool = True,
) -> BulkResult:
    """Bulk-index machine parts / BOM documents."""
    target = index or os.environ.get("ELASTIC_PARTS_INDEX", DEFAULT_PARTS_INDEX)
    if ensure_index:
        ensure_parts_index(cfg, index=target)
    return _bulk_index_docs(
        cfg, list(docs), index=target, chunk_size=chunk_size, refresh=refresh
    )
