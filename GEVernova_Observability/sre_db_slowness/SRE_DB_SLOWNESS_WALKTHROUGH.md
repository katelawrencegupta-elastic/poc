# SRE space — DB slowness walkthrough

**Kibana space:** `sre`  
**Project:** my-observability-project-f2e495 (Elastic Observability, us-west-2)  
**Dashboard:** `[SRE] DB slowness walkthrough` (`sre-db-slowness-walkthrough`)  
**Window used to build this:** last 3 days ending 16 Sep 2026 21:00 UTC

Open the space, then the dashboard:

https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud/s/sre/app/dashboards#/view/sre-db-slowness-walkthrough

Keep the time picker on **last 3 days** for the demo. Click a legend item on the chart to isolate one RDS host.

---

## What you are about to show

A user-facing “the product is slow” complaint often starts as **CPU on something named postgres**. Elastic’s job is to walk from that symptom to the **calling app**, the **SQL**, the **distributed trace**, and the **logs** — and to drop false leads.

Two findings from this window:

1. **False lead.** `paf-postgres-dc-test` in `paf-service-stage` sat on its container CPU limit and spiked to **335%** at 15 Sep 04:58 UTC. Logs at 04:52 are a **Spring Boot banner** (`PostgresRefImplConnectorApplication` 1.5.0). That pod is a PAF analytics *connector*, not PostgreSQL. The only well-traced PAF client (`paf-analytic-catalog-eks-stage`) talks to RDS `paf-analytic-catalog-rdsmig-stage` at **0.6 ms** average — not this pod.

2. **Real DB slowness.** Client spans with `span.destination.service.resource = postgresql` lasting **≥1 second**: about **28,500** in three days. The long tail is `meridium-service-search` → `apm-classic-stage-rds` (**p95 ~56 s**, max **67 minutes**) and `meridium-webapi` → `apm-m-perf-perf-db1` (many ≥1 s spans, max ~47 s).

---

## Walk the dashboard in this order

### 1. KPIs (is postgres actually slow?)

Four numbers at the top.

- **Slow postgresql spans (≥1s)** — count of DB client spans over one second. This is the page line for “the database hop is slow,” independent of host CPU.
- **Longest DB span (seconds)** — in this window it is **4035 s** (~67 minutes).
- **Apps with a slow DB span** — how many `service.name` values appear on those spans.
- **classic-stage-rds CPU % max** — infra for the RDS instance that search hits. It is **not** what explains a 67-minute `SELECT`.

If the slow-span KPI is ~0, stop talking about the database.

### 2. Chart (which RDS?)

Line chart: slow span **count** over time, split by a short RDS name (`classic-stage-rds`, `meridium-perf-db1`, `alerts-postgres`, …).

Click **classic-stage-rds**. The burst hours (for example 14 Sep 09:00 and 15 Sep 05:00–11:00 UTC) are search/onboarding work, not a generic “RDS is down.”

### 3. Apps table (who called it?)

Each row is `service.name` × RDS hostname.

Read **search → classic-stage-rds** first (few thousand slow spans, worst max). Then **meridium-webapi → perf-db1** (highest *count* of ≥1 s spans — that is the user-facing API). Then alarms/cases if someone asks “is it only Meridium?”

This is the pivot from infra to **application**.

### 4. SQL table (what did they run?)

`attributes.db.query.text` exists on the search service (Npgsql / OTel). The table keeps the `FROM …` excerpt.

You should see the same shape over and over:

```text
SELECT … , count(*) over () …
FROM MI_EQUIP000 …
WHERE (… FMLY_KEY = @family …)
```

Same pattern on `MI_MRBIANAL`, `MI_FNCLOC00`, `MI_REF_DOCUMENTS`. That windowed `count(*) over ()` plus a family filter is why a single span can run for **tens of minutes**. Other apps often have no `db.query.text`; their rows will not appear here — that is an instrumentation gap, not “they were fast.”

### 5. Traces table (open the waterfall)

Sorted by duration, **≥5 s**. Click **trace.id**.

Example from this window:

https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud/s/sre/app/apm/link-to/trace/9a51f6833eb9be520f647e3c8111877c

That trace is **not** a single HTTP click. Trace context is propagated over **ActiveMQ**, so the waterfall also shows GAA, eLog, rounds, policy, UAA `/token_keys`, and **106** postgres spans on search. The slow one is `span.name = postgresql` on pod `apm-classic-meridium-service-search-fd97586fd-r5k7v` in `apm-classic-stage`.

This is the moment to say: Elastic joins **infra identity** (RDS host, pod, namespace) to **app identity** (`service.name`) to **one request** (`trace.id`).

### 6. Logs (what was the pod doing?)

Same deployment, same time picker: `apm-classic-meridium-service-search`.

You will not see a Postgres error. You will see:

```text
Working on EntityDeleted by apm-dew-stage-admin Entity EK: … FId: MI_DEW_DQ_EQUI_MAP
from activemq://…/apmclassicapmd_APMDEWIngestionSvc_bus_…
```

Search is consuming DEW **entity-deleted** messages and then running those heavy `MI_EQUIP000` selects. Logs explain *why* the SQL ran; traces explain *how long*; RDS metrics say the instance was not in a storage stall (read latency ~4 ms).

### 7. RDS row (close the infra question)

`apm-classic-stage-rds`: CPU average is single-digit percent in this mapping; disk queue peaked around **7**; read latency stayed milliseconds. The database *host* is not the 67-minute problem. The **query shape + search/DEW workload** is.

---

## Optional extra hop (user impact)

If the conversation is “did a person wait on this?”, open the existing AppHub board (client HTTP to Classic/Meridium), not this DB board:

https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud/s/sre/app/dashboards#/view/sre-apphub-meridium-latency

`meridium-webapi` is the API that AppHub calls. Its slow postgresql spans to `perf-db1` / `classic-stage-rds` are the ones that can show up as AppHub client latency or timeouts.

---

## How to demo it (five minutes)

1. Open the walkthrough dashboard, last 3 days. Point at **28k slow spans** and **4035 s** max.
2. Isolate **classic-stage-rds** on the chart.
3. In the apps table, name **meridium-service-search** and **meridium-webapi**.
4. In SQL, read `FROM MI_EQUIP000` + `count(*) over ()`.
5. Click the top `trace.id`, stay on the postgresql span, then come back and scroll to **EntityDeleted** logs.
6. If someone says “we saw high CPU on paf-postgres,” show the intro callout: connector restart, not the DB.

Do not claim RDS was idle if someone drills into `cpu.total.pct` and sees a 100% sample — the field is a 0–1 fraction scaled to percent on the KPI. The **average** is low; the **query duration** is the page-worthy signal.

---

## What this is not

- Not an alert or case workflow (unlike OOM / AppHub latency).
- Not coverage of every postgres in the estate — IAM UAA, alerts, cases, SmartSignal all have their own RDS hosts on the same destination resource name `postgresql`. Filter by `server.address` / the chart legend.
- Not proof of a missing index without `EXPLAIN` — Elastic shows the statement and the duration; DBA work still happens in Postgres.
