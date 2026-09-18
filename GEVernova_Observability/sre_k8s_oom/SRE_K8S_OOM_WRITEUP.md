# SRE space — Kubernetes OOM / pod-crash instrumentation

**Kibana space:** `sre`  
**Project:** my-observability-project-f2e495 (Elastic Observability, us-west-2)  
**Scope:** Kubernetes OOM and multi-pod crash detection only (OpenSearch and ALB/WAF omitted)

---

## Purpose

Notice when Kubernetes pods crash or run out of memory, open an Observability case with evidence and root-cause analysis (RCA), and record that a **code ticket** should be opened — without changing anything live in the cluster.

---

## Dashboard

**`[SRE] K8s OOM / crash`** (`sre-k8s-oom-crash`)

Three views:

1. **OOM phrases** in container logs  
2. **Multi-pod restart bursts**  
3. Containers near their **memory limit** (≥95% utilization)

Default time window is oriented toward sparse historical OOM signals (e.g. last 3 days).

---

## Alerts

All classic custom-threshold rules below are **enabled**.

| Alert ID | Name | Watches for | What happens |
|----------|------|-------------|--------------|
| `gev-sre-k8s-oom-phrase` | [SRE] K8s OOM phrase in container logs | Log phrases such as “Out of memory”, `OutOfMemoryError`, `OOMKilled` | Starts the **auto-code** case workflow |
| `gev-sre-k8s-mem-limit-saturate` | [SRE] K8s container memory limit ≥ 95% | Container `memory_limit_utilization` ≥ 0.95 | Starts the **auto-code** case workflow |
| `gev-sre-k8s-restart-burst` | [SRE] K8s multi-pod restart burst | High absolute restart counters (noisy) | **Server log only** — does **not** open a case |

**Alert states that start the workflow (OOM phrase + mem-limit):** `new` and `recovered` (not `ongoing`).

**v2 ES|QL companions** exist for dashboard / future use (`restart-burst`, `oom-phrase`, `mem-limit-saturate`, `oomkilled-status`). They do **not** auto-start workflows today (`actions: null`). The OOMKilled status rule needs Wave 0 OTel `status.reason` rolled to clusters before it can breach reliably.

---

## Workflows

### Auto path (what alerts use) — `gev-sre-k8s-oom-crash-auto-code`

Enabled. Triggered by OOM-phrase / mem-limit alerts, or manually / via tool `gev-sre-k8s-oom-run-auto-code`.

1. Creates or updates an Observability case  
2. Pulls restart, memory, and OOM-log evidence (ES|QL)  
3. Classifies the crash (`oom.app` / `oom.likely` / `crash.not_oom` / `crash.unknown`)  
4. Writes RCA and proposed remediations  
5. **Auto-approves** as `approve_code_ticket` (no human-in-the-loop pause)  
6. Does **not** patch Deployments or mutate the cluster  

### HITL path (manual / agent) — `gev-sre-k8s-oom-crash-case`

Enabled. Same investigation path, but pauses for a human to choose:

- `approve_raise_memory_limits` — record a GitOps memory request/limit bump proposal  
- `approve_code_ticket` — record a code/config fix proposal  
- `reject_false_positive`  

Agent tool: `gev-sre-k8s-oom-run`.

### Concurrency

Both workflows use **max 1** execution per key:

`cluster | namespace | deployment | alert_status`

with **queue** strategy. Unfinished runs (especially old HITL `waiting_for_input`) block later runs for the same key until resumed or cancelled.

---

## Agent

**`gev-sre-k8s-oom`** — SRE K8s OOM / crash analyst

- Detects crash anomalies with ES|QL (prefer multi-pod restart **deltas**, not absolute lifetime counters)  
- Investigates OOM phrases / memory util / logs  
- Produces Analysis & Insights (memory trend, runaway process, leak vs contention)  
- Proposes Resolution & Remediation (GitOps limit bumps and/or code tickets)  
- Can start a case workflow via tools  

Default tool points at the HITL workflow; `gev-sre-k8s-oom-run-auto-code` is available for the no-HITL path.

---

## Day-to-day flow

1. **OOM log phrase** or **mem-limit ≥ 95%** alert fires → auto-code workflow → case + RCA + “open a code ticket”  
2. **Restart-burst** alert → log only; use the dashboard or agent for true multi-pod restart deltas  
3. Operators can still run the **HITL** workflow by hand when a human decision is preferred  

---

## Known gaps / caveats

- **Fargate / no memory limit:** some services expose raw memory (`working_set`, `usage`, `rss`) but **not** `memory_limit_utilization` when no container limit is set. RCA then leans on OOM log phrases and restart deltas.  
- **Wave 0 OTel:** `status.reason == OOMKilled` detection needs collector metric enablement rolled to clusters.  
- **Classic restart-burst** uses absolute restart counters and is intentionally detached from the case workflow to avoid noise.  
- Stuck **HITL** executions on the old path can leave concurrency keys occupied and queue newer runs until cleared.

---

## Asset quick reference

| Kind | ID |
|------|-----|
| Dashboard | `sre-k8s-oom-crash` |
| Alert (classic) | `gev-sre-k8s-oom-phrase` |
| Alert (classic) | `gev-sre-k8s-mem-limit-saturate` |
| Alert (classic) | `gev-sre-k8s-restart-burst` |
| Workflow (alerts) | `gev-sre-k8s-oom-crash-auto-code` |
| Workflow (HITL) | `gev-sre-k8s-oom-crash-case` |
| Agent | `gev-sre-k8s-oom` |
| Tool (auto) | `gev-sre-k8s-oom-run-auto-code` |
| Tool (HITL) | `gev-sre-k8s-oom-run` |
| Install | `sre_k8s_oom/apply.py` |

---

*Generated for GE Vernova Observability PoC — Kibana `sre` space.*
