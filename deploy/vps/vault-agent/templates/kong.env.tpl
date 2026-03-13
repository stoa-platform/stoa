# Kong secrets — rendered by Vault Agent
# Source: Vault KV v2 at stoa/vps/kong
{{ with secret "stoa/data/vps/kong" }}
KONG_ADMIN_TOKEN={{ .Data.data.KONG_ADMIN_TOKEN }}
{{ end }}
