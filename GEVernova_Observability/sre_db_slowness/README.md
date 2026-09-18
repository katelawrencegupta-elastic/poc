# SRE DB slowness walkthrough

Dashboard + demo script that traces **postgresql slowness** through
apps, SQL, APM traces, and container logs — same Kibana `sre` space as
`sre_apphub_meridium/` and `sre_k8s_oom/`.

This is a **walkthrough**, not an alerting loop. No rules or HITL workflows.

## What we actually follow

The CPU-hot pod `paf-postgres-dc-test` is a **Spring Boot connector**
(`PostgresRefImplConnectorApplication`) that restarted 15 Sep 04:52 UTC.
It is not the database, and PAF services are not well traced into it.

The path that has apps + traces + logs is:

`meridium-service-search` (and `meridium-webapi`) →
`apm-classic-stage-rds` / `apm-m-perf-perf-db1` via `span.destination = postgresql`

Worst sample in the last 3 days: **67-minute** `SELECT … count(*) over ()`
on `MI_EQUIP000` in trace
[`9a51f6833eb9be520f647e3c8111877c`](https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud/s/sre/app/apm/link-to/trace/9a51f6833eb9be520f647e3c8111877c).

## What is here

| Path | Purpose |
|---|---|
| `dashboards.py` | ES\|QL KPI / XY / tables |
| `kibana/sre-db-slowness-walkthrough.json` | Written on install |
| `SRE_DB_SLOWNESS_WALKTHROUGH.md` | Spoken demo script |
| `apply.py` | Install into Kibana `sre` space |

## Install

```bash
cd sre_db_slowness
ELASTIC_API_KEY=... python3 apply.py            # verify + dashboard
ELASTIC_API_KEY=... python3 apply.py dashboard
ELASTIC_API_KEY=... python3 apply.py verify
```

Dashboard: `/s/sre/app/dashboards#/view/sre-db-slowness-walkthrough` (default last 3 days).

Click `trace.id` in the traces table — the SRE traces data view formats it as
an APM deep link.
