# GE Vernova — Splunk Observability Cloud Deployment Summary

**Source:** `olly_inventory/outputs/o11y_inventory/` (realm `us1`, inventory generated 2026-08-11 00:01 UTC)
**Purpose:** Migration scoping — object counts, complexity, consolidation opportunities.

---

## 1. Deployment at a glance

| Object | Count |
|---|---|
| Dashboard groups | 1,110 |
| Dashboards | 1,909 |
| Charts on dashboards | 13,241 |
| Detectors (alerts) | 780 |
| Trigger rules across detectors | 4,859 |
| Alert muting rules | 119 |
| Synthetic tests | 50 |
| Teams | 15 |
| Metrics in org | 15,588 |
| **Active MTS (metric time series)** | **933,055** |

Dashboards date from 2020-10-10 through 2026-08-09 — roughly six years of accumulation with no evident pruning cycle.

---

## 2. Dashboards ranked by popularity

Splunk O11y's API exposes no view counts. But a real usage signal is recoverable from the detector payloads: **every alert rule carries a `tip` and `runbookUrl`, and 4,045 of those URLs deep-link to a specific dashboard.** Those are the dashboards an on-call engineer lands on when paged — operational pull-through, not shelf-ware.

Only **23 dashboards in the entire 1,909-dashboard estate are linked from any alert.** That is 1.2%.

### Top 5 dashboards by popularity

| # | Dashboard | Alert refs | Detectors | Charts | Group | Last updated |
|---|---|---|---|---|---|---|
| 1 | **RDS Prod** | 2,101 | 102 | 13 | SRE EKS - AWS Services USW | 2026-05-25 |
| 2 | **MQ Prod** | 443 | 20 | 18 | SRE EKS - AWS Services USW | 2026-03-29 |
| 3 | **K8s container** | 301 | 30 | 9 | Kubernetes | 2026-06-29 |
| 4 | **Cache Instance** | 348 | 34 | 10 | AWS Service Usage Details | 2025-03-18 |
| 5 | **EC2 instances** | 60 | 12 | 27 | AWS EC2 | 2026-08-05 |

Ranked by a composite of alert references, distinct referencing detectors, update recency, and chart count. `Cache Instance` outranks `EC2 instances` on raw references but is 17 months stale, which the recency weighting offsets.

**None of these appear in the top 10 by chart count.** `RDS Prod` — the single most operationally important dashboard in the org, referenced by 102 detectors — has just 13 charts. Meanwhile `SFC Template` (84 charts, the largest build in the estate) is referenced by zero alerts. Size and usage are inversely correlated here.

### Ranks 6–15

| # | Dashboard | Alert refs | Detectors | Charts | Last updated |
|---|---|---|---|---|---|
| 6 | CONFIG-SERVICE | 165 | 18 | 10 | 2025-07-22 |
| 7 | ACTIVEMQ MQ | 143 | 10 | 11 | 2025-11-18 |
| 8 | USW_EKS_POD's | 160 | 21 | 4 | 2025-04-03 |
| 9 | ALB Prod | 86 | 42 | 7 | 2024-07-15 |
| 10 | ELASTIC SEARCH PROD | 60 | 6 | 13 | 2025-09-15 |
| 11 | Tables | 32 | 2 | 18 | 2026-08-10 |
| 12 | Cache Prod | 44 | 8 | 11 | 2025-07-18 |
| 13 | K8s Pods | 50 | 5 | 2 | 2023-11-02 |
| 14 | Timeseries MSK-US WEST | 8 | 1 | 23 | 2026-07-15 |
| 15 | ALB Prod EUC | 16 | 8 | 7 | 2023-12-22 |

Note rank 9, `ALB Prod`: referenced by **42 distinct detectors** — the second-broadest reach in the org — but last updated July 2024. Widely depended on, actively rotting.

Full ranking of all 1,909 dashboards: `dashboard_popularity_ranking.csv`.

### Dashboard groups by popularity

Group popularity is even more concentrated than dashboard popularity.

| # | Group | Alert refs | Detectors | Dashboards in group |
|---|---|---|---|---|
| 1 | **SRE EKS - AWS Services USW** | 2,877 | 188 | 7 referenced |
| 2 | AWS Service Usage Details | 348 | 34 | 1 |
| 3 | Kubernetes | 301 | 30 | 1 (of 25) |
| 4 | TMS-EKS-SERVICES-PROD-USW | 165 | 18 | 1 |
| 5 | SRE_EKS_POD's | 160 | 21 | 1 |

Then: AWS EC2 (60), K8s Pods (50), Timeseries Keyspace (48), SRE EKS - EUC AWS Services (16), Predix-Timeseries-EU (7), AWS SQS (6), Predix-Timeseries-US-West (5).

**`SRE EKS - AWS Services USW` alone absorbs 71% of all alert-to-dashboard traffic** and is referenced by 188 of 780 detectors. Twelve groups out of 1,110 receive any alert traffic at all.

Compare against the groups that merely *hold the most dashboards* — `veerendra.hegde@ge.com` (30, a personal group), PAF Dashboard - EKS USW (26), Kubernetes (25), PAF Dashboard - EKS Frankfurt (24), Timeseries Keyspace (23). Only Kubernetes and Timeseries Keyspace appear on both lists. The PAF groups hold 90+ dashboards between them and pull zero alert traffic.

### Chart counts — the full distribution

13,241 charts across 1,909 dashboards, mean 6.9. Grouped by usage tier:

| Tier | Dashboards | Charts | Share of charts |
|---|---|---|---|
| **A** — referenced by alerts | 23 | 348 | 2.6% |
| **B** — no refs, updated <180d, has charts | 185 | 2,527 | 19.1% |
| **C** — no refs, 180–365d | 56 | 655 | 4.9% |
| **D** — no refs, stale >365d | 738 | 9,711 | 73.3% |
| **E** — empty (0 charts) | 907 | 0 | 0% |
| **Total** | **1,909** | **13,241** | |

