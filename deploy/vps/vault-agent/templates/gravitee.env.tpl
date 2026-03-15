# Gravitee secrets — rendered by Vault Agent
# Source: Vault KV v2 at stoa/vps/gravitee
{{ with secret "stoa/data/vps/gravitee" }}
GRAVITEE_ADMIN_PASSWORD={{ .Data.data.GRAVITEE_ADMIN_PASSWORD }}
GRAVITEE_MONGODB_PASSWORD={{ .Data.data.GRAVITEE_MONGODB_PASSWORD }}
{{ end }}
