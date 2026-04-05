#!/bin/bash
# Resolve env vars in pipeline template before starting Data Prepper
cat > /usr/share/data-prepper/pipelines/pipelines.yaml << YAML
otel-traces-pipeline:
  source:
    otel_trace_source:
      port: 4317
      ssl: false
      health_check_service: true
  sink:
    - opensearch:
        hosts: ["https://opensearch:9200"]
        username: "${OPENSEARCH_USER}"
        password: "${OPENSEARCH_PASSWORD}"
        insecure: true
        index_type: trace-analytics-raw
YAML

exec /usr/share/data-prepper/bin/data-prepper