**73% of all chart-building effort in this org sits on dashboards that are over a year stale and referenced by no alert.**

Note on Tier E: 873 of those 907 empty dashboards are auto-provisioned personal defaults, not abandoned work. Only 34 empty dashboards exist in the shared estate. See §6.

The largest builds by raw chart count — SFC Template (84), Security Service Dashboard (75), Smart Factory Cloud (50), Cloud integrations (47), K8s control plane summary (41) — are Tier B: recently maintained, real content, but no alert wiring. They're likely browsed manually rather than paged into, so they deserve a direct question to the owning teams rather than an assumption either way. Behind them, Redis USW and REDIS EUC (39 charts each) haven't been touched since 2022.

Only **6 dashboards are mirrored across multiple groups** (`Service` appears in 11), and only 155 of 1,909 (8%) have ever been edited by someone other than their creator — further evidence of low collaborative use across the estate.

### Top 5 of the Tier A+B migration set

Restricting to the 208-dashboard defensible target (Tier A + B, 2,875 charts):

| # | Dashboard | Alert refs | Detectors | Charts | Group | Last updated |
|---|---|---|---|---|---|---|
| 1 | RDS Prod | 2,101 | 102 | 13 | SRE EKS - AWS Services USW | 2026-05-25 |
| 2 | K8s container | 301 | 30 | 9 | Kubernetes | 2026-06-29 |
| 3 | MQ Prod | 443 | 20 | 18 | SRE EKS - AWS Services USW | 2026-03-29 |
| 4 | Cache Instance | 348 | 34 | 10 | AWS Service Usage Details | 2025-03-18 |
| 5 | EC2 instances | 60 | 12 | 27 | AWS EC2 | 2026-08-05 |

**77 charts across these five** — 2.7% of the Tier A+B chart total. Rebuilding these five is a days-not-weeks exercise and covers the dashboards behind the majority of alert traffic in the org.

### Why there is no per-chart or per-access ranking

Two hard blockers, both worth stating plainly before this goes to a customer:

1. **Splunk Observability Cloud does not expose dashboard or chart view counts through any API.** The Organization Overview "Engagement" tab and the `sf.org.*` metrics count objects *created* — `sf.org.num.dashboard`, `sf.org.num.detector` — not objects *viewed*. The Audit Events API returns configuration-change history (who edited what, when), not access history. No amount of re-running the inventory script will produce a true "most-accessed dashboard" list.

2. **This export contains no chart names at all.** The script's `--include-charts` flag was not used, so `charts.csv` was never generated. Chart objects inside `raw/dashboards.json` carry only `chartId`, `row`, `column`, `width`, `height` — grid geometry, nothing else. There are 13,012 distinct chart IDs in the estate and not one resolvable title.

**What would close gap 2:** re-run with `python3 o11y_inventory.py --include-charts`. That hits `/v2/chart` and returns chart names, types, and creators — enough to rank charts by reuse (229 chart IDs already appear on more than one dashboard) and to scope chart-level migration properly. Roughly a 13,000-object pull; slow but straightforward.

**What partially closes gap 1:** the Audit Events API gives per-object edit history. Frequency of *edits* is a weaker proxy than views but it identifies which dashboards teams actively maintain and who owns them — which is the question Tier B (185 dashboards, no alert wiring, recently updated) actually needs answered.

**What definitively closes gap 1:** asking the SRE and platform teams directly. Twelve dashboard groups carry all the alert traffic; a 30-minute conversation with their owners will beat any telemetry proxy available here.

---

## 3. Alerts (detectors)

**780 detectors, all `ACTIVE`, all `METRIC` type, containing 4,859 individual trigger rules.**

The API does not expose firing history, so "top" detectors are ranked by **number of trigger rules** — the closest available proxy for alert surface area and the direct driver of migration effort.

### Top 5 detectors by trigger rules

| # | Detector | Rules | Severity mix | Channel | Last updated |
|---|---|---|---|---|---|
| 1 | `[sFx-SRE-PROD-EUC-AWS/RDS-756641539810]-PAF` | 84 | 56 Major / 28 Critical | ServiceNow | 2026-04-01 |
| 2 | `[sFx-SRE-PROD-USW-AWS/RDS-816857971392]-PAF` | 84 | 56 Major / 28 Critical | ServiceNow | 2026-04-01 |
| 3 | `[QA-sFx-SRE-PROD-USW-AWS/RDS-816857971392]-PAF` | 84 | 56 Major / 28 Critical | ServiceNow | 2026-03-31 |
| 4 | `[QA-sFx-SRE-PROD-EUC-AWS/RDS-756641539810]-PAF` | 84 | 56 Major / 28 Critical | ServiceNow | 2026-03-31 |
| 5 | `[sFx-SRE-PROD-USW-AWS/RDS-159310808016]-APM-M` | 56 | 36 Major / 20 Critical | ServiceNow | 2026-04-01 |

All five are AWS/RDS monitors. Note that #3 and #4 are QA clones of #1 and #2 — the same 84 rules maintained twice.

### Trigger rules by severity

| Severity | Rules | Share |
|---|---|---|
| Major | 3,108 | 64% |
| Critical | 1,626 | 33% |
| Warning | 63 | 1.3% |
| Minor | 33 | 0.7% |
| Info | 29 | 0.6% |

**97% of all trigger rules are Critical or Major.** There is effectively no low-severity tier — a classic alert-fatigue signature.

### Notification routing

| Channel | Rule notifications |
|---|---|
| ServiceNow | 4,058 (78%) |
| Email | 1,043 (20%) |
| Team (in-product) | 26 |
| Splunk Platform | 7 |

