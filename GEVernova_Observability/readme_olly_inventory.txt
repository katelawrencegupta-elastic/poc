#README - Take an inventory of a Splunk Observability Cloud org

#Usage
export SFX_REALM="us1"
export SFX_TOKEN="<org token with API access>"

# Quick pass: dashboards, detectors, synthetics, metric names
python3 o11y_inventory.py --include-metrics

# Full pass with per-metric MTS usage (slower)
python3 o11y_inventory.py --mts-counts


#What will this script create?

o11y_inventory/
├── inventory_summary.txt        # counts of every object type
├── dashboard_groups.csv
├── dashboards.csv
├── detectors.csv
├── alert_muting_rules.csv
├── teams.csv
├── synthetics_tests.csv
├── metrics.csv                  # only with --include-metrics / --mts-counts
├── charts.csv                   # only with --include-charts
└── raw/
    ├── dashboard_groups.json    # complete API payloads, nothing dropped
    ├── dashboards.json
    ├── detectors.json           # includes full SignalFlow programText
    ├── alert_muting_rules.json
    ├── teams.json
    ├── synthetics_tests.json
    └── metrics.json

- dashboards.csv — dashboard name, its parent group (ID and resolved name), chart count, creator, created/last-updated dates. Good for spotting stale dashboards.
- dashboard_groups.csv — group name, how many dashboards it holds, which teams own it.
- detectors.csv — alert name, enabled/disabled status, origin (UI-built vs Terraform/API), a compact per-rule summary like Critical(2 notif); Warning(1 notif), owning teams, and the full SignalFlow program text flattened onto one line. This is the file you'd use to scope an alert migration.
- synthetics_tests.csv — test name, type (browser/api/http/port), active or paused, run frequency in minutes, locations, last run status.
- metrics.csv — metric name, type (gauge/counter/cumulative), whether it's custom, and — if you ran --mts-counts — an mts_count column sorted descending, so the most expensive metrics by cardinality are at the top.
- teams.csv and alert_muting_rules.csv — supporting context (member counts, active mute windows).