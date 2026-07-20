"""Synthetic CT telemetry factories for GEH testing."""

from .honeycomb import (
    HoneycombConfig,
    HoneycombSample,
    generate_honeycomb,
    generate_honeycomb_sample,
    generate_honeycomb_sample_set,
)
from .indicators import IndicatorConfig, generate_indicator_events
from .elastic import (
    DEFAULT_ELASTIC_URL,
    DEFAULT_PARTS_INDEX,
    DEFAULT_REPAIR_INDEX,
    ElasticConfig,
    fetch_indicator_system_keys,
    honeycomb_to_documents,
    index_honeycomb,
    index_honeycomb_samples,
    index_indicator_events,
    index_parts,
    index_repairs,
)
from .parts import PartsConfig, generate_machine_parts, summarize_machine_parts
from .repairs import (
    RepairConfig,
    SystemKey,
    generate_repair_history,
    generate_repairs_for_system,
    summarize_repairs,
)

__all__ = [
    "DEFAULT_ELASTIC_URL",
    "DEFAULT_PARTS_INDEX",
    "DEFAULT_REPAIR_INDEX",
    "ElasticConfig",
    "HoneycombConfig",
    "HoneycombSample",
    "IndicatorConfig",
    "PartsConfig",
    "RepairConfig",
    "SystemKey",
    "fetch_indicator_system_keys",
    "generate_honeycomb",
    "generate_honeycomb_sample",
    "generate_honeycomb_sample_set",
    "generate_indicator_events",
    "generate_machine_parts",
    "generate_repair_history",
    "generate_repairs_for_system",
    "honeycomb_to_documents",
    "index_honeycomb",
    "index_honeycomb_samples",
    "index_indicator_events",
    "index_parts",
    "index_repairs",
    "summarize_machine_parts",
    "summarize_repairs",
]

__version__ = "0.1.0"