ServiceNow is the single dominant destination; any migration must reproduce that integration on day one. **81 detectors have no notification configured on any rule** — they fire into the void.

### How alerts are categorized

There are **four independent classification systems** layered over the detector estate, and only one of them is consistently applied.

#### 1. Detector name taxonomy — 43% adoption

338 detectors (43%) follow a strict convention:

```
[QA-]sFx-SRE-<ENV>-<REGION>-<AWS_SERVICE>-<AWS_ACCOUNT_ID>]-<APP>
```

Every conforming detector is owned by team token `SRE`. The dimensions it encodes:

| Dimension | Values |
|---|---|
| Environment | PROD 270, PREPROD 66 |
| Region | USW 202, EUC 134 |
| AWS service | `AWS/RDS` 103, `K8Services` 77, `AWS/ApplicationELB` 51, `AWS/ElastiCache` 42, `AWS/AmazonMQ` 31, `EC2` 15, `AWS/SQS` 6, `AWS/ES` 6, `AWS/Kafka` 2, `AWS/Cassandra` 2 |
| AWS account | 12 distinct accounts; top three are `159310808016` (93), `555031161167` (49), `816857971392` (43) |
| Application | APM-M 33, SmartSignal 30, EdgeManager 20, PAF 20, APM-P 18, APPHUB 18, UOM 16, IBI-Server 12, IAM 12, TMS 12, CAF 12, GEDA 12 |

174 of the 338 are `QA-` prefixed duplicates. A further 16 bracketed detectors use ad-hoc formats — `[TS Keyspace] ReadThrottleEvents`, `[PROD] Write Throttle Events-EU` — a second, undocumented convention for the Timeseries Keyspace estate.

**The remaining 426 detectors (55%) follow no convention at all.** Free-text names like `Cases worker serice Alert` (sic), `APM Latency Degradation`, `Kafka - Consumer group lag`, `Grid Example Top 10 Nodes by CPU Capacity Usage % Detector`, and one called simply `test`. Grouped thematically:

| Theme | Detectors |
|---|---|
| Other / unclassifiable | 157 |
| Kubernetes / EKS | 67 |
| APM | 54 |
| Database | 42 |
| Kafka / MQ | 29 |
| Synthetics | 27 |
| Smart Factory Cloud | 24 |
| Predix / platform | 15 |
| ITSI / Splunk | 8 |
| Test / scratch | 3 |

#### 2. Priority prefix on trigger labels — the real severity model

Individual trigger rules carry a `detectLabel` encoding priority, and this maps almost perfectly onto severity:

| Prefix | Rules | Severity mapping |
|---|---|---|
| `P2-MajorAlert-` | 2,944 (61%) | Major 2,925 / Critical 19 |
| `P1-CriticalAlert-` | 1,132 (23%) | Critical 1,129 / Major 3 |
| unprefixed | 783 (16%) | Critical 478, Major 180, Warning 63, Minor 33, Info 29 |

P1/P2 discipline is strong where applied — 99.8% consistency. The 783 unprefixed rules are where all the Warning, Minor and Info severities live, and they're concentrated in the unconventionally-named 426.

#### 3. Data-loss pairing — a deliberate design pattern

**1,746 of 4,859 rules (36%) are `*_data_loss_detected` triggers.** Nearly every metric threshold alert is paired with a companion detector that fires at P2/Major when the signal stops arriving. That's a mature pattern — it catches collector failures, not just threshold breaches — and it explains why the rule count is nearly 3× what the underlying monitoring logic would suggest. It also means roughly a third of the alert estate is really "is telemetry flowing," which Elastic addresses differently.

#### 4. What is actually being monitored

195 distinct metrics are alerted on. The top of the distribution is conventional infrastructure:

| Metric | Rules |
|---|---|
| `CPUUtilization` | 291 |
| `DatabaseConnections` | 257 |
| `FreeStorageSpace` | 196 |
| `k8s.pod.phase` | 193 |
| `FreeableMemory` | 149 |
| `container_cpu_utilization` | 144 |
| `k8s.container.memory_request` | 132 |
| `container_memory_usage_bytes` | 112 |
| `ReadIOPS` / `WriteIOPS` | 190 |
| `UnHealthyHostCount` | 73 |

CloudWatch metric names and Kubernetes/OTel metric names sit side by side — two ingestion paths feeding one alerting layer.

### The SRE-owned estate by update recency

Filtering to **active detectors carrying the `SRE` team token: 338 detectors holding 4,042 trigger rules.** That is 43% of the detectors but **83% of all trigger rules in the org** — this is where the alerting weight actually sits.

Unlike the dashboards, this estate is well maintained:

| Last updated | Detectors |
|---|---|
| Under 30 days | 26 |
| 30–90 days | 113 |
| 90–180 days | 187 |
| 180–365 days | 11 |
| Over a year | 1 |

**326 of 338 (96%) were updated within the last six months.** Most recent is 2026-08-10 — the day before the inventory ran. Oldest is 2025-08-04. Compare that against dashboards, where 74% of the shared estate is over a year stale. The alerting layer is alive; the visualization layer is not.

#### 25 most recently updated

