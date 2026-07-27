# GEH synthetic telemetry

Factories for **CT dynamic indicator events** and **detector LPP / honeycomb** maps, profiled from `sample_data/`.

The two streams are separate schemas (no join keys in the samples). Generate them independently; correlate only if your test invents a link (e.g. `sysid` + calibration time).

## Install

```bash
pip install -e .
# or just run as a module with no install:
python -m geh_synthetic --help
```

## Generate indicators

Session narratives: `start_patient_session` → `Exam_start` → collateral faults → `Exam_end`.

```bash
# Lab profile (default): GEHQ sample systems, legacy rising exam numbers
python -m geh_synthetic indicators --sessions 2 --sysid CTBAY52WSO --out fixtures/demo.ndjson

# Fleet profile: 6 synthetic hospitals, Internal/Clinical/Demo, random 3-digit exams
python -m geh_synthetic indicators --profile fleet --sessions 50 --out fixtures/fleet.ndjson
python -m geh_synthetic indicators --profile fleet --site mayo_rst --machine-type Clinical --sessions 10
```

Options: `--error-rate`, `--min-exams` / `--max-exams`, `--seed`, `--domain` (non-ES field names).

## Generate honeycomb

Profiles `sample_data/mock_sample_honeycombdata_elastic (1).json` (sysService_v1 LPP map).

```bash
# Compact fail (custom bad-module count)
python -m geh_synthetic honeycomb --status fail --bad-modules 8 --failed-modules 13 --out fixtures/hc.json
python -m geh_synthetic honeycomb --status pass --out fixtures/hc_pass.json

# Golden-sample-like FAIL (184 modules, empirical pixels/module, failed=[13])
python -m geh_synthetic honeycomb --sample-like --out fixtures/hc_sample_like.json

# Sample set across fleet systems + push to Elastic
python -m geh_synthetic honeycomb-samples --count 12 --out-dir fixtures/honeycomb_samples --to-elastic --refresh
```

Invariants enforced: `is_bad_count == sum(len(pixels))`; FAIL `failed_modules` ⊆ `is_bad` keys.

Elastic ingest expands one payload into **one document per module** (`record_type=module`,
`_id=<session_id>:<module_id>`). PASS maps with empty `is_bad` emit a single
`record_type=session` stub. Session fields (`status`, `failed_modules`, …) are
denormalized onto each module doc.

## Fixture tiers

```bash
python -m geh_synthetic fixtures --out-dir fixtures
```

| Tier | Files | Intent |
|------|--------|--------|
| micro | `micro_indicators.ndjson`, `micro_honeycomb_{fail,pass}.json` | Unit tests |
| session | `session_indicators.ndjson`, `session_honeycomb_fail.json` | One-day integration |
| load | `load_indicators.ndjson`, `load_honeycomb_fail.json` | Soak / scale |

## Push to Elasticsearch

Default cluster:

`https://klggehpoc-eb6d47.es.us-central1.gcp.elastic.cloud:443`

1. Copy `.env.example` → `.env` and set `ELASTIC_API_KEY` (or `ELASTIC_USER` + `ELASTIC_PASSWORD`).
2. Ping, then generate + bulk index:

```bash
python -m geh_synthetic ping --to-elastic
python -m geh_synthetic indicators --sessions 2 --sysid CTBAY52WSO --to-elastic --refresh
python -m geh_synthetic honeycomb --status fail --bad-modules 8 --to-elastic --refresh
python -m geh_synthetic fixtures --tier micro --to-elastic --refresh

# Historical repair records for every sysid/machine_type/sw_version in the July 2026 indicator month
python -m geh_synthetic repairs --to-elastic --refresh --out fixtures/repairs.ndjson

# Short device manuals for Revolution CT and Revolution Apex
python -m geh_synthetic manuals --to-elastic --refresh --out fixtures/manuals.ndjson

# Machine parts / BOM lists correlated with sysid, systype, and sw_version
python -m geh_synthetic parts --to-elastic --refresh --out fixtures/machine_parts.ndjson

# Enable semantic search (ELSER) on manuals, repairs, and parts narrative text
python -m geh_synthetic semantic --to-elastic --refresh --verify
```

| Stream | Default index |
|--------|----------------|
| Indicators | each doc `_index` (e.g. `ct_sitedata_ext2_indicator_events_m-2026.07.01`), fallback `ct_sitedata_ext2_indicator_events_m` |
| Honeycomb | `pcd_detector_lpp_honeycomb` |
| Repairs | `ct_system_repair_history` |
| Manuals | `ct_device_manuals` |
| Parts | `ct_machine_parts` |

