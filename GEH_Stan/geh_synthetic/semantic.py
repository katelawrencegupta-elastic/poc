"""Semantic search helpers for CT manuals, repairs, and parts indexes.

Adds a ``semantic_search`` ``semantic_text`` field (ELSER by default) that
concatenates the free-text narrative fields recommended for NL retrieval.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .elastic import (
    DEFAULT_MANUAL_INDEX,
    DEFAULT_PARTS_INDEX,
    DEFAULT_REPAIR_INDEX,
    ElasticConfig,
    request_json,
)

# Hosted ELSER on Elastic serverless (sparse). Override with ELASTIC_SEMANTIC_INFERENCE_ID.
DEFAULT_SEMANTIC_INFERENCE_ID = ".elser-2-elastic"
DEFAULT_MANUAL_LOOKUP_INDEX = "ct_device_manuals_lookup"

SEMANTIC_FIELD = "semantic_search"


def semantic_field_mapping(
    inference_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "semantic_text",
        "inference_id": inference_id
        or os.environ.get("ELASTIC_SEMANTIC_INFERENCE_ID")
        or DEFAULT_SEMANTIC_INFERENCE_ID,
    }


def _join_parts(parts: Sequence[str | None]) -> str:
    return "\n\n".join(p.strip() for p in parts if p and str(p).strip())


def manual_semantic_text(doc: dict[str, Any]) -> str:
    """Combine manual prose used for field-service NL search."""
    chunks: list[str] = []
    for key in ("title", "overview", "safety", "content", "escalation"):
        val = doc.get(key)
        if isinstance(val, str) and val.strip():
            chunks.append(val)
    checks = doc.get("daily_checks") or []
    if checks:
        chunks.append("Daily checks: " + "; ".join(str(c) for c in checks))
    for section in doc.get("sections") or []:
        heading = section.get("heading") or section.get("subsystem") or "Section"
        body = section.get("body") or ""
        if body:
            chunks.append(f"{heading}: {body}")
    for fault in doc.get("common_faults") or []:
        code = fault.get("failure_code") or ""
        symptom = fault.get("symptom") or ""
        actions = fault.get("first_actions") or []
        action_txt = "; ".join(str(a) for a in actions) if actions else ""
        bits = [b for b in (code, symptom, action_txt) if b]
        if bits:
            chunks.append(" — ".join(bits))
    return _join_parts(chunks)


def repair_semantic_text(doc: dict[str, Any]) -> str:
    """Combine repair narrative fields for NL triage search."""
    chunks: list[str] = []
    for key in ("symptom", "root_cause", "resolution", "notes", "customer_impact"):
        val = doc.get(key)
        if isinstance(val, str) and val.strip():
            chunks.append(val)
    for part in doc.get("parts_replaced") or []:
        desc = part.get("description")
        pn = part.get("part_number")
        if desc:
            chunks.append(f"Part {pn}: {desc}" if pn else str(desc))
    return _join_parts(chunks)


def parts_semantic_text(doc: dict[str, Any]) -> str:
    """Combine BOM part descriptions for NL part lookup."""
    chunks: list[str] = []
    for part in doc.get("parts") or []:
        desc = part.get("description")
        if not desc:
            continue
        pn = part.get("part_number")
        sub = part.get("subsystem")
        label = desc
        if pn:
            label = f"{pn}: {desc}"
        if sub:
            label = f"{label} ({sub})"
        chunks.append(label)
    return _join_parts(chunks)


def attach_semantic_search(
    doc: dict[str, Any],
    builder: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """Return a shallow copy with ``semantic_search`` populated when non-empty."""
    out = dict(doc)
    text = builder(out)
    if text:
        out[SEMANTIC_FIELD] = text
    return out


@dataclass
class SemanticIndexPlan:
    index: str
    builder: Callable[[dict[str, Any]], str]
    label: str


def default_semantic_plans(
    *,
    manuals_index: str | None = None,
    manuals_lookup_index: str | None = None,
    repairs_index: str | None = None,
    parts_index: str | None = None,
) -> list[SemanticIndexPlan]:
    return [
        SemanticIndexPlan(
            index=manuals_index
            or os.environ.get("ELASTIC_MANUAL_INDEX", DEFAULT_MANUAL_INDEX),
            builder=manual_semantic_text,
            label="manuals",
        ),
        SemanticIndexPlan(
            index=manuals_lookup_index
            or os.environ.get(
                "ELASTIC_MANUAL_LOOKUP_INDEX", DEFAULT_MANUAL_LOOKUP_INDEX
            ),
            builder=manual_semantic_text,
            label="manuals_lookup",
        ),
        SemanticIndexPlan(
            index=repairs_index
            or os.environ.get("ELASTIC_REPAIR_INDEX", DEFAULT_REPAIR_INDEX),
            builder=repair_semantic_text,
            label="repairs",
        ),
        SemanticIndexPlan(
            index=parts_index
            or os.environ.get("ELASTIC_PARTS_INDEX", DEFAULT_PARTS_INDEX),
            builder=parts_semantic_text,
            label="parts",
        ),
    ]


def put_semantic_mapping(
    cfg: ElasticConfig,
    index: str,
    *,
    inference_id: str | None = None,
) -> dict[str, Any]:
    """Add ``semantic_search`` mapping (no-op if already present with same type)."""
    body = {
        "properties": {
            SEMANTIC_FIELD: semantic_field_mapping(inference_id),
        }
    }
    return request_json(
        cfg, "PUT", f"/{index}/_mapping", json.dumps(body).encode("utf-8")
    )


def _scroll_sources(
    cfg: ElasticConfig,
    index: str,
    *,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """Load all docs with _id and _source (small CT indexes)."""
    docs: list[dict[str, Any]] = []
    payload = {
        "size": page_size,
        "query": {"match_all": {}},
        "sort": [{"_doc": "asc"}],
    }
    path = f"/{index}/_search?scroll=2m"
    resp = request_json(cfg, "POST", path, json.dumps(payload).encode("utf-8"))
    scroll_id = resp.get("_scroll_id")
    while True:
        hits = (resp.get("hits") or {}).get("hits") or []
        if not hits:
            break
        for hit in hits:
            src = dict(hit.get("_source") or {})
            src["_id"] = hit.get("_id")
            docs.append(src)
        if not scroll_id:
            break
        resp = request_json(
            cfg,
            "POST",
            "/_search/scroll",
            json.dumps({"scroll": "2m", "scroll_id": scroll_id}).encode("utf-8"),
        )
        scroll_id = resp.get("_scroll_id")
    if scroll_id:
        try:
            request_json(
                cfg,
                "DELETE",
                "/_search/scroll",
                json.dumps({"scroll_id": [scroll_id]}).encode("utf-8"),
            )
        except RuntimeError:
            pass
    return docs


def backfill_semantic_search(
    cfg: ElasticConfig,
    plan: SemanticIndexPlan,
    *,
    chunk_size: int = 25,
    refresh: bool = False,
) -> dict[str, Any]:
    """Compute and bulk-update ``semantic_search`` for every document in the index."""
    docs = _scroll_sources(cfg, plan.index)
    updated = 0
    skipped = 0
    errors = 0
    error_samples: list[str] = []

    for i in range(0, len(docs), chunk_size):
        chunk = docs[i : i + chunk_size]
        lines: list[str] = []
        for doc in chunk:
            doc_id = doc.get("_id")
            text = plan.builder(doc)
            if not text or not doc_id:
                skipped += 1
                continue
            action = {"update": {"_index": plan.index, "_id": doc_id}}
            # doc partial update; inference runs on write
            body = {"doc": {SEMANTIC_FIELD: text}}
            lines.append(json.dumps(action, separators=(",", ":")))
            lines.append(json.dumps(body, separators=(",", ":")))
        if not lines:
            continue
        path = "/_bulk"
        if refresh:
            path += "?refresh=true"
        from .elastic import bulk

        result = bulk(cfg, lines, refresh=refresh)
        updated += result.indexed
        errors += result.errors
        if result.errors:
            for item in result.items:
                action = next(iter(item.values()), {})
                if action.get("error"):
                    error_samples.append(json.dumps(action["error"])[:300])
                    if len(error_samples) >= 5:
                        break
        # Gentle pacing so inference cold-start does not stampede
        time.sleep(0.2)

    return {
        "index": plan.index,
        "label": plan.label,
        "docs_seen": len(docs),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_samples": error_samples,
    }


def enable_semantic_processing(
    cfg: ElasticConfig,
    *,
    plans: Sequence[SemanticIndexPlan] | None = None,
    inference_id: str | None = None,
    chunk_size: int = 25,
    refresh: bool = False,
    skip_missing: bool = True,
) -> list[dict[str, Any]]:
    """Put semantic mappings and backfill ``semantic_search`` on planned indexes."""
    selected = list(plans) if plans is not None else default_semantic_plans()
    reports: list[dict[str, Any]] = []
    # Longer timeout for inference-backed writes
    cfg = ElasticConfig(
        url=cfg.url,
        api_key=cfg.api_key,
        username=cfg.username,
        password=cfg.password,
        verify_certs=cfg.verify_certs,
        timeout_s=max(cfg.timeout_s, 180.0),
    )
    for plan in selected:
        try:
            request_json(cfg, "GET", f"/{plan.index}")
        except RuntimeError as exc:
            if skip_missing and "HTTP 404" in str(exc):
                reports.append(
                    {
                        "index": plan.index,
                        "label": plan.label,
                        "skipped": True,
                        "reason": "index_not_found",
                    }
                )
                continue
            raise
        put_semantic_mapping(cfg, plan.index, inference_id=inference_id)
        report = backfill_semantic_search(
            cfg, plan, chunk_size=chunk_size, refresh=refresh
        )
        reports.append(report)
    return reports


def verify_semantic_search(
    cfg: ElasticConfig,
    index: str,
    query: str,
    *,
    size: int = 3,
) -> list[dict[str, Any]]:
    """Run a ``semantic`` query against ``semantic_search`` and return hit summaries."""
    body = {
        "size": size,
        "_source": ["title", "sysid", "hospital", "symptom", "manual_id", "systype"],
        "query": {"semantic": {"field": SEMANTIC_FIELD, "query": query}},
    }
    resp = request_json(
        cfg, "POST", f"/{index}/_search", json.dumps(body).encode("utf-8")
    )
    out: list[dict[str, Any]] = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        out.append(
            {
                "_id": hit.get("_id"),
                "_score": hit.get("_score"),
                "_source": hit.get("_source"),
            }
        )
    return out
