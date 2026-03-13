# Netbox secrets — rendered by Vault Agent
# Source: Vault KV v2 at stoa/vps/netbox
{{ with secret "stoa/data/vps/netbox" }}
NETBOX_DB_PASSWORD={{ .Data.data.NETBOX_DB_PASSWORD }}
NETBOX_SECRET_KEY={{ .Data.data.NETBOX_SECRET_KEY }}
NETBOX_SUPERUSER_PASSWORD={{ .Data.data.NETBOX_SUPERUSER_PASSWORD }}
NETBOX_API_TOKEN={{ .Data.data.NETBOX_API_TOKEN }}
{{ end }}
