
#!/bin/bash
ELASTIC_API_KEY=SENOQVo1OEJtYXVQbmh2S3Fzc3E6Ylh2TXFlcmlqaXFfOENNS296MzE3Zw==

curl -sS -X POST \
  "https://klggehpoc-eb6d47.kb.us-central1.gcp.elastic.cloud/api/workflows/workflow/ct-hybrid-search-api/run" \
  -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "query": "gantry abort detector",
      "size": 10,
      "hospital": "",
      "sysid": "",
      "severity": "Critical",
      "rank_window_size": 100,
      "rank_constant": 60
    }
  }'
