# webMethods secrets — rendered by Vault Agent
# Source: Vault KV v2 at stoa/vps/webmethods + stoa/shared/keycloak
{{ with secret "stoa/data/vps/webmethods" }}
WM_ADMIN_PASSWORD={{ .Data.data.WM_ADMIN_PASSWORD }}
{{ end }}
{{ with secret "stoa/data/shared/keycloak" }}
KC_ADMIN_USER={{ .Data.data.KC_ADMIN_USER }}
KC_ADMIN_PASSWORD={{ .Data.data.KC_ADMIN_PASSWORD }}
{{ end }}
