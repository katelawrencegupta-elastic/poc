# Elastic backups

Timestamped exports of Kibana **workflows**, Agent Builder **agents**, and **tools**.

- `latest/` — most recent backup
- `<UTC timestamp>/` — immutable snapshot

## Restore notes

- Workflows: upsert YAML via `PUT /api/workflows/workflow/{id}` with `{"yaml": "..."}`.
- Agents: recreate/update via Agent Builder API `/api/agent_builder/agents`.
- Built-in agents/tools (`readonly: true`) are exported for reference; they are managed by Elastic.
