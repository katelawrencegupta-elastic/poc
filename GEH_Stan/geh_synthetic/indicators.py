"""Session-aware CT dynamic indicator event factory."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Iterable, Literal, Sequence

from . import catalogs, catalogs_fleet
from .models import IndicatorEvent, SiteProfile, SystemProfile

ProfileName = Literal["lab", "fleet"]


@dataclass
class IndicatorConfig:
    """Controls for synthetic indicator generation."""

    sessions: int = 1
    exams_per_session: tuple[int, int] = (1, 3)
    collateral_per_exam: tuple[int, int] = (0, 4)
    error_rate: float = 1.0
    """Scale factor for collateral/fault events (1.0 ≈ sample density)."""
    profile: ProfileName = "lab"
    """lab = GEHQ sample catalog; fleet = 6 synthetic multi-hospital sites."""
    sysids: Sequence[str] | None = None
    site_ids: Sequence[str] | None = None
    """Fleet only: filter by hospital site_id."""
    machine_types: Sequence[str] | None = None
    """Fleet only: filter Internal / Clinical / Demo."""
    site: SiteProfile | None = None
    """Lab only: override the single GEHQ site profile."""
    start: datetime | None = None
    index_prefix: str = "ct_sitedata_ext2_indicator_events_m"
    seed: int | None = 42
    include_patient_session: bool = True
    es_style: bool = True
    critical_bias: float = 1.0
    """Boost reli_error_code volume and Critical severity (1.0 = sample mix)."""


def _weighted_choice(rng: Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    vals = list(weights.values())
    return rng.choices(keys, weights=vals, k=1)[0]


def _collateral_weights(critical_bias: float) -> dict[str, float]:
    weights = dict(catalogs.EXAM_COLLATERAL_WEIGHTS)
    if critical_bias != 1.0:
        weights["reli_error_code"] = weights.get("reli_error_code", 0.28) * critical_bias
    return weights


def _severity_for(rng: Random, event_type: str, *, critical_bias: float = 1.0) -> str:
    if event_type in catalogs.FIXED_SEVERITY:
        return catalogs.FIXED_SEVERITY[event_type]
    table = catalogs.SEVERITY_WEIGHTS.get(event_type)
    if table:
        if event_type == "reli_error_code" and critical_bias > 1.0:
            # Shift mass toward Critical while keeping other buckets.
            boosted = dict(table)
            boosted["Critical"] = boosted.get("Critical", 0.0) * critical_bias
            return _weighted_choice(rng, boosted)
        return _weighted_choice(rng, table)
    return "Informational"


def _message(rng: Random, event_type: str, *, exam: str, protocol: str) -> str:
    templates = catalogs.MESSAGES.get(event_type, [event_type.replace("_", " ")])
    template = rng.choice(templates)
    protocol_short = protocol.split(" ", 1)[-1] if " " in protocol else protocol
    return template.format(
        exam=exam,
        protocol=protocol,
        protocol_short=protocol_short,
    )


def _indicator_id(rng: Random) -> str:
    return str(rng.randint(1_000_000_000_000, 1_099_999_999_999))


def _doc_id() -> str:
    return uuid.uuid4().hex[:20]


def _index_name(prefix: str, when: datetime) -> str:
    return f"{prefix}-{when.year:04d}.{when.month:02d}.01"


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _random_exam_number(rng: Random, used: set[str]) -> str:
    """Fleet scheme: random zero-padded 3-digit exam number (000–999)."""
    for _ in range(200):
        n = f"{rng.randint(0, 999):03d}"
        if n not in used:
            used.add(n)
            return n
    # Extremely unlikely exhaustion within one generator run.
    n = f"{rng.randint(0, 999):03d}{rng.randint(0, 9)}"
    used.add(n)
    return n


def _apply_site(event: IndicatorEvent, site: SiteProfile) -> None:
    event.hospital = site.hospital
    event.customer = site.customer
    event.city = site.city
    event.state = site.state
    event.country = site.country
    event.region = site.region
    event.zone = site.zone
    event.zipcode = site.zipcode
    event.latitude = site.latitude
    event.longitude = site.longitude
    event.location = site.location
    event.machine_type = site.machine_type
    event.log_type = site.log_type


def _apply_system(event: IndicatorEvent, system: SystemProfile) -> None:
    event.sysid = system.sysid
    event.product_name = system.product_name
    event.systype = system.systype
    event.sw_version = system.sw_version
    event.application_sw_release_id = system.sw_version
    event.install_date = system.install_date
    event.max_warranty_start_date = system.max_warranty_start_date
    if system.machine_type:
        event.machine_type = system.machine_type


def _build_event(
    rng: Random,
    *,
    when: datetime,
    system: SystemProfile,
    site: SiteProfile,
    event_type: str,
    exam_number: str,
    anatomy: str,
    protocol_category: str,
    protocol_name: str,
    batch_from: datetime,
    batch_to: datetime,
    index_prefix: str,
    critical_bias: float = 1.0,
) -> IndicatorEvent:
    severity = _severity_for(rng, event_type, critical_bias=critical_bias)
    message = _message(rng, event_type, exam=exam_number, protocol=protocol_name)
    ifr_name = catalogs.IFR_EVENT_NAMES.get(event_type, event_type)
    event = IndicatorEvent(
        timestamp=_iso(when),
        sysid=system.sysid,
        event_type=event_type,
        indicator_severity=severity,
        indicator_id=_indicator_id(rng),
        indicator_message=message,
        exam_number=exam_number,
        anatomy=anatomy,
        protocol_category=protocol_category,
        product_name=system.product_name,
        systype=system.systype,
        sw_version=system.sw_version,
        application_sw_release_id=system.sw_version,
        ifr_event_name=ifr_name,
        ifr_event_protocol_name=protocol_name,
        event_data=f"{exam_number} {message[:80]}",
        batch_from_date=_iso(batch_from),
        batch_to_date=_iso(batch_to),
        es_load_ts=_iso(when + timedelta(minutes=5)),
        id=_doc_id(),
        index=_index_name(index_prefix, when),
    )
    _apply_site(event, site)
    _apply_system(event, system)
    return event


def _pick_protocol(rng: Random) -> tuple[str, str, str]:
    category, name, anatomy_hint = rng.choice(catalogs.PROTOCOLS)
    if rng.random() < 0.75:
        anatomy = anatomy_hint
    else:
        anatomy = _weighted_choice(rng, catalogs.ANATOMY_WEIGHTS)
    return category, name, anatomy


def _pick_lab_system(
    rng: Random, sysids: Sequence[str] | None
) -> tuple[SystemProfile, SiteProfile]:
    if sysids:
        sysid = rng.choice(list(sysids))
        if sysid not in catalogs.SYSTEMS:
            raise KeyError(
                f"Unknown lab sysid {sysid!r}; known: {sorted(catalogs.SYSTEMS)}"
            )
        return catalogs.SYSTEMS[sysid], catalogs.DEFAULT_SITE
    sysid = _weighted_choice(rng, catalogs.SYSTEM_WEIGHTS)
    return catalogs.SYSTEMS[sysid], catalogs.DEFAULT_SITE


def _pick_fleet_system(
    rng: Random,
    *,
    sysids: Sequence[str] | None,
    site_ids: Sequence[str] | None,
    machine_types: Sequence[str] | None,
) -> tuple[SystemProfile, SiteProfile]:
    filtered = catalogs_fleet.systems_for(
        site_ids=list(site_ids) if site_ids else None,
        machine_types=list(machine_types) if machine_types else None,
        sysids=list(sysids) if sysids else None,
    )
    if not filtered:
        raise ValueError(
            "No fleet systems match filters "
            f"(site_ids={site_ids!r}, machine_types={machine_types!r}, sysids={sysids!r})"
        )
    weights = {
        sid: catalogs_fleet.SYSTEM_WEIGHTS.get(sid, 1.0) for sid in filtered
    }
    sysid = _weighted_choice(rng, weights)
    system = filtered[sysid]
    assert system.site_id is not None
    site = catalogs_fleet.SITES[system.site_id]
    return system, site


def generate_indicator_events(
    config: IndicatorConfig | None = None,
) -> list[IndicatorEvent]:
    """Generate session-narrative indicator events (lab or fleet profile)."""
    cfg = config or IndicatorConfig()
    rng = Random(cfg.seed)
    cursor = cfg.start or datetime(2026, 7, 9, 8, 0, 0, tzinfo=timezone.utc)
    events: list[IndicatorEvent] = []
    used_exams: set[str] = set()
    # Lab keeps legacy rising counter; fleet uses random 3-digit scheme.
    exam_counter = rng.randint(100, 400)

    for _ in range(cfg.sessions):
        if cfg.profile == "fleet":
            system, site = _pick_fleet_system(
                rng,
                sysids=cfg.sysids,
                site_ids=cfg.site_ids,
                machine_types=cfg.machine_types,
            )
        else:
            system, default_site = _pick_lab_system(rng, cfg.sysids)
            site = cfg.site or default_site

        session_start = cursor
        n_exams = rng.randint(*cfg.exams_per_session)
        batch_from = session_start.replace(
            hour=12, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        batch_to = batch_from + timedelta(days=1)

        cat0, proto0, anat0 = _pick_protocol(rng)
        if cfg.profile == "fleet":
            session_exam = _random_exam_number(rng, used_exams)
        else:
            exam_counter += 1
            session_exam = str(exam_counter)

        if cfg.include_patient_session:
            events.append(
                _build_event(
                    rng,
                    when=cursor,
                    system=system,
                    site=site,
                    event_type="start_patient_session",
                    exam_number=session_exam,
                    anatomy=anat0,
                    protocol_category=cat0,
                    protocol_name=proto0,
                    batch_from=batch_from,
                    batch_to=batch_to,
                    index_prefix=cfg.index_prefix,
                    critical_bias=cfg.critical_bias,
                )
            )
            cursor += timedelta(seconds=rng.randint(5, 40))

        collateral_weights = _collateral_weights(cfg.critical_bias)
        for _exam_i in range(n_exams):
            if cfg.profile == "fleet":
                exam_number = _random_exam_number(rng, used_exams)
            else:
                exam_counter += 1
                exam_number = str(exam_counter)
            category, protocol_name, anatomy = _pick_protocol(rng)

            events.append(
                _build_event(
                    rng,
                    when=cursor,
                    system=system,
                    site=site,
                    event_type="Exam_start",
                    exam_number=exam_number,
                    anatomy=anatomy,
                    protocol_category=category,
                    protocol_name=protocol_name,
                    batch_from=batch_from,
                    batch_to=batch_to,
                    index_prefix=cfg.index_prefix,
                    critical_bias=cfg.critical_bias,
                )
            )
            cursor += timedelta(seconds=rng.randint(10, 90))

            base_collateral = rng.randint(*cfg.collateral_per_exam)
            n_collateral = max(0, int(round(base_collateral * cfg.error_rate)))
            for _ in range(n_collateral):
                event_type = _weighted_choice(rng, collateral_weights)
                events.append(
                    _build_event(
                        rng,
                        when=cursor,
                        system=system,
                        site=site,
                        event_type=event_type,
                        exam_number=exam_number,
                        anatomy=anatomy,
                        protocol_category=category,
                        protocol_name=protocol_name,
                        batch_from=batch_from,
                        batch_to=batch_to,
                        index_prefix=cfg.index_prefix,
                        critical_bias=cfg.critical_bias,
                    )
                )
                cursor += timedelta(seconds=rng.randint(2, 45))
                if event_type == "gantry_subsystems_reseting" and rng.random() < 0.7:
                    events.append(
                        _build_event(
                            rng,
                            when=cursor,
                            system=system,
                            site=site,
                            event_type="gantry_subsystem_ready",
                            exam_number=exam_number,
                            anatomy=anatomy,
                            protocol_category=category,
                            protocol_name=protocol_name,
                            batch_from=batch_from,
                            batch_to=batch_to,
                            index_prefix=cfg.index_prefix,
                            critical_bias=cfg.critical_bias,
                        )
                    )
                    cursor += timedelta(seconds=rng.randint(3, 20))

            events.append(
                _build_event(
                    rng,
                    when=cursor,
                    system=system,
                    site=site,
                    event_type="Exam_end",
                    exam_number=exam_number,
                    anatomy=anatomy,
                    protocol_category=category,
                    protocol_name=protocol_name,
                    batch_from=batch_from,
                    batch_to=batch_to,
                    index_prefix=cfg.index_prefix,
                    critical_bias=cfg.critical_bias,
                )
            )
            cursor += timedelta(seconds=rng.randint(30, 180))

        cursor += timedelta(minutes=rng.randint(5, 60))

    events.sort(key=lambda e: e.timestamp)
    return events


def events_to_dicts(
    events: Iterable[IndicatorEvent],
    *,
    es_style: bool = True,
) -> list[dict]:
    return [e.to_dict(es_style=es_style) for e in events]
