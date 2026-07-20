"""Short field-service device manuals for CT systypes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from .semantic import manual_semantic_text

DEFAULT_MANUAL_INDEX = "ct_device_manuals"
MANUAL_VERSION = "1.0"

# One short device manual per systype. Content is synthetic field-service
# guidance aligned with subsystems used in the repair catalog.
DEVICE_MANUALS: list[dict[str, Any]] = [
    {
        "manual_id": "revct-short-v1",
        "title": "Revolution CT Short Device Manual",
        "systype": "Revolution CT",
        "productName": "Revolution CT (Rev 160)",
        "machine_family": "Revolution CT",
        "audience": "field_service",
        "doc_type": "short_device_manual",
        "sw_baselines": ["25MW38.x", "24MW*"],
        "overview": (
            "Revolution CT (Rev 160) is a wide-coverage CT platform used for "
            "cardiac, trauma, and general radiology workflows. This short manual "
            "covers safe power-up, daily checks, subsystem cues, and the most "
            "common field failures seen on Rev 160 fleets."
        ),
        "safety": (
            "Lock out gantry rotation and HV enable before opening covers. "
            "Confirm X-ray interlocks and laser alignment are clear before any "
            "exposure. Coolant loops and HV tank surfaces may be hot after high "
            "mA protocols. Follow site radiation safety and GE electrical lockout "
            "procedures; do not defeat door or thermal interlocks during service."
        ),
        "daily_checks": [
            "Console boot to clinical desktop with no persistent fault banners",
            "Gantry home / laser alignment visual check",
            "Table elevation and longitudinal travel end-to-end",
            "Cooling unit pressure and reservoir level within site sticker",
            "UPS self-test status PASS if available",
            "Quick air scan or phantom QA if site SOP requires",
        ],
        "sections": [
            {
                "heading": "Detector / LPP",
                "subsystem": "Detector",
                "body": (
                    "LPP / honeycomb maps flag elevated bad-pixel counts. On FAIL, "
                    "note failed module IDs, reseat DAS harnesses, and re-run flat "
                    "and LPP. Persistent single-module FAIL usually means module "
                    "replacement then recalibration. Banding on wide-collimation "
                    "abdomen helicals often tracks DAS channel boards rather than "
                    "the entire detector ring."
                ),
            },
            {
                "heading": "Gantry communication",
                "subsystem": "Gantry",
                "body": (
                    "Intermittent gantry telemetry during helical exams commonly "
                    "points to slip-ring brushes or encoder cabling. Capture "
                    "comm-drop timestamps, inspect brush wear, and verify continuous "
                    "telemetry on a soak helical before releasing the system."
                ),
            },
            {
                "heading": "HV / generator thermal",
                "subsystem": "HV / Generator",
                "body": (
                    "HV tank over-temp warnings and high-mA aborts: check HV cooling "
                    "fans, coolant filter, and duty-cycle limits. Flush and refill "
                    "only with approved coolant. After service, run a thermal soak "
                    "on high-mA protocols and confirm warnings clear."
                ),
            },
            {
                "heading": "Patient table",
                "subsystem": "Patient Table",
                "body": (
                    "Elevation stalls at mid-height are usually the vertical "
                    "actuator or limit switches. Verify end-stops, lubricate the "
                    "drive per PM, and test travel under load with a phantom or "
                    "weight bag before clinical return."
                ),
            },
            {
                "heading": "Collimator",
                "subsystem": "Collimator",
                "body": (
                    "Blade position mismatch vs commanded aperture: clean blade "
                    "guides, check motor and position sensor PCB, then recalibrate "
                    "apertures. Confirm collimation QA matches protocol settings "
                    "across 20/40/80 mm where applicable."
                ),
            },
            {
                "heading": "Host software / recon",
                "subsystem": "Host Software",
                "body": (
                    "Console crashes during recon: clear the recon queue, apply "
                    "the site-approved host SW patch, or roll to a known-good "
                    "build. Capture crash dumps before rebuilds. Validate a full "
                    "exam including recon soak before handoff."
                ),
            },
            {
                "heading": "X-ray tube",
                "subsystem": "X-Ray Tube",
                "body": (
                    "Arcing at elevated kV with generator fault dumps: review tube "
                    "hours, oil filter condition, and seasoning history. Oil "
                    "service plus seasoning often clears mild arcing; repeated "
                    "high-kV arcs after seasoning indicate tube insert replacement."
                ),
            },
            {
                "heading": "Cooling unit",
                "subsystem": "Cooling",
                "body": (
                    "Low cooling pressure trips scanner thermal interlocks. Check "
                    "pump cartridge, pressure sensor, and air in the loop. Top, "
                    "purge, and restore setpoints; verify interlock clear under "
                    "load before releasing."
                ),
            },
            {
                "heading": "Power / UPS",
                "subsystem": "Power",
                "body": (
                    "UPS battery self-test FAIL and power-quality alarms: replace "
                    "the 48 V battery pack if due, clear alarms, and confirm "
                    "self-test PASS. Investigate site mains quality if alarms "
                    "return with a healthy UPS."
                ),
            },
            {
                "heading": "Preventive maintenance",
                "subsystem": "Service",
                "body": (
                    "Annual PM uses kit PM-KIT-REVCT. Prioritize tube-hour "
                    "interval, cooling service, slip-ring inspection, laser "
                    "alignment, and detector flat/LPP. Record SW baseline and "
                    "QA results in the work order."
                ),
            },
        ],
        "common_faults": [
            {
                "failure_code": "DET-LPP-FAIL",
                "symptom": "Detector LPP calibration FAIL; elevated bad-pixel count",
                "first_actions": [
                    "Record failed module IDs from honeycomb map",
                    "Reseat DAS harness and re-run flat / LPP",
                    "Replace failed module if single-module FAIL persists",
                ],
            },
            {
                "failure_code": "GAN-COMM-INT",
                "symptom": "Gantry intermittent communication loss during helical exams",
                "first_actions": [
                    "Inspect slip-ring brushes and encoder cable",
                    "Run soak helical and watch telemetry continuity",
                ],
            },
            {
                "failure_code": "HV-OT-WARN",
                "symptom": "HV tank over-temp warning; scan abort on high-mA protocols",
                "first_actions": [
                    "Check HV cooling fans and coolant filter",
                    "Thermal soak after service; confirm warnings clear",
                ],
            },
            {
                "failure_code": "CLU-PRESS-LO",
                "symptom": "Cooling unit pressure low; scanner thermal interlock",
                "first_actions": [
                    "Check pump, sensor, and coolant level",
                    "Purge air and restore pressure setpoints",
                ],
            },
            {
                "failure_code": "XR-ARC-HV",
                "symptom": "X-ray tube arcing at elevated kV; generator fault dump",
                "first_actions": [
                    "Review tube hours and oil service history",
                    "Season tube; replace insert if arcs persist",
                ],
            },
        ],
        "escalation": (
            "If faults recur after parts and calibration, capture logs "
            "(indicator events, LPP map, generator dumps) and escalate to "
            "product support with systype Revolution CT, productName "
            "Revolution CT (Rev 160), sysid, and SW version."
        ),
    },
    {
        "manual_id": "revapex-short-v1",
        "title": "Revolution Apex Short Device Manual",
        "systype": "Revolution Apex",
        "productName": "Revolution Apex Elite (160)",
        "machine_family": "Revolution Apex",
        "audience": "field_service",
        "doc_type": "short_device_manual",
        "sw_baselines": ["25MW38.x", "25MW*"],
        "overview": (
            "Revolution Apex Elite (160) extends the Revolution platform with "
            "higher workflow throughput and Apex Elite imaging options. This "
            "short manual focuses on field cues that differ in emphasis from "
            "base Rev CT—especially cooling under dense cardiac/ED loads, "
            "detector/DAS banding, and host recon stability on Apex builds."
        ),
        "safety": (
            "Same lockout rules as Revolution CT: gantry rotation, HV enable, "
            "and radiation interlocks before cover removal. Apex sites often "
            "run denser high-mA cardiac schedules—allow extra cool-down before "
            "HV tank or tube work. Never bypass thermal or door interlocks to "
            "clear a backlog of exams."
        ),
        "daily_checks": [
            "Host SW build matches site-approved Apex baseline",
            "No sticky cooling or HV thermal banners after overnight idle",
            "Table travel and elevation under clinical load profile",
            "Collimator aperture spot-check on cardiac and abdomen protocols",
            "UPS / power quality status",
            "Review overnight indicator severity if remote monitoring is enabled",
        ],
        "sections": [
            {
                "heading": "Detector / DAS image quality",
                "subsystem": "Detector / DAS",
                "body": (
                    "Apex Elite wide-coverage abdomen and cardiac helicals are "
                    "sensitive to DAS gain drift. Banding (IMG-BAND-ART) after "
                    "module work: recalibrate DAS gains and detector offsets "
                    "before swapping additional hardware. Honeycomb FAIL still "
                    "follows the Rev CT module-replace path."
                ),
            },
            {
                "heading": "Cooling under high utilization",
                "subsystem": "Cooling",
                "body": (
                    "Apex fleets in ED/cardiac rooms see CLU-PRESS-LO more often "
                    "when utilization is high. Treat low pressure as urgent: "
                    "thermal interlocks will stop scanning. Pump cartridge, "
                    "pressure sensor, purge, and setpoint restore are the usual "
                    "fix path; confirm pressure holds through a busy protocol set."
                ),
            },
            {
                "heading": "HV / generator",
                "subsystem": "HV / Generator",
                "body": (
                    "High-mA cardiac and dual-energy style loads stress HV cooling. "
                    "Fans, coolant filter, and duty-cycle calibration after any "
                    "HV-OT-WARN. Document ambient room temperature—Apex rooms "
                    "with marginal HVAC amplify tank warnings."
                ),
            },
            {
                "heading": "Gantry and slip ring",
                "subsystem": "Gantry",
                "body": (
                    "Helical comm drops (GAN-COMM-INT) on Apex: prioritize brush "
                    "condition on high-rotation cardiac schedules. Encoder cable "
                    "re-termination is the next step if brushes are within wear "
                    "spec. Require a continuous-telemetry soak before release."
                ),
            },
            {
                "heading": "Patient table",
                "subsystem": "Patient Table",
                "body": (
                    "Elevation faults (TBL-ELEV-FLT) interrupt trauma and cardiac "
                    "workflows quickly. Replace actuator / limit switches as on "
                    "Rev CT; add a loaded travel test that matches Apex cardiac "
                    "table heights used on site."
                ),
            },
            {
                "heading": "Collimator calibration",
                "subsystem": "Collimator",
                "body": (
                    "Position mismatch (COL-POS-MIS) affects dose and coverage "
                    "claims on Apex Elite protocols. After motor or sensor work, "
                    "recalibrate and verify apertures against cardiac and wide "
                    "abdomen protocol cards."
                ),
            },
            {
                "heading": "Host software / recon",
                "subsystem": "Host Software",
                "body": (
                    "SW-RECON-CRASH on Apex builds: prefer the site-approved "
                    "25MW38.x patch train before broad rebuilds. Clear recon "
                    "queues, restore configuration baseline, and validate "
                    "cardiac recon soak exams. Roll only to known-good Apex "
                    "builds documented for that hospital."
                ),
            },
            {
                "heading": "X-ray tube",
                "subsystem": "X-Ray Tube",
                "body": (
                    "Tube arcing (XR-ARC-HV) under elevated kV: Apex cardiac "
                    "kV profiles can expose marginal tubes sooner. Oil service "
                    "and seasoning first; replace insert when arcs survive "
                    "seasoning. Track tube hours against PM interval closely."
                ),
            },
            {
                "heading": "Power / UPS",
                "subsystem": "Power",
                "body": (
                    "UPS-BATT-FAIL and power-quality alarms: replace battery "
                    "pack, re-run self-test, and clear alarms. Apex scanners "
                    "with frequent generator dumps plus UPS alarms need a joint "
                    "power-quality review with facilities."
                ),
            },
            {
                "heading": "Preventive maintenance",
                "subsystem": "Service",
                "body": (
                    "Use the Apex-appropriate PM consumables kit (same family as "
                    "PM-KIT-REVCT unless site BOM differs). Emphasize cooling "
                    "loop, slip-ring brushes, tube hours, and detector/DAS "
                    "calibration. Record productName Revolution Apex Elite (160) "
                    "and SW version on every PM closeout."
                ),
            },
        ],
        "common_faults": [
            {
                "failure_code": "CLU-PRESS-LO",
                "symptom": "Cooling unit pressure low; scanner thermal interlock",
                "first_actions": [
                    "Treat as scan-stopping; check pump/sensor/level",
                    "Purge and restore setpoints; verify under busy protocol set",
                ],
            },
            {
                "failure_code": "IMG-BAND-ART",
                "symptom": "Image artifact banding on wide-collimation abdomen helical",
                "first_actions": [
                    "Recalibrate DAS gains and detector offsets",
                    "Replace DAS channel board if banding persists on QA phantom",
                ],
            },
            {
                "failure_code": "DET-LPP-FAIL",
                "symptom": "Detector LPP calibration FAIL; elevated bad-pixel count",
                "first_actions": [
                    "Note failed modules; reseat DAS; re-run LPP",
                    "Replace module and recalibrate if FAIL persists",
                ],
            },
            {
                "failure_code": "SW-RECON-CRASH",
                "symptom": "Console application crash during recon; exam incomplete",
                "first_actions": [
                    "Capture dump; clear recon queue",
                    "Apply approved Apex SW patch or known-good build",
                ],
            },
            {
                "failure_code": "HV-OT-WARN",
                "symptom": "HV tank over-temp warning; scan abort on high-mA protocols",
                "first_actions": [
                    "Inspect HV fans/filter; check room HVAC",
                    "Thermal soak on cardiac/high-mA protocols after fix",
                ],
            },
        ],
        "escalation": (
            "Escalate recurring Apex issues with logs, LPP/honeycomb export, "
            "and generator dumps. Include systype Revolution Apex, productName "
            "Revolution Apex Elite (160), sysid, machine_type, and SW version "
            "(typically 25MW38.x)."
        ),
    },
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _section_text(manual: dict[str, Any]) -> str:
    parts = [
        manual["title"],
        manual["overview"],
        "Safety: " + manual["safety"],
        "Daily checks: " + "; ".join(manual["daily_checks"]),
    ]
    for section in manual["sections"]:
        parts.append(f"{section['heading']}: {section['body']}")
    for fault in manual["common_faults"]:
        actions = "; ".join(fault["first_actions"])
        parts.append(
            f"{fault['failure_code']} — {fault['symptom']}. First actions: {actions}"
        )
    parts.append("Escalation: " + manual["escalation"])
    return "\n\n".join(parts)


def build_manual_document(
    manual: dict[str, Any],
    *,
    version: str = MANUAL_VERSION,
    index: str = DEFAULT_MANUAL_INDEX,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Turn a catalog manual into an Elasticsearch document."""
    when = timestamp or datetime.now(timezone.utc)
    ts = when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    subsystems = sorted({s["subsystem"] for s in manual["sections"]})
    failure_codes = [f["failure_code"] for f in manual["common_faults"]]
    content = _section_text(manual)
    doc = {
        "_id": manual["manual_id"],
        "_index": index,
        "@timestamp": ts,
        "es_load_ts": _utc_now_iso(),
        "record_type": "manual",
        "doc_type": manual["doc_type"],
        "manual_id": manual["manual_id"],
        "title": manual["title"],
        "version": version,
        "systype": manual["systype"],
        "productName": manual["productName"],
        "machine_family": manual["machine_family"],
        "audience": manual["audience"],
        "sw_baselines": list(manual["sw_baselines"]),
        "overview": manual["overview"],
        "safety": manual["safety"],
        "daily_checks": list(manual["daily_checks"]),
        "sections": list(manual["sections"]),
        "common_faults": list(manual["common_faults"]),
        "subsystems": subsystems,
        "failure_codes": failure_codes,
        "escalation": manual["escalation"],
        "content": content,
        "synthetic": True,
        "log_type": "device_manual",
    }
    doc["semantic_search"] = manual_semantic_text(doc)
    return doc


def generate_manuals(
    *,
    systypes: Sequence[str] | None = None,
    version: str = MANUAL_VERSION,
    index: str = DEFAULT_MANUAL_INDEX,
    timestamp: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build short device manual documents (default: both Revolution systypes)."""
    wanted = {s.lower() for s in systypes} if systypes else None
    docs: list[dict[str, Any]] = []
    for manual in DEVICE_MANUALS:
        if wanted is not None and manual["systype"].lower() not in wanted:
            continue
        docs.append(
            build_manual_document(
                manual, version=version, index=index, timestamp=timestamp
            )
        )
    if wanted is not None and not docs:
        raise ValueError(
            f"no manuals for systypes={list(systypes)!r}; "
            f"known: {[m['systype'] for m in DEVICE_MANUALS]}"
        )
    return docs


def summarize_manuals(docs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "manual_count": len(docs),
        "systypes": sorted({d["systype"] for d in docs}),
        "manual_ids": [d["manual_id"] for d in docs],
        "section_counts": {d["manual_id"]: len(d["sections"]) for d in docs},
    }
