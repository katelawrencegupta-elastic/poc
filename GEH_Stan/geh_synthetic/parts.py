"""Machine parts / BOM lists correlated with CT sysid, systype, and sw_version."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from .repairs import REPAIR_CATALOG, SystemKey
from .semantic import parts_semantic_text

DEFAULT_PARTS_INDEX = "ct_machine_parts"
BOM_VERSION = "1.0"

# Shared field-replaceable parts derived from the repair catalog, plus a few
# systype-scoped kits so Apex vs CT BOMs are not identical.
def _parts_from_repair_catalog() -> list[dict[str, Any]]:
    by_pn: dict[str, dict[str, Any]] = {}
    for entry in REPAIR_CATALOG:
        for part_number, description, qty in entry["parts"]:
            row = by_pn.setdefault(
                part_number,
                {
                    "part_number": part_number,
                    "description": description,
                    "subsystem": entry["subsystem"],
                    "default_qty": int(qty),
                    "role": "field_replaceable",
                    "failure_codes": [],
                    "systype_scope": ["Revolution CT", "Revolution Apex"],
                },
            )
            code = entry["failure_code"]
            if code not in row["failure_codes"]:
                row["failure_codes"].append(code)
    return list(by_pn.values())


PARTS_CATALOG: list[dict[str, Any]] = _parts_from_repair_catalog() + [
    {
        "part_number": "DET-MOD-REVCT-160",
        "description": "Revolution CT Rev 160 detector ring spare module kit",
        "subsystem": "Detector",
        "default_qty": 1,
        "role": "bom_kit",
        "failure_codes": ["DET-LPP-FAIL", "IMG-BAND-ART"],
        "systype_scope": ["Revolution CT"],
        "sw_baselines": ["25MW38.x", "25MW27.x", "24MW*"],
    },
    {
        "part_number": "DET-MOD-APEX-160",
        "description": "Revolution Apex Elite 160 detector / DAS spare module kit",
        "subsystem": "Detector / DAS",
        "default_qty": 1,
        "role": "bom_kit",
        "failure_codes": ["DET-LPP-FAIL", "IMG-BAND-ART"],
        "systype_scope": ["Revolution Apex"],
        "sw_baselines": ["25MW38.x", "25MW27.x", "24MW10.x"],
    },
    {
        "part_number": "CLU-KIT-APEX-HT",
        "description": "Apex high-throughput cooling pump + sensor kit",
        "subsystem": "Cooling",
        "default_qty": 1,
        "role": "bom_kit",
        "failure_codes": ["CLU-PRESS-LO", "HV-OT-WARN"],
        "systype_scope": ["Revolution Apex"],
        "sw_baselines": ["25MW38.x", "25MW27.x"],
    },
    {
        "part_number": "PM-KIT-REVAPEX",
        "description": "Annual PM consumables kit — Revolution Apex Elite",
        "subsystem": "Service",
        "default_qty": 1,
        "role": "pm_kit",
        "failure_codes": ["PM-SCHEDULED"],
        "systype_scope": ["Revolution Apex"],
        "sw_baselines": ["25MW*", "24MW*"],
    },
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _doc_id(sysid: str, machine_type: str, sw_version: str) -> str:
    raw = f"{sysid}:{machine_type}:{sw_version}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _sw_matches(baselines: Sequence[str] | None, sw_version: str) -> bool:
    if not baselines:
        return True
    sw = sw_version or ""
    for pattern in baselines:
        if pattern.endswith("*"):
            if sw.startswith(pattern[:-1]):
                return True
        elif pattern.endswith(".x"):
            prefix = pattern[:-1]  # e.g. 25MW38.
            if sw.startswith(prefix):
                return True
        elif sw == pattern:
            return True
    return False


def parts_for_system(
    *,
    systype: str,
    sw_version: str,
    catalog: Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return BOM rows applicable to a systype + software version."""
    rows: list[dict[str, Any]] = []
    for part in catalog or PARTS_CATALOG:
        scope = part.get("systype_scope") or ["Revolution CT", "Revolution Apex"]
        if systype and systype not in scope:
            continue
        if not _sw_matches(part.get("sw_baselines"), sw_version):
            continue
        rows.append(
            {
                "part_number": part["part_number"],
                "description": part["description"],
                "subsystem": part["subsystem"],
                "role": part.get("role", "field_replaceable"),
                "default_qty": int(part.get("default_qty", 1)),
                "failure_codes": list(part.get("failure_codes") or []),
                "systype_scope": list(scope),
            }
        )
    rows.sort(key=lambda p: (p["subsystem"], p["part_number"]))
    return rows


