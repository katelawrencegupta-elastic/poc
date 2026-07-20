"""Synthetic historical field-service repair records for CT systems."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Any, Literal, Sequence

from .semantic import repair_semantic_text

DetailLevel = Literal["sparse", "standard", "rich"]

DEFAULT_REPAIR_INDEX = "ct_system_repair_history"
SOURCE_INDICATOR_INDEX = "ct_sitedata_ext2_indicator_events_m-2026.07.01"

# (symptom, failure_code, subsystem, typical_parts, resolutions)
REPAIR_CATALOG: list[dict[str, Any]] = [
    {
        "symptom": "Detector LPP calibration FAIL; elevated bad-pixel count",
        "failure_code": "DET-LPP-FAIL",
        "subsystem": "Detector",
        "parts": [
            ("5794000-2", "Detector module assembly", 1),
            ("46-329142P1", "Thermal interface pad kit", 1),
        ],
        "resolutions": [
            "Replaced failed detector module; recalibrated LPP map PASS",
            "Reseated DAS harness and re-ran detector flat / LPP; PASS",
            "Updated detector firmware and cleared bad-pixel map; PASS",
        ],
    },
    {
        "symptom": "Gantry intermittent communication loss during helical exams",
        "failure_code": "GAN-COMM-INT",
        "subsystem": "Gantry",
        "parts": [
            ("46-308821P2", "Slip-ring brush assembly", 1),
            ("2118794-2", "Gantry encoder cable", 1),
        ],
        "resolutions": [
            "Replaced slip-ring brushes; verified continuous gantry telemetry",
            "Re-terminated encoder cable; no further comm drops over soak test",
        ],
    },
    {
        "symptom": "HV tank over-temp warning; scan abort on high-mA protocols",
        "failure_code": "HV-OT-WARN",
        "subsystem": "HV / Generator",
        "parts": [
            ("2243475", "HV tank cooling fan", 2),
            ("46-287110P1", "Coolant filter cartridge", 1),
        ],
        "resolutions": [
            "Replaced HV cooling fans and filter; thermal soak within spec",
            "Flushed coolant loop and recalibrated HV duty cycle limits",
        ],
    },
    {
        "symptom": "Table elevation fault; vertical drive stall at mid-height",
        "failure_code": "TBL-ELEV-FLT",
        "subsystem": "Patient Table",
        "parts": [
            ("5127894-3", "Table elevation actuator", 1),
            ("46-295501P4", "Limit switch assembly", 2),
        ],
        "resolutions": [
            "Replaced elevation actuator and limit switches; verified travel",
            "Adjusted end-stops and lubricated drive; no stall under load",
        ],
    },
    {
        "symptom": "Collimator blade position mismatch vs commanded aperture",
        "failure_code": "COL-POS-MIS",
        "subsystem": "Collimator",
        "parts": [
            ("46-301122P1", "Collimator motor assembly", 1),
            ("2116502", "Position sensor PCB", 1),
        ],
        "resolutions": [
            "Replaced collimator motor and sensor; recalibrated apertures",
            "Cleaned blade guides and recalibrated position encoders",
        ],
    },
    {
        "symptom": "Console application crash during recon; exam incomplete",
        "failure_code": "SW-RECON-CRASH",
        "subsystem": "Host Software",
        "parts": [],
        "resolutions": [
            "Applied host SW patch; cleared recon queue and validated exams",
            "Rebuilt recon services and restored configuration baseline",
            "Rolled SW to known-good build and verified recon soak",
        ],
    },
    {
        "symptom": "X-ray tube arcing at elevated kV; generator fault dump",
        "failure_code": "XR-ARC-HV",
        "subsystem": "X-Ray Tube",
        "parts": [
            ("2345678-1", "X-ray tube insert", 1),
            ("46-276543P2", "Tube oil filter", 1),
        ],
        "resolutions": [
            "Replaced x-ray tube; seasoned and verified air-kerma output",
            "Oil service + seasoning cycle; arcing cleared on high-kV protocols",
        ],
    },
    {
        "symptom": "Cooling unit pressure low; scanner thermal interlock",
        "failure_code": "CLU-PRESS-LO",
        "subsystem": "Cooling",
        "parts": [
            ("46-288001P1", "Coolant pump cartridge", 1),
            ("46-288110P3", "Pressure sensor", 1),
        ],
        "resolutions": [
            "Replaced coolant pump and sensor; restored pressure setpoints",
            "Topped coolant, purged air, and verified interlock clear",
        ],
    },
    {
        "symptom": "UPS battery failed self-test; power quality alarms",
        "failure_code": "UPS-BATT-FAIL",
        "subsystem": "Power",
        "parts": [
            ("UPS-BATT-48V", "UPS battery pack", 1),
        ],
        "resolutions": [
            "Replaced UPS battery pack; self-test PASS; cleared alarms",
        ],
    },
    {
        "symptom": "Image artifact banding on wide-collimation abdomen helical",
        "failure_code": "IMG-BAND-ART",
        "subsystem": "Detector / DAS",
        "parts": [
            ("5794012-1", "DAS channel board", 1),
        ],
        "resolutions": [
            "Replaced DAS channel board; artifact cleared on QA phantom",
            "Recalibrated DAS gains and detector offsets; banding resolved",
        ],
    },
    {
        "symptom": "Preventive maintenance due; tube hours near service interval",
        "failure_code": "PM-SCHEDULED",
        "subsystem": "Service",
        "parts": [
            ("PM-KIT-REVCT", "Annual PM consumables kit", 1),
        ],
        "resolutions": [
            "Completed scheduled PM checklist; system returned to clinical use",
            "PM completed with tube season and detector QA; signed off",
        ],
    },
    {
        "symptom": "Laser alignment offset; scout FOV mis-registration",
        "failure_code": "LAS-ALIGN-OFF",
        "subsystem": "Laser / Alignment",
        "parts": [
            ("46-312200P1", "Laser diode assembly", 1),
        ],
        "resolutions": [
            "Replaced laser diode and recalibrated isocenter lasers",
            "Mechanical realignment of laser mounts; FOV registration OK",
        ],
    },
]

PRIORITIES = ["P1-Critical", "P2-High", "P3-Medium", "P4-Low", "P5-PM"]
PRIORITY_WEIGHTS = [0.08, 0.22, 0.35, 0.20, 0.15]
STATUSES = ["Closed", "Closed", "Closed", "Closed", "Cancelled"]
VISIT_TYPES = ["Onsite", "Onsite", "Remote Assist", "Parts Only", "Onsite"]
FE_FIRST = [
    "A. Patel",
    "J. Nguyen",
    "M. Ortiz",
    "S. Okonkwo",
    "C. Berg",
    "L. Chen",
    "R. Singh",
    "K. Mueller",
    "T. Alvarez",
    "E. Johansson",
]


@dataclass
class SystemKey:
    """A distinct system identity found in indicator events."""

    sysid: str
    machine_type: str
    sw_version: str
    hospital: str = ""
    customer: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    region: str = ""
    zone: str = ""
    zipcode: str = ""
    latitude: str = ""
    longitude: str = ""
    location: str = ""
    product_name: str = ""
    systype: str = ""
    install_date: str = ""
    log_type: str = ""
    application_sw_release_id: str = ""
    indicator_doc_count: int = 0

    @classmethod
    def from_context(cls, ctx: dict[str, Any], *, doc_count: int = 0) -> SystemKey:
        return cls(
            sysid=str(ctx.get("sysid", "")),
            machine_type=str(ctx.get("machine_type", "")),
            sw_version=str(ctx.get("sw_version", "")),
            hospital=str(ctx.get("hospital", "")),
            customer=str(ctx.get("customer", "")),
            city=str(ctx.get("city", "")),
            state=str(ctx.get("state", "")),
            country=str(ctx.get("country", "")),
            region=str(ctx.get("region", "")),
            zone=str(ctx.get("zone", "")),
            zipcode=str(ctx.get("zipcode", "")),
            latitude=str(ctx.get("latitude", "")),
            longitude=str(ctx.get("longitude", "")),
            location=str(ctx.get("location", "")),
            product_name=str(ctx.get("productName", "")),
            systype=str(ctx.get("systype", "")),
            install_date=str(ctx.get("installDate", "")),
            log_type=str(ctx.get("log_type", "")),
            application_sw_release_id=str(
                ctx.get("application_sw_release_id", ctx.get("sw_version", ""))
            ),
            indicator_doc_count=doc_count,
        )


@dataclass
class RepairConfig:
    """Controls for synthetic repair history generation."""

    systems: Sequence[SystemKey]
    seed: int | None = 42
    history_end: datetime | None = None
    """Newest repair close time (default: 2026-07-01 UTC)."""
    min_repairs: int = 2
    max_repairs: int = 14
    index: str = DEFAULT_REPAIR_INDEX
    source_indicator_index: str = SOURCE_INDICATOR_INDEX
    detail_mix: dict[DetailLevel, float] = field(
        default_factory=lambda: {"sparse": 0.25, "standard": 0.45, "rich": 0.30}
    )


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _stable_seed(*parts: object) -> int:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _work_order_id(rng: Random, when: datetime) -> str:
    return f"WO-{when.year}{when.month:02d}-{rng.randint(100000, 999999)}"


def _repair_doc_id(sysid: str, work_order: str) -> str:
    return hashlib.sha1(f"{sysid}:{work_order}".encode("utf-8")).hexdigest()[:20]


def _choose_detail(rng: Random, mix: dict[DetailLevel, float]) -> DetailLevel:
    keys = list(mix.keys())
    weights = [mix[k] for k in keys]
    return rng.choices(keys, weights=weights, k=1)[0]


def _history_span_days(rng: Random, machine_type: str) -> int:
    """How far back the repair history reaches (calendar days)."""
    if machine_type == "Demo":
        return rng.randint(90, 400)
    if machine_type == "Internal":
        return rng.randint(180, 900)
    return rng.randint(120, 1200)


def _repair_count(rng: Random, span_days: int, cfg: RepairConfig) -> int:
    # Longer histories tend to have more tickets, still capped.
    density = span_days / 120.0
    lo = cfg.min_repairs
    hi = min(cfg.max_repairs, max(lo, int(2 + density * rng.uniform(0.6, 1.4))))
    return rng.randint(lo, hi)


def _parts_payload(
    rng: Random, catalog_entry: dict[str, Any], detail: DetailLevel
) -> list[dict[str, Any]]:
    parts = list(catalog_entry.get("parts") or [])
    if detail == "sparse" or not parts:
        return []
    if detail == "standard":
        parts = parts[:1] if parts else []
    out = []
    for pn, name, qty in parts:
        q = qty if detail == "rich" else rng.randint(1, max(1, qty))
        item: dict[str, Any] = {
            "part_number": pn,
            "description": name,
            "quantity": q,
        }
        if detail == "rich":
            item["unit_cost_usd"] = round(rng.uniform(85.0, 18500.0), 2)
            item["warranty_covered"] = rng.random() < 0.55
        out.append(item)
    return out


def _notes(
    rng: Random,
    *,
    detail: DetailLevel,
    symptom: str,
    resolution: str,
    subsystem: str,
    fe: str,
) -> str:
    if detail == "sparse":
        return resolution
    base = (
        f"Reported: {symptom}. Subsystem: {subsystem}. "
        f"Action: {resolution}. FE: {fe}."
    )
    if detail == "standard":
        return base
    extras = [
        "Customer confirmed clinical workflow restored after QA phantom scans.",
        "Left system in clinical mode; advised overnight soak monitoring.",
        "Parts staged overnight; second visit completed swap and calibration.",
        "Reviewed prior tickets for recurrence; no matching open SR found.",
        "Captured logs package uploaded to engineering for trend review.",
        "Verified collimation / detector LPP / HV interlocks all within limits.",
    ]
    return base + " " + " ".join(rng.sample(extras, k=rng.randint(2, 4)))


def _follow_ups(rng: Random, detail: DetailLevel) -> list[dict[str, Any]]:
    if detail != "rich" or rng.random() < 0.55:
        return []
    n = rng.randint(1, 2)
    kinds = [
        "Engineering review",
        "Parts return RMA",
        "Customer callback",
        "Remote log pull",
        "PM reminder",
    ]
    return [
        {
            "type": rng.choice(kinds),
            "due_days": rng.randint(3, 45),
            "owner": rng.choice(FE_FIRST),
        }
        for _ in range(n)
    ]


def generate_repairs_for_system(
    system: SystemKey,
    cfg: RepairConfig,
    *,
    rng: Random | None = None,
) -> list[dict[str, Any]]:
    """Generate a variable-length, variable-detail repair history for one system."""
    local = rng or Random(
        (cfg.seed or 0)
        ^ _stable_seed(system.sysid, system.machine_type, system.sw_version)
    )
    end = cfg.history_end or datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    span_days = _history_span_days(local, system.machine_type)
    start = end - timedelta(days=span_days)
    n = _repair_count(local, span_days, cfg)

    # Spread close times unevenly across the span.
    close_offsets = sorted(local.uniform(0.0, float(span_days)) for _ in range(n))
    docs: list[dict[str, Any]] = []

    for i, offset in enumerate(close_offsets):
        detail = _choose_detail(local, cfg.detail_mix)
        entry = local.choice(REPAIR_CATALOG)
        # Demo systems skew toward PM / SW; clinical toward hardware.
        if system.machine_type == "Demo" and local.random() < 0.35:
            entry = next(e for e in REPAIR_CATALOG if e["failure_code"] == "PM-SCHEDULED")
        closed = start + timedelta(days=offset, hours=local.uniform(6, 20))
        # Open duration varies with detail / priority.
        priority = local.choices(PRIORITIES, weights=PRIORITY_WEIGHTS, k=1)[0]
        if priority.startswith("P1"):
            open_hours = local.uniform(2, 36)
        elif priority.startswith("P2"):
            open_hours = local.uniform(8, 96)
        elif priority == "P5-PM":
            open_hours = local.uniform(4, 48)
        else:
            open_hours = local.uniform(12, 240)
        opened = closed - timedelta(hours=open_hours)
        status = local.choice(STATUSES)
        fe = local.choice(FE_FIRST)
        visit = local.choice(VISIT_TYPES)
        resolution = local.choice(entry["resolutions"])
        work_order = _work_order_id(local, closed)
        labor = round(local.uniform(0.5, 14.0), 1)
        if detail == "sparse":
            labor = round(local.uniform(0.5, 4.0), 1)

        doc: dict[str, Any] = {
            "@timestamp": _iso(closed),
            "_id": _repair_doc_id(system.sysid, work_order),
            "_index": cfg.index,
            "record_type": "repair",
            "work_order_id": work_order,
            "repair_sequence": i + 1,
            "repair_count_for_system": n,
            "detail_level": detail,
            "status": status,
            "priority": priority,
            "visit_type": visit,
            "opened_at": _iso(opened),
            "closed_at": _iso(closed),
            "duration_hours": round((closed - opened).total_seconds() / 3600.0, 2),
            "history_span_days": span_days,
            "sysid": system.sysid,
            "machine_type": system.machine_type,
            "sw_version": system.sw_version,
            "application_sw_release_id": system.application_sw_release_id
            or system.sw_version,
            "productName": system.product_name,
            "systype": system.systype,
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
            "log_type": system.log_type,
            "symptom": entry["symptom"],
            "failure_code": entry["failure_code"],
            "subsystem": entry["subsystem"],
            "resolution": resolution,
            "field_engineer": fe,
            "source_indicator_index": cfg.source_indicator_index,
            "source_indicator_doc_count": system.indicator_doc_count,
            "synthetic": True,
            "es_load_ts": _iso(datetime.now(timezone.utc)),
        }
        if system.install_date:
            doc["installDate"] = system.install_date

        if detail in ("standard", "rich"):
            doc["labor_hours"] = labor
            doc["parts_replaced"] = _parts_payload(local, entry, detail)
            doc["warranty_covered"] = local.random() < 0.6
            doc["travel_required"] = visit == "Onsite"
            doc["root_cause"] = (
                f"{entry['subsystem']} fault ({entry['failure_code']}) "
                f"on {system.systype or 'CT'} running {system.sw_version}"
            )

        if detail == "rich":
            doc["notes"] = _notes(
                local,
                detail=detail,
                symptom=entry["symptom"],
                resolution=resolution,
                subsystem=entry["subsystem"],
                fe=fe,
            )
            doc["follow_ups"] = _follow_ups(local, detail)
            doc["qa_checks"] = {
                "detector_lpp": local.choice(["PASS", "PASS", "PASS", "N/A"]),
                "air_kerma": local.choice(["PASS", "PASS", "N/A"]),
                "collimation": local.choice(["PASS", "PASS", "PASS", "N/A"]),
                "safety_interlocks": "PASS" if status == "Closed" else "N/A",
            }
            doc["customer_impact"] = local.choice(
                [
                    "Scanner down during visit",
                    "Reduced throughput; redirected exams",
                    "No clinical impact (PM window)",
                    "Single protocol unavailable",
                    "Intermittent abort; clinical ops continued",
                ]
            )
            if local.random() < 0.4:
                doc["related_case_id"] = f"SR-{local.randint(10_000_000, 99_999_999)}"
        elif detail == "standard":
            doc["notes"] = _notes(
                local,
                detail=detail,
                symptom=entry["symptom"],
                resolution=resolution,
                subsystem=entry["subsystem"],
                fe=fe,
            )
        # sparse: only core fields already set

        doc["semantic_search"] = repair_semantic_text(doc)
        docs.append(doc)

    return docs


def generate_repair_history(cfg: RepairConfig) -> list[dict[str, Any]]:
    """Generate repair docs for every system key in the config."""
    if not cfg.systems:
        return []
    base_rng = Random(cfg.seed)
    all_docs: list[dict[str, Any]] = []
    for system in cfg.systems:
        # Independent stream per system, still reproducible from cfg.seed.
        sys_rng = Random(
            base_rng.randint(0, 2**31 - 1)
            ^ _stable_seed(system.sysid, system.machine_type, system.sw_version)
        )
        all_docs.extend(generate_repairs_for_system(system, cfg, rng=sys_rng))
    # Stable-ish ordering by close time then sysid.
    all_docs.sort(key=lambda d: (d["@timestamp"], d["sysid"], d["work_order_id"]))
    # Ensure unique ids if collision (extremely unlikely).
    seen: set[str] = set()
    for doc in all_docs:
        doc_id = doc["_id"]
        if doc_id in seen:
            doc["_id"] = uuid.uuid4().hex[:20]
        seen.add(doc["_id"])
    return all_docs


def summarize_repairs(docs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_sys: dict[str, int] = {}
    by_detail: dict[str, int] = {}
    by_machine: dict[str, int] = {}
    for d in docs:
        by_sys[d["sysid"]] = by_sys.get(d["sysid"], 0) + 1
        by_detail[d["detail_level"]] = by_detail.get(d["detail_level"], 0) + 1
        by_machine[d["machine_type"]] = by_machine.get(d["machine_type"], 0) + 1
    timestamps = [d["@timestamp"] for d in docs]
    return {
        "repairs": len(docs),
        "systems": len(by_sys),
        "by_detail_level": dict(sorted(by_detail.items())),
        "by_machine_type": dict(sorted(by_machine.items())),
        "repairs_per_sysid": dict(sorted(by_sys.items())),
        "earliest": min(timestamps) if timestamps else None,
        "latest": max(timestamps) if timestamps else None,
    }