Semantic NL search uses a `semantic_search` (`semantic_text`) field on manuals (+ lookup copy), repairs, and parts. Override the inference endpoint with `--inference-id` or `ELASTIC_SEMANTIC_INFERENCE_ID` (default `.elser-2-elastic`).

Overrides: `--elastic-url`, `--index`, `--indicator-index`, `--honeycomb-index`, or `ELASTIC_*` env vars.

## Kibana dashboards

Upsert the fleet overview + hospital detail dashboards (Kibana Dashboards API):

```bash
python -m geh_synthetic dashboards
```

| Dashboard | ID | Contents |
|-----------|----|----------|
| Fleet overview | `geh-fleet-overview` | Distinct hospitals / machine types / sysIds; US-state choropleth of machine counts; hospital table (`# of machines`, `# of machine types`, `# of Critical Issues Found`) with drilldown |
| Hospital detail | `geh-hospital-detail` | Critical & Warning by sysId & hospital with device-manual LOOKUP; top messages; repair history; parts/BOM lists |

Open:

- Overview: `https://klggehpoc-eb6d47.kb.us-central1.gcp.elastic.cloud/app/dashboards#/view/geh-fleet-overview`
- Detail: `https://klggehpoc-eb6d47.kb.us-central1.gcp.elastic.cloud/app/dashboards#/view/geh-hospital-detail`

Definitions live in `kibana/dashboards/*.json`. Drilldown: from the hospital table, apply a hospital filter (or use the panel drilldown action) to open the detail dashboard with filters/time range carried forward.

## Alerting rule + AI email workflow

Upsert the PCD collimation FAIL + CT Critical correlation rule and workflow:

```bash
python -m geh_synthetic alerts
```

| Asset | ID | Behavior |
|-------|----|----------|
| Rule | tag `geh:pcd-collimation-fail-critical` | ES\|QL over `pcd*` + `ct*`: `collimation_status.keyword == "FAIL"` and `indicator_severity` Critical (case-insensitive `CRITICAL`) correlated by `sysid` |
| Workflow | `pcd-collimation-fail-critical-summary` | On alert: fetch PCD FAIL + Critical indicators for the sysid, AI-summarize PCD failures, email `kate.lawrencegupta@elastic.co` via `Elastic-Cloud-SMTP` |

Definitions: `kibana/rules/pcd-collimation-fail-critical.json`, `kibana/workflows/pcd-collimation-fail-critical-summary.yaml`.

## CT hybrid search REST API

Upsert the Search Application + manual workflow:

```bash
python -m geh_synthetic hybrid-search-api --query "gantry abort" --severity Critical
```

| Asset | Endpoint |
|-------|----------|
| Search Application (sync) | `POST https://klggehpoc-eb6d47.es.us-central1.gcp.elastic.cloud:443/_application/search_application/ct-hybrid-search-api/_search` |
| Workflow run (async) | `POST https://klggehpoc-eb6d47.kb.us-central1.gcp.elastic.cloud/api/workflows/workflow/ct-hybrid-search-api/run` |

Request body (Search Application):

```json
{
  "params": {
    "query": "gantry abort detector",
    "size": 10,
    "hospital": "",
    "sysid": "",
    "severity": "Critical",
    "rank_window_size": 100,
    "rank_constant": 60
  }
}
```

Hybrid ranking: BM25 (`multi_match`) + semantic (`indicator_message_semantic`) fused with RRF over `ct_sitedata_ext2_indicator_events_m-2026.07.01`.

Definitions: `kibana/search_applications/ct-hybrid-search-api.json`, `kibana/workflows/ct-hybrid-search-api.yaml`.

## Elastic backups

Timestamped exports of live Kibana workflows + Agent Builder agents/tools:

- `kibana/backups/latest/` — newest snapshot
- `kibana/workflows/` — workflow YAML (synced from cluster)
- `kibana/agents/` — agent JSON (synced from cluster)

See `kibana/backups/README.md`.

## Sample data

- `sample_data/mock_CT_dynamic_indicator_TestMachineData (1).csv` — Kibana export used as the value catalog (not the emit format)
- `sample_data/mock_sample_honeycombdata_elastic (1).json` — golden FAIL LPP shape

Emit format is clean ES-oriented JSON/NDJSON (logical fields only; ISO timestamps; string `indicator_id`).
