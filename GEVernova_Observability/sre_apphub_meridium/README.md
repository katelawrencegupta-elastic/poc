# SRE AppHub → Meridium latency

Implements detection → investigation → HITL for **client-side latency**
from AppHub to APM Classic / Meridium ingress, mirroring `sre_k8s_oom/`
and `sre_opensearch/`.

AppHub does not call `meridium-webapi` as a Kubernetes service name. The
observable hop is `predix-apphub-*` HTTPS client spans to:

- `apm-classic-stage.apm.stage.usw02.15.energy:443` (volume path)
- `apm-classic-dev.apm-temp.dev.usw02.15.energy:443`
- `apm-classic-beta-stage.lb2.apm.stage.usw02.15.energy:443`
- `apm-meridium-ui-stage.apm.stage.usw02.15.energy:443` (rare)

## What is here

| Path | Purpose |
|---|---|
| `esql/*.esql` | Breach queries for alerting v2 |
| `kibana/*-v2.json` | Written by `apply.py` on install |
| `dashboards.py` | ES\|QL KPI / table / auto-bucket line charts |
| `vega.py` | Heatmap + host-bar queries and inline vis configs |
| `kibana/sre-apphub-meridium-latency.json` | Dashboard (written on install) |
| `kibana/workflows/gev-sre-apphub-meridium-latency-case.yaml` | Case + evidence + RCA + HITL |
| `kibana/workflows/gev-sre-apphub-meridium-latency-auto.yaml` | Same path, no HITL — RCA-based escalate / investigate |
| `kibana/workflows/gev-sre-apphub-meridium-latency-auto-code.yaml` | Same path, no HITL — auto `investigate_apphub_proxy` |
| `kibana/agents/gev-sre-apphub-meridium.json` | Agent Builder analyst |
| `kibana/tools/gev-sre-apphub-meridium-run.json` | Manual HITL workflow tool |
| `kibana/tools/gev-sre-apphub-meridium-run-auto.json` | Manual RCA-based auto-approve tool |
| `kibana/tools/gev-sre-apphub-meridium-run-auto-code.json` | Manual auto-code-ticket workflow tool |
| `kibana/cases/configure-fields.json` | Case template only (no new custom fields) |
| `apply.py` | Install into Kibana `sre` space |

## Install

```bash
cd sre_apphub_meridium
ELASTIC_API_KEY=... python3 apply.py            # verify + dashboard + rules + workflow
ELASTIC_API_KEY=... python3 apply.py dashboard
ELASTIC_API_KEY=... python3 apply.py rules
ELASTIC_API_KEY=... python3 apply.py workflow
ELASTIC_API_KEY=... python3 apply.py verify
```

Dashboard: `/s/sre/app/dashboards#/view/sre-apphub-meridium-latency` (default last 3 days).

## Rules

| Rule id | Severity intent | Signal | Auto-starts workflow |
|---|---|---|---|
| `gev-sre-apphub-meridium-latency` | P2 | v2: dest avg ≥ 500 ms, ≥30 calls; classic: avg span ≥ 500 ms | classic yes |
| `gev-sre-apphub-meridium-errors` | P1 | v2: fail share ≥ 5%, ≥20 calls; classic: ≥20 failure spans | classic yes |
| `gev-sre-apphub-meridium-timeouts` | P1 | ≥3 client spans ≥ 30 s | classic yes |

Alerting v2 rules still have `actions: null`. Classic companions on
`traces-*` attach `system-connector-.workflows` →
`gev-sre-apphub-meridium-auto-approve` on **new** and **recovered**
(RCA → escalate or investigate; no HITL). The HITL workflow
`gev-sre-apphub-meridium-latency-case` remains for manual / agent tool
`gev-sre-apphub-meridium-run`.

## Notes

- Case customFields are capped at **10**. Latency cases **reuse**
  `account-id`=caller service, `region`=destination host,
  `domain-name`=destination host, `node-id`=`apphub-client`.
  All four required OpenSearch slots must be set on create or Kibana
  rejects the case.
- Auto-approve (alerts): RCA picks `escalate_meridium_owners` or
  `investigate_apphub_proxy`. HITL variant still offers those plus
  `reject_false_positive`.
- The workflow never changes routing or service config.