| Updated | Rules | Crit/Major | Env | Region | Service | App | Detector |
|---|---|---|---|---|---|---|---|
| 2026-08-10 | 7 | 3/4 | PROD | EUC | EC2 | IBI-Server | `[sFx-SRE-PROD-EUC-EC2-555031161167]-IBI-Server` |
| 2026-08-10 | 7 | 3/4 | PREPROD | USW | EC2 | IBI-Server | `[sFx-SRE-PREPROD-USW-EC2-159310808016]-IBI-Server` |
| 2026-08-10 | 7 | 3/4 | PROD | USW | EC2 | IBI-Server | `[sFx-SRE-PROD-USW-EC2-159310808016]-IBI-Server` |
| 2026-08-10 | 8 | 1/7 | EUC* | PROD* | AWS/Kafka | TimeSeries-Kafka | `[QA-sFx-SRE-EUC-PROD-AWS/Kafka-460147993799]-TimeSeries-Kafka` |
| 2026-08-10 | 8 | 1/7 | PROD | USW | AWS/Kafka | TimeSeries-Kafka | `[QA-sFx-SRE-PROD-USW-AWS/Kafka-399957848812]-TimeSeries-Kafka` |
| 2026-08-10 | 7 | 3/4 | PROD | EUC | EC2 | IBI-Server | `[QA-sFx-SRE-PROD-EUC-EC2-555031161167]-IBI-Server` |
| 2026-08-10 | 7 | 3/4 | PREPROD | USW | EC2 | IBI-Server | `[QA-sFx-SRE-PREPROD-USW-EC2-159310808016]-IBI-Server` |
| 2026-08-10 | 7 | 3/4 | PROD | USW | EC2 | IBI-Server | `[QA-sFx-SRE-PROD-USW-EC2-159310808016]-IBI-Server` |
| 2026-08-10 | 16 | 6/10 | PROD | USW | AWS/Cassandra | TimeSeries-Keyspace | `[QA-sFx-SRE-PROD-USW-AWS/Cassandra-399957848812]-TimeSeries-Keyspace` |
| 2026-08-10 | 16 | 6/10 | EUC* | PROD* | AWS/Cassandra | TimeSeries-Keyspace | `[QA-sFx-SRE-EUC-PROD-AWS/Cassandra-460147993799]-TimeSeries-Keyspace` |
| 2026-08-10 | 21 | 3/18 | PROD | USW | AWS/AmazonMQ | APM-M | `[QA-sFx-SRE-PROD-USW-AWS/AmazonMQ-159310808016]-APM-M` |
| 2026-08-09 | 16 | 3/13 | PREPROD | USW | AWS/AmazonMQ | APM-M | `[QA-sFx-SRE-PREPROD-USW-AWS/AmazonMQ-159310808016]-APM-M` |
| 2026-08-09 | 29 | 7/22 | PROD | USW | AWS/AmazonMQ | APM-P | `[QA-sFx-SRE-PROD-USW-AWS/AmazonMQ-159310808016]-APM-P` |
| 2026-08-09 | 29 | 7/22 | PREPROD | USW | AWS/AmazonMQ | APM-P | `[QA-sFx-SRE-PREPROD-USW-AWS/AmazonMQ-159310808016]-APM-P` |
| 2026-08-09 | 16 | 4/12 | PROD | EUC | AWS/AmazonMQ | EdgeManager | `[QA-sFx-SRE-PROD-EUC-AWS/AmazonMQ-756641539810]-EdgeManager` |
| 2026-08-09 | 16 | 4/12 | PROD | EUC | AWS/AmazonMQ | PAF | `[QA-sFx-SRE-PROD-EUC-AWS/AmazonMQ-756641539810]-PAF` |
| 2026-08-09 | 16 | 4/12 | PROD | USW | AWS/AmazonMQ | EdgeManager | `[QA-sFx-SRE-PROD-USW-AWS/AmazonMQ-816857971392]-EdgeManager` |
| 2026-08-07 | 29 | 7/22 | PROD | EUC | AWS/AmazonMQ | APM-P | `[QA-sFx-SRE-PROD-EUC-AWS/AmazonMQ-555031161167]-APM-P` |
| 2026-08-07 | 1 | 0/1 | PROD | USW | AWS/ApplicationELB | APM (Clone) | `[QA-sFx-SRE-PROD-USW-AWS/ApplicationELB-159310808016]-APM (Clone)` |
| 2026-08-07 | 2 | 0/2 | PROD | USW | AWS/ApplicationELB | APM (Clone) | `[sFx-SRE-PROD-USW-AWS/ApplicationELB-159310808016]-APM (Clone)` |
| 2026-08-07 | 2 | 0/2 | PROD | USW | AWS/ApplicationELB | APM | `[QA-sFx-SRE-PROD-USW-AWS/ApplicationELB-159310808016]-APM` |
| 2026-07-28 | 11 | 5/6 | PROD | USW | K8Services | APM-P | `[sFx-SRE-PROD-USW-K8Services-159310808016]-APM-P` |
| 2026-07-28 | 11 | 5/6 | PROD | USW | K8Services | APM-P | `[QA-sFx-SRE-PROD-USW-K8Services-159310808016]-APM-P` |
| 2026-07-27 | 4 | 2/2 | PROD | USW | AWS/ApplicationELB | APM | `[sFx-SRE-PROD-USW-AWS/ApplicationELB-159310808016]-APM` |
| 2026-07-21 | 4 | 0/4 | PROD | USW | AWS/ElastiCache | APM-P | `[sFx-SRE-PROD-USW-AWS/ElastiCache-159310808016]-APM-P` |

All 25 route exclusively to ServiceNow. Recent activity is concentrated in **AmazonMQ, EC2/IBI-Server, Kafka and Cassandra** — the AmazonMQ work is notable given that AmazonMQ is one of the Tier B gaps with no prebuilt Elastic dashboard.

Full list of all 338: `sre_detectors_by_recency.csv`.

#### This reverses the earlier QA de-duplication advice

**19 of the 26 detectors updated in the last 30 days are `QA-` prefixed.** Looking at all 152 QA detectors that have a live production twin:

| Relationship | Count |
|---|---|
| QA updated **ahead of** its prod twin | 110 |
| Updated same day | 22 |
| Prod ahead of QA | 20 |
| **Rule-count mismatch between the pair** | **9** |

