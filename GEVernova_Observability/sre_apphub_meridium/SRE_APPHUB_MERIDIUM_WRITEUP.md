# SRE space — AppHub → Meridium latency

**Kibana space:** `sre`  
**Project:** my-observability-project-f2e495 (Elastic Observability, us-west-2)  
**Window reviewed:** last 3 days (12 Sep 2026 12:00 UTC through 15 Sep 2026 12:00 UTC)  
**Scope:** client-side latency from AppHub to APM Classic / Meridium only

---

## In one paragraph

Users reach Meridium through AppHub. AppHub does not call the `meridium-webapi` service by name. It makes HTTPS calls to APM Classic / Meridium hostnames (mainly `apm-classic-stage`). Over the last three days that hop on **stage** was mostly fine: about **169,000** calls, **193 ms** average, **1.4%** failures. The problems worth paging are short error storms, a few APIs that are consistently slow (especially session at ~3 seconds), and client timeouts that sit at **~5 minutes** with no HTTP status. **Dev** is a different story: about **one in four** calls failed, mostly a Rounds API. A dashboard, three alerts, a case workflow, and an analyst agent are now live in the `sre` space so the next spike opens a case instead of living only in traces.

---

## What we are actually measuring

Think of AppHub as the front door and Meridium / APM Classic as the product behind it. When someone opens a Meridium screen from AppHub, AppHub proxies that request. Elastic already records those outgoing calls as traces from `predix-apphub-stage-active`.

The hosts on the other side of that proxy are:

| Host | Role in the last 3 days |
|------|-------------------------|
| `apm-classic-stage.apm.stage.usw02.15.energy` | Main path — almost all of the traffic |
| `apm-classic-dev.apm-temp.dev.usw02.15.energy` | Dev — much noisier |
| `apm-classic-beta-stage.lb2.apm.stage.usw02.15.energy` | Beta — low volume, sometimes very slow |
| `apm-meridium-ui-stage.apm.stage.usw02.15.energy` | Almost unused (one 404) |

We do **not** treat AppHub → `meridium-webapi` as a direct service-to-service call. That name does not appear as AppHub’s destination. Meridium backends do emit their own traces now; they are just not this hop.

---

## What the last 3 days looked like

### Stage (the path that matters)

| Measure | Result |
|---------|--------|
| Calls | 168,825 |
| Average latency | 193 ms |
| Successful calls, typical (p50) | 25 ms |
| Successful calls, slow tail (p95) | 247 ms |
| Failure rate | 1.44% (2,436 failed spans) |

Most traffic is healthy. A successful page load from AppHub to Classic is usually tens of milliseconds, and the slow-but-still-OK tail is about a quarter of a second.

### Where it hurt

**Client timeouts.** 67 failed calls had **no HTTP status** and lasted about **4 minutes** on average (p99 about **5 minutes**). That is AppHub giving up while waiting on Classic/Meridium, not a clean 500 from the API.

**Slow APIs (even when they succeed).**

- `GET /api/v1/core/security/session` — about **3 seconds** average, 3,356 calls  
- `POST /api/v1/core/queryengine/executesync/container` — about **281 ms**, 11,562 calls (highest volume API)  
- `GET /api/v1/internal/mi/im/imconfiguration` — about **613 ms** average, p95 about **1.2 seconds**

**Error-shaped hours on stage.**

- 13 Sep 10:00–13:00 UTC — almost every call failed, but volume was low (~300 calls)  
- 14 Sep 01:00 UTC — average jumped to **670 ms** (would have paged as slow)  
- 14 Sep 16:00 UTC — **484** failures in one hour (3.1% of a busy hour)  
- 15 Sep 01:00 UTC — average **469 ms** (just under the 500 ms page line)  
- 15 Sep 06:00 and 09:00 UTC — failure rate near **4–4.5%** (just under the 5% page line)

**Other HTTP errors on stage (3 days):** 1,288 × 400, 516 × 500, 504 × 404. `POST /api/v1/core/userpref/set` failed **28%** of the time (mostly 4xx, fast).

### Dev (noisy, keep it separate)

| Measure | Result |
|---------|--------|
| Calls | 11,311 |
| Average latency | 483 ms |
| Failure rate | 26% |

Almost all of that pain is `POST /rounds/v1/routes/route-masters/` — **86%** failed, p95 about **10.5 seconds**. Dev Rounds should not be mixed into a “stage Meridium is slow” page.

### Beta (small, currently hot)

Over 3 days: 2,344 calls, **708 ms** average, 0.38% failures. At install time (15 Sep ~12:15 UTC) this host was already in breach: **3.5 seconds** average over 15 minutes and **3** timeouts around **110 seconds**.

---

## What we installed

Same pattern as the Kubernetes OOM use case: a dashboard to look, alerts to notice, a workflow to open a case, and an agent to investigate.

### Dashboard

**`[SRE] AppHub → Meridium latency`** (`sre-apphub-meridium-latency`)

Default window: last 3 days.

It shows call volume, average latency, trace p95, failure rate, timeouts ≥30 seconds, **line charts and a heatmap that re-bucket with the time picker**, a host comparison (avg ms vs fail %), and tables of destinations, HTTP paths, timeouts, and status codes. Click a legend item on a line chart to isolate a host.

Open it in the `sre` space: Dashboards → `[SRE] AppHub → Meridium latency`.

### Alerts

All three classic custom-threshold rules below are **enabled**. They watch AppHub client traces to Classic/Meridium hosts. When they fire **new** or **recovered**, they start the case workflow.

