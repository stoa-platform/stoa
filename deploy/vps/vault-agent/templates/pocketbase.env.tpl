# PocketBase secrets — rendered by Vault Agent
# Source: Vault KV v2 at stoa/vps/pocketbase
{{ with secret "stoa/data/vps/pocketbase" }}
PB_ADMIN_EMAIL={{ .Data.data.PB_ADMIN_EMAIL }}
PB_ADMIN_PASSWORD={{ .Data.data.PB_ADMIN_PASSWORD }}
{{ end }}