Drift runs as far as **335 days** — `[QA-sFx-SRE-PROD-EUC-AWS/RDS-756641539810]-APPHUB` was updated 2026-07-05 while its production twin has sat untouched since 2025-08-04. A cluster of ten ApplicationELB pairs all show 147-day drift.

The nine rule-count mismatches are the concerning ones, because the two versions have genuinely diverged in logic:

| Detector | QA rules | Prod rules | Drift |
|---|---|---|---|
| `[...PROD-USW-AWS/AmazonMQ-159310808016]-APM-M` | 21 | 19 | +124d |
| `[...PREPROD-USW-AWS/AmazonMQ-159310808016]-APM-M` | 16 | 14 | +122d |
| `[...PROD-USW-AWS/AmazonMQ-159310808016]-APM-P` | 29 | 27 | +60d |
| `[...PREPROD-USW-AWS/AmazonMQ-159310808016]-APM-P` | 29 | 27 | +93d |
| `[...PROD-EUC-AWS/AmazonMQ-555031161167]-APM-P` | 29 | 27 | +91d |
| `[...PROD-EUC-AWS/AmazonMQ-555031161167]-APM-M` | 19 | 17 | +75d |
| `[...PREPROD-USW-K8Services-159310808016]-APM-P` | 11 | 10 | +82d |
| `[...PROD-EUC-K8Services-555031161167]-APM-P` | 11 | 10 | +82d |
| `[...PROD-USW-AWS/ApplicationELB-159310808016]-APM` | 2 | 4 | +11d |

**So the `QA-` detectors are not stale clones to be discarded — in most pairs they are the more current logic.** My earlier framing (§6, "QA-clone tax") holds for effort estimation but not for source selection: when consolidating a pair, the QA version is usually the newer one, and in nine cases production is running fewer rules than QA. Confirm with the SRE team which side is authoritative before collapsing anything.

#### Two naming defects

`[QA-sFx-SRE-EUC-PROD-AWS/Kafka-460147993799]-TimeSeries-Kafka` and `[QA-sFx-SRE-EUC-PROD-AWS/Cassandra-460147993799]-TimeSeries-Keyspace` have the environment and region slots transposed — `EUC-PROD` where every other detector reads `PROD-EUC`. Both were updated 2026-08-10. Minor, but they'll break any parser built on the convention.

### Routing and muting

**97 distinct notification destinations.** The two largest ServiceNow credentials absorb 1,059 and 1,043 rule notifications respectively; nine ServiceNow endpoints cover the bulk. Email destinations are team aliases — `predix.timeseries.alerts@gevernova.com` (212), `cloud-mes_pager-duty@gevernova.com` (88).

**119 muting rules, all still active, and 101 of them have no end time** — permanent suppressions. 112 of 119 mute by `sf_detectorId`, meaning specific detectors have been silenced indefinitely rather than fixed or disabled. That's worth auditing before migration: those are alerts someone decided were noise but never removed.

### Gaps worth flagging

- **81 detectors have no notification configured on any rule.** They evaluate and fire into the void. Includes production-sounding alerts: `APM Error Rate Increased`, `APM Latency Degradation`, `Kafka - Consumer group lag`, `APM - Sudden change in service error rate`.
- **367 detectors (47%) have no runbook URL on any rule.** Overall rule-level runbook coverage is 88%, but it is entirely concentrated in the conforming `[sFx-SRE-...]` estate. The unconventionally-named half has almost none.
- **101 permanent mutes** with no expiry.

### Detector composition

- **Origin:** 739 Standard (UI/API-built), 39 AutoDetect, 2 AutoDetectCustomization
- **SignalFlow footprint:** 2.43M characters of program text across 780 detectors — avg 3,117 chars, max 32,316. 4,813 `detect()` calls total.
- **Function usage** is narrow: `publish`, `count`, `ceil`, `sum`, `scale`, `abs`, `mean` cover the vast majority. Only 18 uses of `detector_mean_std` (anomaly-style detection). This is a threshold-based estate — mechanically translatable, not algorithmically exotic.
- **Runbook coverage is strong:** 4,298 of 4,859 rules (88%) carry a Confluence runbook URL.
- 62 rules are individually disabled inside otherwise-active detectors.

---

## 4. Synthetics

50 tests — 36 HTTP, 12 API, 2 browser. 47 active, 3 paused. Most run every 5 minutes (38 tests); three run every 2 minutes.

**6 tests failed their last run:** `Splunk Cloud - GEDWest` (browser), `predix-io-registration-server.url`, `Audit-service prod-usw`, `time-series-canary-rearch`, plus two paused-and-failing Smart Factory Cloud tests. One test is literally named `TO-BE-REMOVED-smart-factory-cloud-PA-Robex-Server-Windows-Se`.

Coverage is heavily Predix/Smart Factory Cloud oriented across USW and EUC.

---

## 5. Metric cardinality — where the cost is

933,055 active MTS. The distribution is extraordinarily top-heavy:

| Metric | MTS | Type |
|---|---|---|
| `dns.lookup.duration_bucket` | 200,000 | Cumulative counter |
| `http.client.request.time_in_queue_bucket` | 183,375 | Cumulative counter |
| `k8s.container.status.reason` | 114,678 | Gauge |
| `spans` | 27,872 | Histogram |
| `dns.lookup.duration_{min,max,count,sum}` | 18,788 each | Gauge / counter |

**The top three metrics alone account for ~53% of total org cardinality.** The two `_bucket` series — 383,375 MTS combined, 41% of the org — are OpenTelemetry histograms exploded into one time series per bucket boundary, which is how Splunk O11y bills them.

Metric type split: 8,690 GAUGE, 1,082 COUNTER, 214 CUMULATIVE_COUNTER, 14 HISTOGRAM. No metrics are flagged as custom in the export.