| Alert ID | Name | Watches for | Priority |
|----------|------|-------------|----------|
| `gev-sre-apphub-meridium-latency` | [SRE] AppHub → Meridium avg latency ≥ 500ms | Average client wait ≥ 500 ms over 15 minutes | P2 |
| `gev-sre-apphub-meridium-errors` | [SRE] AppHub → Meridium error rate ≥ 5% | ≥20 failed calls in 15 minutes | P1 |
| `gev-sre-apphub-meridium-timeouts` | [SRE] AppHub → Meridium client timeouts ≥ 30s | ≥3 calls that lasted 30 seconds or more | P1 |

Matching v2 ES|QL rules exist for the same signals (destination metrics for latency/errors; traces for timeouts). They do **not** auto-start the workflow today (`actions: null`). The classic companions are what open the case.

Those thresholds were chosen from this 3-day window: stage’s normal average is well under 200 ms, so 500 ms is a real spike; 5% failures is above the 1.4% baseline; 30-second spans catch the 5-minute client abort pattern without paging on ordinary slowness.

### Auto path (what alerts use) — `gev-sre-apphub-meridium-auto-approve`

Enabled. Triggered by AppHub/Meridium latency, error, and timeout alerts, or manually / via tool `gev-sre-apphub-meridium-run-auto-approve`.

Same evidence and RCA as the HITL path, then **auto-approves** from RCA: `escalate_meridium_owners` (default) or `investigate_apphub_proxy` when class is `apphub.proxy`. Does not change routing.

### HITL path — `gev-sre-apphub-meridium-latency-case`

**`gev-sre-apphub-meridium-latency-case`** — enabled. Manual / agent tool.

1. Creates or updates an Observability case  
2. Pulls destination latency, hourly trend, slow HTTP paths, and timeout evidence  
3. Classifies the issue (`timeout.client` / `meridium.slow_path` / `meridium.errors` / `apphub.proxy` / `latency.unknown`)  
4. Writes RCA and proposed next steps  
5. Pauses for a human to choose:
   - `escalate_meridium_owners` — hand off to Meridium / APM Classic  
   - `investigate_apphub_proxy` — look at AppHub routing / templates  
   - `reject_false_positive`  
6. Does **not** change routing, ingress, or any live service  

Concurrency is **max 1** per `caller | destination | alert_status`, queued. A stuck HITL wait will block later runs for the same key until it is resumed or cancelled.

Case fields reuse existing slots (the space is capped at 10 custom fields, and four of them are **required**): **account-id** = AppHub service name, **region** and **domain-name** = destination host, **node-id** = `apphub-client`. Create fails if domain/node are omitted.

### Agent

**`gev-sre-apphub-meridium`** — SRE AppHub → Meridium latency analyst

- Detects slow or failing hops with ES|QL without being told the hostname  
- Breaks the problem into trend, slow paths, and timeout vs backend error  
- Starts the case workflow via `gev-sre-apphub-meridium-run`  
- Never changes routing itself  

---

## Day-to-day flow

1. Average wait ≥ 500 ms, failure count ≥ 20, or ≥3 calls ≥30 s → classic alert → auto-code workflow → case + RCA + `investigate_apphub_proxy`  
2. Use the dashboard (last 3 days) to see whether it is stage, dev, or beta, and which API path  
3. Ask the agent “is AppHub to Meridium slow?” for an investigation without waiting for an alert  
4. HITL (`gev-sre-apphub-meridium-run`) still pauses for approve/reject in the Kibana workflow execution, not in chat  

---

## How to read a page

| You see… | Likely meaning |
|----------|----------------|
| High average, low failure rate | A slow Meridium/Classic API (check session, query engine, IM config) |
| High failure rate, normal latency | 4xx/5xx from Classic/Meridium (or AppHub template 404s) |
| Spans at ~30–300 seconds with no status | AppHub client timed out waiting |
| Dev Rounds POST failing | Dev-only noise — do not treat as a stage outage |
| Beta 3+ second averages | Real, but low volume — still worth a case if it persists |

---

## Known gaps / caveats

- This use case is the **AppHub client view**. It does not yet split time spent in AppHub vs time spent inside each Meridium microservice.  
- Dev Rounds failures will page if they hit the error/timeout thresholds. That is intentional so they are visible; treat them as a separate queue from stage.  
- Classic latency uses average span duration on traces; v2 latency uses destination 1-minute metrics. They should agree closely (they did over this 3-day window).  
- Stuck HITL executions occupy the concurrency key until cleared.

---

## Asset quick reference

| Kind | ID |
|------|-----|
| Dashboard | `sre-apphub-meridium-latency` |
| Alert (classic + v2) | `gev-sre-apphub-meridium-latency` |
| Alert (classic + v2) | `gev-sre-apphub-meridium-errors` |
| Alert (classic + v2) | `gev-sre-apphub-meridium-timeouts` |
| Workflow (alerts) | `gev-sre-apphub-meridium-auto-approve` |
| Workflow (HITL) | `gev-sre-apphub-meridium-latency-case` |
| Agent | `gev-sre-apphub-meridium` |
| Tool (auto) | `gev-sre-apphub-meridium-run-auto-approve` |
| Tool (HITL) | `gev-sre-apphub-meridium-run` |
| Install | `sre_apphub_meridium/apply.py` |
| This write-up | `sre_apphub_meridium/SRE_APPHUB_MERIDIUM_WRITEUP.md` |

---

*Generated for GE Vernova Observability PoC — Kibana `sre` space — 15 Sep 2026.*
