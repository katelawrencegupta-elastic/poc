"""Detector LPP / honeycomb map factory.

Profiles `sample_data/mock_sample_honeycombdata_elastic (1).json`:

- Root: `{<session_uuid>: {<N>mm, map}, specid, status}`
- FAIL sample: 184 modules with bad pixels (ids ~2–192, a few gaps),
  `is_bad_count` 891, pixels/module skewed ~1–6 (median 4, max 17),
  `failed_modules: [13]`, collimation 80, `system_lpp_map`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from random import Random
from typing import Any, Literal, Sequence


Status = Literal["pass", "fail"]

# Empirical pixels-per-module histogram from the golden FAIL sample
# (mock_sample_honeycombdata_elastic). Mean ≈ 4.84, median 4.
SAMPLE_PIXEL_COUNT_WEIGHTS: dict[int, int] = {
    1: 17,
    2: 23,
    3: 19,
    4: 43,
    5: 23,
    6: 15,
    7: 11,
    8: 14,
    9: 8,
    10: 2,
    11: 5,
    12: 1,
    13: 1,
    16: 1,
    17: 1,
}

SAMPLE_MODULE_ID_MIN = 2
SAMPLE_MODULE_ID_MAX = 192
SAMPLE_BAD_MODULE_COUNT = 184
SAMPLE_PIXEL_ID_MIN = 6
SAMPLE_PIXEL_ID_MAX = 2487
SAMPLE_FAILED_MODULES = [13]
SAMPLE_DATASET = "cal-data-mode-pcd-non-spectral"
SAMPLE_VECTOR_TYPE = "system_lpp_map"
SAMPLE_SPECID = "sysService_v1"


@dataclass
class HoneycombConfig:
    """Controls for synthetic detector LPP map generation."""

    status: Status = "fail"
    collimation: str = "80"
    dataset: str = SAMPLE_DATASET
    vector_type: str = SAMPLE_VECTOR_TYPE
    specid: str = SAMPLE_SPECID
    session_id: str | None = None
    module_id_min: int = SAMPLE_MODULE_ID_MIN
    module_id_max: int = SAMPLE_MODULE_ID_MAX
    """Inclusive module id range matching sample (~2–192)."""
    bad_module_count: int | None = None
    """Modules with ≥1 bad pixel. Defaults: 0 for pass, 184 for fail (sample-like)."""
    bad_pixels_per_module: tuple[int, int] = (1, 17)
    """Uniform fallback range when ``pixel_count_weights`` is None and
    ``use_sample_pixel_distribution`` is False."""
    use_sample_pixel_distribution: bool = True
    """When True (default), draw pixels/module from the golden-sample histogram."""
    pixel_count_weights: dict[int, int] | None = None
    """Optional override histogram ``{pixel_count: weight}``."""
    pixel_id_min: int = SAMPLE_PIXEL_ID_MIN
    pixel_id_max: int = SAMPLE_PIXEL_ID_MAX
    failed_modules: list[int] | None = None
    """Explicit failed modules for FAIL status. Default [13] when fail."""
    seed: int | None = 42
    # Optional site/system context for Elastic documents
    sysid: str | None = None
    hospital: str | None = None
    machine_type: str | None = None
    site_id: str | None = None
    product_name: str | None = None

    @classmethod
    def sample_fail(cls, *, seed: int | None = 42, **kwargs: Any) -> HoneycombConfig:
        """Preset matching the golden Elastic FAIL sample shape/stats."""
        return cls(
            status="fail",
            bad_module_count=SAMPLE_BAD_MODULE_COUNT,
            failed_modules=list(SAMPLE_FAILED_MODULES),
            use_sample_pixel_distribution=True,
            seed=seed,
            **kwargs,
        )

    @classmethod
    def sample_pass(cls, *, seed: int | None = 42, **kwargs: Any) -> HoneycombConfig:
        """Clean PASS map (empty ``is_bad``)."""
        return cls(
            status="pass",
            bad_module_count=0,
            failed_modules=[],
            seed=seed,
            **kwargs,
        )


@dataclass
class HoneycombSample:
    """Generated payload plus flat Elastic-oriented metadata."""

    payload: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)


def _validate(payload: dict[str, Any]) -> None:
    session_keys = [k for k in payload if k not in ("specid", "status")]
    if len(session_keys) != 1:
        raise ValueError("payload must contain exactly one session UUID key")
    node = payload[session_keys[0]]
    m = node["map"]
    is_bad: dict[str, list[int]] = m["is_bad"]
    counted = sum(len(v) for v in is_bad.values())
    if counted != m["is_bad_count"]:
        raise AssertionError(
            f"is_bad_count {m['is_bad_count']} != sum(pixels) {counted}"
        )
    collimation = str(m["collimation"])
    mm_key = f"{collimation}mm"
    if mm_key not in node:
        raise AssertionError(f"missing collimation block {mm_key}")
    failed = node[mm_key].get("failed_modules", [])
    if node[mm_key]["status"] == "FAIL":
        for mod in failed:
            if str(mod) not in is_bad:
                raise AssertionError(
                    f"failed module {mod} not present in is_bad"
                )


def _draw_pixel_count(rng: Random, cfg: HoneycombConfig) -> int:
    weights = cfg.pixel_count_weights
    if weights is None and cfg.use_sample_pixel_distribution:
        weights = SAMPLE_PIXEL_COUNT_WEIGHTS
    if weights:
        choices = list(weights.keys())
        w = [weights[c] for c in choices]
        n_pix = rng.choices(choices, weights=w, k=1)[0]
    else:
        n_pix = rng.randint(*cfg.bad_pixels_per_module)
    span = cfg.pixel_id_max - cfg.pixel_id_min + 1
    return min(int(n_pix), span)


def generate_honeycomb(config: HoneycombConfig | None = None) -> dict[str, Any]:
    """Generate a sysService_v1-style detector LPP / honeycomb payload."""
    return generate_honeycomb_sample(config).payload


def generate_honeycomb_sample(
    config: HoneycombConfig | None = None,
) -> HoneycombSample:
    """Generate honeycomb payload with optional machine/site metadata."""
    cfg = config or HoneycombConfig()
    rng = Random(cfg.seed)
    session_id = cfg.session_id or str(uuid.UUID(int=rng.getrandbits(128)))

    if cfg.status == "pass":
        bad_module_count = 0 if cfg.bad_module_count is None else cfg.bad_module_count
        failed_modules: list[int] = (
            [] if cfg.failed_modules is None else list(cfg.failed_modules)
        )
        mm_status = "PASS"
        root_status = "pass"
    else:
        bad_module_count = (
            SAMPLE_BAD_MODULE_COUNT
            if cfg.bad_module_count is None
            else cfg.bad_module_count
        )
        failed_modules = (
            list(SAMPLE_FAILED_MODULES)
            if cfg.failed_modules is None
            else list(cfg.failed_modules)
        )
        mm_status = "FAIL"
        root_status = "fail"

    module_pool = list(range(cfg.module_id_min, cfg.module_id_max + 1))
    if bad_module_count > len(module_pool):
        raise ValueError(
            f"bad_module_count {bad_module_count} exceeds module pool {len(module_pool)}"
        )

    chosen: set[int] = set()
    for mod in failed_modules:
        if mod < cfg.module_id_min or mod > cfg.module_id_max:
            raise ValueError(f"failed module {mod} outside module range")
        chosen.add(mod)

    remaining_needed = max(0, bad_module_count - len(chosen))
    candidates = [m for m in module_pool if m not in chosen]
    if remaining_needed:
        chosen.update(rng.sample(candidates, remaining_needed))

    if len(chosen) > bad_module_count:
        keep = set(failed_modules)
        extras = [m for m in chosen if m not in keep]
        need = max(0, bad_module_count - len(keep))
        chosen = keep.union(extras[:need]) if need else keep

    is_bad: dict[str, list[int]] = {}
    for mod in sorted(chosen):
        n_pix = _draw_pixel_count(rng, cfg)
        pixels = sorted(
            rng.sample(range(cfg.pixel_id_min, cfg.pixel_id_max + 1), n_pix)
        )
        is_bad[str(mod)] = pixels

    bad_count = sum(len(v) for v in is_bad.values())
    collimation = str(cfg.collimation)
    mm_key = f"{collimation}mm"

    payload: dict[str, Any] = {
        session_id: {
            mm_key: {
                "failed_modules": failed_modules,
                "status": mm_status,
            },
            "map": {
                "collimation": collimation,
                "dataset": cfg.dataset,
                "is_bad": is_bad,
                "is_bad_count": bad_count,
                "vector_type": cfg.vector_type,
            },
        },
        "specid": cfg.specid,
        "status": root_status,
    }
    _validate(payload)

    meta = {
        "sysid": cfg.sysid,
        "hospital": cfg.hospital,
        "machine_type": cfg.machine_type,
        "site_id": cfg.site_id,
        "productName": cfg.product_name,
    }
    meta = {k: v for k, v in meta.items() if v is not None}
    return HoneycombSample(payload=payload, meta=meta)


def generate_honeycomb_sample_set(
    *,
    count: int = 12,
    seed: int = 42,
    pass_ratio: float = 0.25,
    site_ids: Sequence[str] | None = None,
) -> list[HoneycombSample]:
    """Generate a mixed pass/fail sample set across fleet systems."""
    from . import catalogs_fleet

    rng = Random(seed)
    systems = list(
        catalogs_fleet.systems_for(
            site_ids=list(site_ids) if site_ids else None
        ).values()
    )
    if not systems:
        raise ValueError("no fleet systems available for honeycomb sample set")

    samples: list[HoneycombSample] = []
    for i in range(count):
        system = rng.choice(systems)
        assert system.site_id is not None
        site = catalogs_fleet.SITES[system.site_id]
        status: Status = "pass" if rng.random() < pass_ratio else "fail"
        if status == "fail":
            bad_modules = rng.randint(8, 60)
            failed = [rng.randint(2, 50)]
        else:
            bad_modules = 0
            failed = []

        cfg = HoneycombConfig(
            status=status,
            bad_module_count=bad_modules if status == "fail" else 0,
            failed_modules=failed if status == "fail" else [],
            seed=seed + i * 17,
            sysid=system.sysid,
            hospital=site.hospital,
            machine_type=system.machine_type or site.machine_type,
            site_id=system.site_id,
            product_name=system.product_name,
        )
        samples.append(generate_honeycomb_sample(cfg))
    return samples