---

## 6. Consolidation and cleanup opportunities

These are the numbers that should shape scoping — the raw object counts materially overstate what actually needs to migrate.

**Most of the object count is auto-provisioned personal space, not content.**

**906 of the 1,110 dashboard groups (82%) are email-named personal groups** — Splunk O11y provisions one per user on first login, each containing a single empty dashboard named after that user. 872 of the 873 empty dashboards inside personal space carry the owner's own email address as the dashboard title, and 863 of the 906 groups hold exactly one dashboard. This is platform behaviour, not accumulated clutter.

That materially changes the shape of the estate:

| View | Groups | Dashboards | Charts | Empty |
|---|---|---|---|---|
| Raw inventory | 1,110 | 1,909 | 13,241 | 907 |
| Personal auto-provisioned space | 906 | 971 | 1,098 | 873 |
| **Real shared estate** | **204** | **938** | **12,143** | **34** |

So the earlier "48% of dashboards are empty" reading is misleading. Outside personal space there are only **34 empty dashboards** — the shared estate is essentially all populated. The real problem is staleness, not emptiness:

- Of the 938 shared dashboards, **697 (74%) have not been updated in over a year**; only 183 (20%) inside 180 days.
- Only **23 dashboards are wired into alerting.**
- 906 personal groups implies roughly **906 provisioned users**, against 15 teams whose largest has 147 members.

The defensible migration target remains Tier A + Tier B — **208 dashboards, 2,875 charts** — but it should now be read as 22% of the *shared* estate, not of a headline count inflated by user provisioning.

**Detectors carry a QA-clone tax.**

- 174 detectors are `QA-` prefixed; **152 of them (87%) have an exact non-QA twin.** That is ~20% of the entire detector estate maintained in duplicate.
- 17 detectors share a name with another detector.
- Environment split: 367 PROD, 82 PREPROD. Region split: 270 USW, 167 EUC — the same monitors replicated per region.
- 426 detectors (55%) use no bracketed naming convention at all, so the `[sFx-SRE-ENV-REGION-SERVICE-ACCOUNT]` standard is only half-adopted.

After de-duplicating QA clones and collapsing region/env variants, the unique detector *logic* count is closer to **250–300 patterns**, not 780.

**Team ownership is not implemented.**

15 teams exist (MFG with 147 members, SRE with 19, the rest 0–10), but **zero dashboards and zero detectors are linked to any team**. Two teams — `SRE_PROD_Detectors` and `SRE_QA_Detectors` — are named for detector ownership but have 0 and 2 members respectively. There is no RBAC or ownership model to port; it would need to be built fresh.

---

## 6b. Ad-hoc query activity

**Splunk Observability Cloud persists no record of interactive queries.** SignalFlow typed into the Metric Finder, chart builder or Analytics workspace is executed and discarded — it is not stored in any object the inventory API can reach. There is no equivalent of a search audit log. Anything below is inference from *saved* artifacts, and the true volume of exploratory work is unmeasurable from this export.

What the saved artifacts show:

**Ad-hoc exploration that got saved is rare and heavily concentrated.**

- 906 users have a provisioned personal space. **Only 33 of them (3.6%) have ever saved a dashboard with any content in it.**
- Those 33 produced **98 dashboards and 1,098 charts** — 9% of the org's total chart count.
- **89 of the 98 (91%) are over a year stale.** Only 8 have been touched in the last 180 days.
- One user, `veerendra.hegde@ge.com`, owns 29 of the 98. The next three own 12, 8 and 5. The remaining 29 users own 1–4 each.

The named content is recognisably project work rather than throwaway exploration — `Pelican-DEV-Policy`, `Pelican-DEV-WebAPI`, `Pelican-PERF-Redis`, `apm-geda-perf-rds-dashboard`, `apm-meridium-ui-prod-euc`, `EKS - APM CASES`, `Audit-persister-EU`. These are personal builds that were never promoted into a shared group.

**Scratch and disposable naming across the whole estate: 82 dashboards.**

| Marker | Dashboards | Charts |
|---|---|---|
| Marked for deletion (`TO-BE-REMOVED`, `deprecated`, `obsolete`, `unused`) | 37 | 342 |
| `test` | 26 | 190 |
| Work-in-progress (`inprogress`, `draft`, `POC`) | 8 | 117 |
| `new` / `old` / `v2` | 5 | 60 |
| `debug` | 4 | 111 |
| `demo` / `example` / `sample` | 4 | 12 |
| `temp` / `scratch` / `sandbox` | 1 | 9 |

Notably **zero dashboards contain "copy", "clone" or "untitled"** — the classic ad-hoc duplication signature is absent. Combined with the 50 one-or-two-chart dashboards created and abandoned the same day, the picture is of an org where exploratory work is either done and discarded in-session, or built deliberately as a project artifact. There is little evidence of a heavy save-and-forget ad-hoc culture in the O11y platform.

**Migration implication.** Ad-hoc usage is not a meaningful migration workload here — 98 personal dashboards, 91% stale, concentrated in 33 users. Confirm with the four heaviest owners whether anything in their personal space is still live, then leave the rest. The more important question is the one this data cannot answer: how much *unsaved* interactive querying the SRE team does daily, and whether Elastic's Discover and Lens surfaces need to be part of enablement. That requires asking them.

---

## 7. Migration candidates — which dashboards to move

### First, strip the estate down to what is actually GE Vernova's

The 208-dashboard Tier A+B set still contains a large amount of content GE Vernova never built. Four exclusion classes:

| Exclusion class | Dashboards | Charts | Alert refs |
|---|---|---|---|
| Splunk vendor built-ins (bulk-updated 2026-05-21, creator `AAAAAAAAAAA`) | 59 | 705 | 0 |
| Explicitly `(deprecated)` in name or group | 36 | 338 | 0 |
| Splunk platform self-monitoring (`Organization metrics` group) | 10 | 183 | 0 |
| Personal scratch dashboards (email-named groups) | 8 | 96 | 0 |

