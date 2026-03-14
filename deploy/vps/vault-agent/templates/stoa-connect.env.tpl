# STOA Connect secrets — rendered by Vault Agent
# Source: Vault KV v2 at stoa/shared/stoa-connect
# Shared across all VPS instances (same API key for all connect agents)
{{ with secret "stoa/data/shared/stoa-connect" }}
STOA_CONTROL_PLANE_URL={{ .Data.data.STOA_CONTROL_PLANE_URL }}
STOA_GATEWAY_API_KEY={{ .Data.data.STOA_GATEWAY_API_KEY }}
{{ end }}
