"""Lightweight invariants for the factories (stdlib only)."""

from __future__ import annotations

import re

from .catalogs_fleet import MACHINE_TYPES, SITES
from .honeycomb import HoneycombConfig, generate_honeycomb
from .indicators import IndicatorConfig, generate_indicator_events


def main() -> None:
    events = generate_indicator_events(
        IndicatorConfig(sessions=3, seed=7, sysids=["CTBAY47", "CTBAY52WSO"])
    )
    assert events, "expected events"
    assert all(e.indicator_id.isdigit() for e in events)
    assert all("E+" not in e.indicator_id for e in events)
    assert any(e.event_type == "start_patient_session" for e in events)
    assert any(e.event_type == "Exam_start" for e in events)
    assert any(e.event_type == "Exam_end" for e in events)
    starts = {e.exam_number for e in events if e.event_type == "Exam_start"}
    ends = {e.exam_number for e in events if e.event_type == "Exam_end"}
    assert starts == ends

    fleet = generate_indicator_events(
        IndicatorConfig(profile="fleet", sessions=40, seed=11)
    )
    hospitals = {e.hospital for e in fleet}
    machine_types = {e.machine_type for e in fleet}
    assert len(SITES) >= 18
    assert len(hospitals) >= 3, hospitals
    assert machine_types <= set(MACHINE_TYPES)
    assert machine_types & {"Internal", "Clinical", "Demo"}
    exam_re = re.compile(r"^\d{3}$")
    exam_nums = {e.exam_number for e in fleet if e.event_type == "Exam_start"}
    assert exam_nums, "expected fleet exams"
    assert all(exam_re.match(n) for n in exam_nums), exam_nums
    f_starts = {e.exam_number for e in fleet if e.event_type == "Exam_start"}
    f_ends = {e.exam_number for e in fleet if e.event_type == "Exam_end"}
    assert f_starts == f_ends

    clinical_only = generate_indicator_events(
        IndicatorConfig(
            profile="fleet",
            sessions=10,
            machine_types=["Clinical"],
            seed=12,
        )
    )
    assert clinical_only
    assert all(e.machine_type == "Clinical" for e in clinical_only)

    demo_only = generate_indicator_events(
        IndicatorConfig(
            profile="fleet",
            sessions=5,
            machine_types=["Demo"],
            seed=13,
        )
    )
    assert demo_only
    assert all(e.machine_type == "Demo" for e in demo_only)
    assert {e.sysid for e in demo_only} <= {
        "CTCSM22D",
        "CTCHA42D",
        "CTJHH62D",
        "CTMSN82D",
        "CTNMH02D",
        "CTSKH02D",
    }

    fail = generate_honeycomb(
        HoneycombConfig(status="fail", bad_module_count=12, seed=9)
    )
    uid = next(k for k in fail if k not in ("specid", "status"))
    assert fail["status"] == "fail"
    assert fail[uid]["map"]["is_bad_count"] == sum(
        len(v) for v in fail[uid]["map"]["is_bad"].values()
    )

    ok = generate_honeycomb(HoneycombConfig(status="pass", seed=9))
    uid = next(k for k in ok if k not in ("specid", "status"))
    assert ok["status"] == "pass"
    assert ok[uid]["map"]["is_bad_count"] == 0
    assert ok[uid]["80mm"]["status"] == "PASS"

    golden = generate_honeycomb(HoneycombConfig.sample_fail(seed=42))
    g_uid = next(k for k in golden if k not in ("specid", "status"))
    g_map = golden[g_uid]["map"]
    assert len(g_map["is_bad"]) == 184
    assert golden[g_uid]["80mm"]["failed_modules"] == [13]
    pix_counts = [len(v) for v in g_map["is_bad"].values()]
    mean_pix = sum(pix_counts) / len(pix_counts)
    assert 3.5 <= mean_pix <= 6.5, mean_pix  # sample mean ≈ 4.84

    from .elastic import honeycomb_to_documents

    docs = honeycomb_to_documents(golden)
    assert len(docs) == 184
    assert all(d["record_type"] == "module" for d in docs)
    assert docs[0]["module_id"] < docs[-1]["module_id"]
    assert sum(d["pixel_count"] for d in docs) == docs[0]["is_bad_count"]
    assert all(d["session_id"] == g_uid for d in docs)
    assert any(d["is_failed_module"] for d in docs if d["module_id"] == 13)
    assert len({d["_id"] for d in docs}) == 184

    pass_docs = honeycomb_to_documents(ok)
    assert len(pass_docs) == 1
    assert pass_docs[0]["record_type"] == "session"

    print(
        f"selfcheck ok: lab={len(events)} fleet={len(fleet)} "
        f"hospitals={sorted(hospitals)} machine_types={sorted(machine_types)} "
        f"honeycomb_mean_pix={mean_pix:.2f} honeycomb_docs={len(docs)}"
    )


if __name__ == "__main__":
    main()