@dataclass
class PartsConfig:
    systems: Sequence[SystemKey]
    index: str = DEFAULT_PARTS_INDEX
    bom_version: str = BOM_VERSION
    source_indicator_index: str = ""
    timestamp: datetime | None = None


def build_machine_parts_document(
    system: SystemKey,
    *,
    index: str = DEFAULT_PARTS_INDEX,
    bom_version: str = BOM_VERSION,
    source_indicator_index: str = "",
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    when = timestamp or datetime.now(timezone.utc)
    ts = when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    parts = parts_for_system(systype=system.systype, sw_version=system.sw_version)
    subsystems = sorted({p["subsystem"] for p in parts})
    failure_codes = sorted(
        {code for p in parts for code in p.get("failure_codes") or []}
    )
    doc = {
        "_id": _doc_id(system.sysid, system.machine_type, system.sw_version),
        "_index": index,
        "@timestamp": ts,
        "es_load_ts": _utc_now_iso(),
        "record_type": "machine_parts",
        "bom_version": bom_version,
        "source_catalog": "repair_catalog_v1+systype_kits",
        "source_indicator_index": source_indicator_index or None,
        "synthetic": True,
        "sysid": system.sysid,
        "machine_type": system.machine_type,
        "sw_version": system.sw_version,
        "application_sw_release_id": system.application_sw_release_id
        or system.sw_version,
        "systype": system.systype,
        "productName": system.product_name,
        "hospital": system.hospital,
        "customer": system.customer,
        "city": system.city,
        "state": system.state,
        "country": system.country,
        "region": system.region,
        "zone": system.zone,
        "zipcode": system.zipcode,
        "latitude": system.latitude,
        "longitude": system.longitude,
        "location": system.location,
        "installDate": system.install_date or None,
        "log_type": system.log_type or "device_parts",
        "parts": parts,
        "parts_count": len(parts),
        "subsystems": subsystems,
        "failure_codes": failure_codes,
        "source_indicator_doc_count": system.indicator_doc_count,
    }
    doc["semantic_search"] = parts_semantic_text(doc)
    return doc


def generate_machine_parts(cfg: PartsConfig) -> list[dict[str, Any]]:
    """One parts/BOM document per sysid × machine_type × sw_version."""
    docs = [
        build_machine_parts_document(
            system,
            index=cfg.index,
            bom_version=cfg.bom_version,
            source_indicator_index=cfg.source_indicator_index,
            timestamp=cfg.timestamp,
        )
        for system in cfg.systems
    ]
    docs.sort(key=lambda d: (d["systype"], d["hospital"], d["sysid"], d["sw_version"]))
    return docs


def summarize_machine_parts(docs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_systype: dict[str, int] = {}
    part_numbers: set[str] = set()
    for doc in docs:
        by_systype[doc["systype"]] = by_systype.get(doc["systype"], 0) + 1
        for part in doc.get("parts") or []:
            part_numbers.add(part["part_number"])
    return {
        "document_count": len(docs),
        "systypes": by_systype,
        "unique_sysids": len({d["sysid"] for d in docs}),
        "unique_part_numbers": len(part_numbers),
        "avg_parts_per_system": (
            round(sum(d["parts_count"] for d in docs) / len(docs), 2) if docs else 0
        ),
    }
