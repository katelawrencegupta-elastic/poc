# SRE K8s OOM / multi-pod crash detection

Implements the detection → investigation → HITL remediation loop for
anomalous Kubernetes pod crashes (especially OOM), mirroring
`sre_opensearch/`.

## What is here

| Path | Purpose |
|---|---|
| `esql/*.esql` | Breach queries for alerting v2 |
| `kibana/*-v2.json` | Written by `apply.py` on install |
| `dashboards.py` | ES|QL Lens panels for OOM / restart burst / mem saturate |
| `kibana/sre-k8s-oom-crash.json` | Dashboard `[SRE] K8s OOM / crash` (written on install) |
| `kibana/workflows/gev-sre-k8s-oom-crash-case.yaml` | Case + evidence + RCA + HITL |
| `kibana/workflows/gev-sre-k8s-oom-crash-auto-code.yaml` | Same path, no HITL — auto `approve_code_ticket` |
| `kibana/agents/gev-sre-k8s-oom.json` | Agent Builder analyst |
| `kibana/tools/gev-sre-k8s-oom-run.json` | Manual HITL workflow tool |
| `kibana/tools/gev-sre-k8s-oom-run-auto-code.json` | Manual auto-code-ticket workflow tool |
| `kibana/cases/configure-fields.json` | Extra case fields/template (merged) |
| `apply.py` | Install into Kibana `sre` space |

## Wave 0 (OTel) — required for OOMKilled status alerts

Already patched in repo (must be rolled to clusters):

- `elastic-otel-values-live.yaml`
- `otel.yaml` / `otelnew.yaml`

Enables:

```yaml
k8s_cluster:
  metrics:
    k8s.container.status.reason: { enabled: true }
    k8s.container.status.state: { enabled: true }
    k8s.pod.status_reason: { enabled: true }
```

Until collectors pick this up, `gev-sre-k8s-oomkilled-status` will not breach.
Phrase + restart + memory rules still work.

## Install

```bash
cd sre_k8s_oom
ELASTIC_API_KEY=... python3 apply.py            # verify + dashboard + rules + workflow
ELASTIC_API_KEY=... python3 apply.py dashboard  # sre-k8s-oom-crash + v2 rule artifacts
ELASTIC_API_KEY=... python3 apply.py rules
ELASTIC_API_KEY=... python3 apply.py workflow
ELASTIC_API_KEY=... python3 apply.py verify
```

Dashboard: `/s/sre/app/dashboards#/view/sre-k8s-oom-crash` (default last 3 days).
KPIs and tables use the same ES|QL as the v2 rules (OOM phrase, multi-pod restart Δ, memory-limit ≥95%). `OOMKilled` status.reason is omitted until Wave 0 collectors emit the field.

## Rules

| Rule id | Severity intent | Signal | Auto-starts workflow |
|---|---|---|---|
| `gev-sre-k8s-restart-burst` | P2 | v2: ≥2 pods Δrestarts; classic: max restarts ≥ 5 | **no** (classic too noisy; agent/v2 detect) |
| `gev-sre-k8s-oom-phrase` | P1 | OOM log phrases (v2 QSTR + classic count) | classic yes |
| `gev-sre-k8s-mem-limit-saturate` | P2 | memory_limit_utilization ≥ 0.95 | classic yes |
| `gev-sre-k8s-oomkilled-status` | P1 | status.reason == OOMKilled (v2 only; needs Wave 0) | no (v2) |

### Agent loop (Detection → Investigation → Analysis → Remediation)

The Agent Builder agent `gev-sre-k8s-oom` is instructed to:

1. **Detect** anomalous multi-pod restart Δ via ES|QL without the user naming OOM or a deployment.
2. **Investigate** OOM phrases / memory util / status.reason for those deployments.
3. **Analyze** memory trend, runaway/suspect process from logs, and leak vs contention vs undersized limit.
4. **Remediate (propose only)** concrete GitOps memory request/limit bumps and/or code tickets for leaks/runaway jobs — never patch live clusters.
5. **Case** via `gev-sre-k8s-oom-run` → RCA + HITL (`approve_raise_memory_limits` / `approve_code_ticket` / `reject_false_positive`).

Auto-wake of the workflow (without chat) still comes from classic **OOM phrase** and **mem-limit saturate** alert actions.

Classic `observability.rules.custom_threshold` companions attach
`system-connector-.workflows` → `gev-sre-k8s-oom-crash-auto-code` on **new** and
**recovered** (auto `approve_code_ticket`; no HITL). The HITL workflow
`gev-sre-k8s-oom-crash-case` remains for manual / agent tool `gev-sre-k8s-oom-run`.

## Notes

- Alerting v2 rules still have `actions: null`. Classic companions are the
  path that auto-starts the workflow today.
- Case customFields are capped at **10** in the sre space (8 already used by
  OpenSearch). K8s cases **reuse** existing slots:
  `account-id`=cluster, `region`=namespace, `domain-name`=deployment,
  `node-id`=container. Tags + title still carry the real k8s identity.
- Auto-code workflow never patches Deployment memory limits — it records
  `approve_code_ticket` on the case only. HITL variant still available manually.
- Fargate pods often have null kubelet memory fields; classifier falls back to
  `crash.unknown` or `oom.app` from logs.
- Classic restart companion is coarser than v2 (absolute max ≥ 5, not multi-pod
  Δ). Prefer the v2 signal for accuracy; classic exists so something still
  pages the workflow.