The vendor cohort is unmistakable: 59 dashboards sharing one `lastUpdated` timestamp and one system creator ID, spread across Cloud Foundry, Kafka, Microsoft SQL, Docker, HAProxy, Windows IIS and JMX groups. That's a Splunk content refresh, not human editing. They carry **zero alert references between them.** None of these four classes should migrate — the Splunk self-monitoring dashboards become meaningless off-platform by definition.

**Core migration set: 141 dashboards, 2,074 charts — 7.4% of the original estate.** That set retains **4,043 of 4,045 alert references (99.95%).** Nothing operationally significant is lost by cutting the other 92.6%.

### Wave 1 — Replace with Elastic out-of-the-box integrations (do not rebuild)

**97 dashboards, 1,415 charts, 3,842 alert references (95% of all alert traffic).**

Nearly everything on-call actually uses is standard AWS and Kubernetes infrastructure monitoring — exactly what Elastic's integrations ship prebuilt dashboards for. These should be *retired and replaced*, not ported chart-by-chart.

| Elastic integration | Dashboards replaced | Charts | Alert refs |
|---|---|---|---|
| AWS RDS | 9 | 164 | 2,101 |
| AWS MQ / Kafka / MSK / SQS | 16 | 271 | 616 |
| Kubernetes / EKS | 52 | 676 | 511 |
| AWS ElastiCache / Redis | 2 | 21 | 392 |
| AWS ELB / ALB | 4 | 40 | 102 |
| AWS EC2 / EBS | 7 | 107 | 60 |
| Elasticsearch | 1 | 13 | 60 |
| OTel Collector | 3 | 74 | 0 |
| Hosts / infra | 3 | 49 | 0 |

**The single best migration candidate is `RDS Prod`** — 2,101 alert references, 102 detectors, 13 charts, in the group that carries 71% of all alert traffic. It is small, heavily used, and maps directly onto Elastic's AWS RDS integration. Prove the migration there and the highest-traffic path in the org is covered on day one.

Then in order: `MQ Prod` (443 refs, 18 charts), `Cache Instance` (348 refs, 10 charts), `K8s container` (301 refs, 9 charts), `ACTIVEMQ MQ` (143 refs, 11 charts), `ALB Prod` (86 refs, 7 charts, 42 detectors), `EC2 instances` (60 refs, 27 charts), `ELASTIC SEARCH PROD` (60 refs, 13 charts).

Every one of these is under 30 charts. The top four together are 50 charts and cover 3,193 alert references — **79% of all alert-driven dashboard traffic in a single week of work.**

### Gap analysis — what has no out-of-the-box Elastic equivalent

Verified against the Elastic Package Registry (492 packages; `aws` package v7.1.1 with 33 policy templates) rather than assumed. The core 141 splits four ways:

| Tier | Meaning | Dashboards | Charts | Alert refs |
|---|---|---|---|---|
| **A** | Dedicated Elastic integration with prebuilt dashboards | 108 | 1,513 | 2,900 |
| **B** | Data ingestible, but no prebuilt dashboard | 12 | 157 | 978 |
| **C** | No Elastic equivalent — full custom rebuild | 14 | 345 | 165 |
| **X** | Should not migrate at all | 7 | 59 | 0 |

#### Tier B — data comes across, dashboard does not

**12 dashboards, 157 charts, but 978 alert references (24% of all alert traffic).** This is the tier that matters most, because it is quietly high-value. The metrics are all reachable through the AWS integration's generic CloudWatch template — which exists explicitly "where no out of the box integration is available" — but no prebuilt visualisation ships with them.

| Dashboard | Alert refs | Charts | Gap |
|---|---|---|---|
| MQ Prod | 443 | 18 | AmazonMQ — `activemq` package targets self-managed brokers only |
| Cache Instance | 348 | 10 | ElastiCache — no dedicated package; `redis` package or CloudWatch generic |
| ACTIVEMQ MQ | 143 | 11 | AmazonMQ |
| Cache Prod | 44 | 11 | ElastiCache |
| Amazon MQ for ActiveMQ | 0 | 26 | AmazonMQ |
| MQ Instance / MQ PROD | 0 | 27 | AmazonMQ |
| Amazon MWAA ×3 | 0 | 41 | MWAA — `airflow` package targets self-managed Airflow only |
| EFS Usage | 0 | 7 | EFS — CloudWatch generic |
| ECR Usage | 0 | 6 | ECR — CloudWatch generic |

**AmazonMQ and ElastiCache together carry 978 alert references on 76 charts.** Both are managed AWS services where Elastic ships an integration for the *self-managed* equivalent (ActiveMQ, Redis) but not the managed AWS variant. Data ingestion is straightforward via CloudWatch; the dashboards need building. Budget for this explicitly — it is the single most under-estimated piece of the migration.

#### Tier C — genuinely bespoke, no shortcut

**14 dashboards, 345 charts, 165 alert references.**

| Dashboard | Alert refs | Charts | Notes |
|---|---|---|---|
| CONFIG-SERVICE | 165 | 10 | GE TMS application service. The EKS layer is covered by the Kubernetes integration; the app-level service metrics are not. Highest-value custom asset in the estate. |
| SFC Template | 0 | 84 | Smart Factory Cloud — GE manufacturing platform |
| Security Service Dashboard | 0 | 75 | Platform Security Services |
| Smart Factory Cloud | 0 | 50 | |
| App & Services (prod, US West) | 0 | 22 | |
| **RTE Memory ×8** | 0 | 96 | SmartSignal — one per customer site: Sonelgaz, Steg, Azito, Conoco-Phillips, TierraMojada, Alghanim, sce_prod, sm-stage-auto-u |
| Executive multi Tenant Heat Dashboard | 0 | 8 | Smart Factory Cloud |

