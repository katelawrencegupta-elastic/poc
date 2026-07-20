from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SiteProfile:
    hospital: str = "GE MEDICAL SYSTEMS GLOBAL HEADQUARTERS"
    customer: str = "GE MEDICAL SYSTEMS GLOBAL HEADQUARTERS"
    city: str = "USA Other"
    state: str = "WI"
    country: str = "United States of America"
    region: str = "USCAN"
    zone: str = "USA Other"
    zipcode: str = "53188"
    latitude: str = "42.996"
    longitude: str = "-88.311"
    location: str = "POINT (-88.3115 42.9962)"
    machine_type: str = "Internal"
    log_type: str = "Revo_RTS_Data"
    site_id: str = "gehq"
    site_code: str = "GEHQ"


@dataclass(frozen=True)
class SystemProfile:
    sysid: str
    product_name: str
    systype: str
    sw_version: str = "25MW38.54"
    install_date: str = "2017-10-10T05:30:00.000Z"
    max_warranty_start_date: str = "2017-10-10T05:30:00.000Z"
    site_id: str | None = None
    machine_type: str | None = None
    """When set, overrides SiteProfile.machine_type on emit."""


@dataclass
class IndicatorEvent:
    """Logical indicator-event fields (no Kibana .keyword mirrors)."""

    timestamp: str
    sysid: str
    event_type: str
    indicator_severity: str
    indicator_id: str
    indicator_message: str
    exam_number: str
    anatomy: str
    protocol_category: str
    product_name: str
    systype: str
    sw_version: str
    application_sw_release_id: str
    sw_program: str = "unknown"
    event_data: str = "-"
    ifr_event_name: str = "Unknown"
    ifr_event_category: str = "Unknown"
    ifr_event_data: str = "N/A"
    ifr_event_protocol_name: str = "Unknown"
    ifr_main_event: str = "N/A"
    ifr90_alert: str = "N"
    global_order_number: str = "-"
    fec_attempt_no: str = "-"
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
    machine_type: str = "Internal"
    log_type: str = "Revo_RTS_Data"
    install_date: str = ""
    max_warranty_start_date: str = ""
    batch_from_date: str = ""
    batch_to_date: str = ""
    es_load_ts: str = ""
    id: str = ""
    index: str = ""
    score: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, es_style: bool = False) -> dict[str, Any]:
        """Serialize to clean domain dict, or ES-oriented field names."""
        if es_style:
            payload = {
                "@timestamp": self.timestamp,
                "_id": self.id,
                "_index": self.index,
                "_score": self.score,
                "FEC_attempt_no": self.fec_attempt_no,
                "anatomy": self.anatomy,
                "application_sw_release_id": self.application_sw_release_id,
                "batch_from_date": self.batch_from_date,
                "batch_to_date": self.batch_to_date,
                "city": self.city,
                "country": self.country,
                "customer": self.customer,
                "es_load_ts": self.es_load_ts,
                "event_data": self.event_data,
                "event_type": self.event_type,
                "exam_number": self.exam_number,
                "globalOrderNumber": self.global_order_number,
                "hospital": self.hospital,
                "ifr90_alert": self.ifr90_alert,
                "ifr_event_category": self.ifr_event_category,
                "ifr_event_data": self.ifr_event_data,
                "ifr_event_name": self.ifr_event_name,
                "ifr_event_protocol_name": self.ifr_event_protocol_name,
                "ifr_main_event": self.ifr_main_event,
                "indicator_id": self.indicator_id,
                "indicator_message": self.indicator_message,
                "indicator_severity": self.indicator_severity,
                "installDate": self.install_date,
                "latitude": self.latitude,
                "location": self.location,
                "log_type": self.log_type,
                "longitude": self.longitude,
                "machine_type": self.machine_type,
                "max_warranty_startDate": self.max_warranty_start_date,
                "productName": self.product_name,
                "protocol_category": self.protocol_category,
                "region": self.region,
                "state": self.state,
                "sw_program": self.sw_program,
                "sw_version": self.sw_version,
                "sysid": self.sysid,
                "systype": self.systype,
                "zipcode": self.zipcode,
                "zone": self.zone,
            }
        else:
            payload = asdict(self)
            payload.pop("extras", None)
            payload.update(self.extras)
        return payload