The eight **SmartSignal RTE Memory** dashboards are the clearest consolidation win anywhere in this estate: 12 charts each, identical structure, differing only by customer site. In Elastic that is **one dashboard with a site filter** — 96 charts collapsing to roughly 12.

Excluding those duplicates, the true bespoke rebuild is **7 distinct dashboards, ~261 charts**, dominated by Smart Factory Cloud (142 charts across three) and Security Service Dashboard (75).

#### Tier X — should not migrate

7 dashboards, 59 charts: the `Executive Level` group (License usage overview, Token usage, RUM, APM/IMM, Logs, Synthetics overview) is Splunk platform self-monitoring and billing, meaningless off-platform. Plus one dashboard literally named `test`.

### Wave 2 — Custom rebuild required

**44 dashboards, 659 charts, 201 alert references.**

This is the genuinely bespoke content with no Elastic equivalent:

| Dashboard | Charts | Alert refs | Note |
|---|---|---|---|
| CONFIG-SERVICE | 10 | 165 | TMS EKS services — highest-value custom asset |
| Tables | 18 | 32 | Timeseries Keyspace, updated 2026-08-10 |
| SFC Template | 84 | 0 | Largest build in the org; Smart Factory Cloud |
| Security Service Dashboard | 75 | 0 | Platform Security Services |
| Smart Factory Cloud | 50 | 0 | |
| Service / Service endpoint | 40 | 0 | APM services |
| Predix-Timeseries HAProxy (US + EU) | 42 | 4 | Two region variants |
| App & Services (prod, US West) | 22 | 0 | |
| SFC Prod Synthetics Uptime | 13 | 0 | |

`CONFIG-SERVICE` is the priority here — 165 alert references and only 10 charts. The Smart Factory Cloud and Security Service dashboards are large and recently maintained but alert-unreferenced, so confirm with their owners that they're in live use before committing 209 charts of rebuild effort to them.

### Wave 3 — Do not migrate

The four exclusion classes above (113 dashboards, 1,322 charts) plus all of Tier C and D (794 dashboards, 10,366 charts) and the 907 empty dashboards. **Total left behind: roughly 1,768 dashboards and 11,167 charts.**

### Consolidation on the way in

Within the core 141 there are **14 name-collapse groups covering 28 dashboards** that are pure region or environment variants — `RDS PREPROD`/`RDS Prod`, `MQ PROD`/`MQ Prod`, `ALB Prod`/`ALB Prod EUC`, `Timeseries MSK-US WEST`/`Timeseries MSK -EU`, `Prod - Pods`/`PreProd - PODS`, `Predix-Timeseries-Kafka-Prod`/`-prod-EU`, and duplicate `Debug_EKS` builds. In Elastic these collapse into single dashboards with a region/environment filter, taking the core set closer to **125 dashboards**.

---

## 8. Elastic positioning

**Cardinality is the strongest commercial argument.** 41% of GE Vernova's MTS spend is OTel histogram bucket boundaries billed as individual time series. Elasticsearch stores histograms as a native `histogram` field — one document field, not 200,000 series. That single structural difference addresses roughly 383k of 933k MTS. Add `k8s.container.status.reason` at 114k and the top-three story covers half the org.

**Alert migration is mechanical, not research.** 780 detectors averaging 3,117 chars of threshold-based SignalFlow, with narrow function usage and only 18 anomaly-style detectors. These map cleanly onto Elastic threshold and custom-query rules. The 88% runbook coverage transfers directly. De-duplication first cuts the job by roughly two-thirds.

**Dashboard migration is a triage exercise, not a port.** 48% empty, 90% stale, and only 23 dashboards wired into any alert. The honest conversation is "these 208 have a defensible claim to migrate," not "how do we move 1,909." Frame it as an opportunity to leave six years of accumulated clutter behind — and lead with `RDS Prod`, `MQ Prod`, `K8s container`, `Cache Instance` and `EC2 instances`, since rebuilding those five plus the `SRE EKS - AWS Services USW` group covers the majority of what on-call actually touches.

**Two integration must-haves:** ServiceNow (78% of all alert notifications) and the existing OpenTelemetry pipeline. Neither is a blocker for Elastic, but both need to be in the day-one design.

**Alert fatigue is a discovery hook.** 97% of trigger rules are Critical or Major, and 81 detectors notify nobody. Ask the SRE team what their weekly page volume looks like — the severity distribution suggests the answer is uncomfortable, and it opens the door to a conversation about signal quality rather than tool swap.

---

## 9. Data gaps

The inventory API does not expose:

- **Dashboard view counts** — the alert-reference ranking in §2 is a strong proxy for on-call usage, but it cannot see dashboards people browse manually without being paged there. Tier B (185 dashboards) is where that blind spot lives.
- **Alert firing history / incident counts** — no way to identify noisiest detectors
- **Ingest volume or billing figures** — MTS count is a proxy, not spend
- **Log and trace volumes** — this export covers metrics, dashboards, and detectors only

To close the first two, the inventory script would need to be extended against Splunk O11y's alert-events and audit-log APIs with the same `SFX_TOKEN`, then re-run. That would turn "top 5 by chart count" into "top 5 by actual use" — worth doing before the customer readout if the token allows it.

**Rows of raw data behind this summary:** `dashboards.csv` (1,909), `detectors.csv` (780, includes full flattened SignalFlow), `dashboard_groups.csv` (1,110), `metrics.csv` (10,000 sorted by MTS), `synthetics_tests.csv` (50), `alert_muting_rules.csv` (119), `teams.csv` (15).
