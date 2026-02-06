## CAB-1114 — STOA Logs : OpenSearch Multi-Tenant OIDC + RGPD

### Vue d'ensemble

| Phase | Sujet | Status |
|-------|-------|--------|
| Phase 1 | Déploiement OpenSearch + Ingestion | ✅ Done |
| Phase 2 | RGPD Pipeline (redaction) | ✅ Done |
| Phase 3 | Multi-Tenant OIDC Security | ✅ Done |
| Phase 4 | Intégration Console STOA | ✅ Done |

---

### Phase 1 — Déploiement OpenSearch + Ingestion ✅

- ✅ OpenSearch 2.11.0 + healthcheck
- ✅ Dashboards brandé "STOA Logs"
- ✅ Nginx `/logs/*` + strip X-Frame-Options
- ✅ Index template `stoa-logs-*` + ISM 14 jours
- ✅ 2 tenants avec données réalistes (tenant-alpha, tenant-beta)

---

### Phase 2 — RGPD Pipeline (redaction) ✅

- ✅ **Mode nominal (2xx)** : `request_body` + `response_body` strippés entièrement par le processor `remove`
- ✅ **Mode erreur (4xx/5xx)** : payload indexé avec redaction automatique via Painless script (7 patterns PII)
  - JWT → `[TOKEN:REDACTED]`
  - IBAN → `[IBAN:REDACTED]`
  - Carte bancaire → `[CARD:REDACTED]`
  - N° sécu FR → `[SSN:REDACTED]`
  - API key/token → `[APIKEY:REDACTED]`
  - Email → `[EMAIL:REDACTED]`
  - Téléphone FR → `[PHONE:REDACTED]`
- ✅ Ingest pipeline `stoa-rgpd-redaction` configuré (3 processors: remove/script/set)
- ✅ Pipeline attaché à l'index template `stoa-logs-*` (`default_pipeline`)
- ✅ Patterns dans fichier externalisé : `deploy/opensearch/pipelines/stoa-rgpd-redaction.json`
- ✅ **Test positif** : appel 500 avec email+JWT → masqués dans l'index
- ✅ **Test positif** : appel 400 avec IBAN+téléphone → masqués dans l'index
- ✅ **Test négatif** : appel 200 → zéro payload stocké
- ✅ Init script mis à jour avec données de test RGPD + vérification automatisée
- ✅ 4 champs ajoutés : `request_body`, `response_body`, `rgpd_redacted`, `rgpd_redacted_fields`
- **Commit** : `35fa3943` — `feat(mcp): add RGPD redaction pipeline for API traces (CAB-1114)`

---

### Phase 3 — Multi-Tenant OIDC Security ✅

- ✅ OpenSearch Security plugin activé (remplace `DISABLE_SECURITY_PLUGIN=true`)
- ✅ TLS avec demo certificates + `opensearch.yml` config externalisée
- ✅ Intégration OIDC : Keycloak → OpenSearch backend authentication (`openid_auth_domain`)
- ✅ Client OIDC `opensearch-dashboards` dans Keycloak realm (confidential, avec `tenant_id` mapper)
- ✅ 3 rôles OpenSearch : `stoa_logs_admin` (all), `stoa_logs_tenant_oasis_gunters`, `stoa_logs_tenant_ioi_sixers`
- ✅ Mapping rôle OIDC → tenant : `cpi-admin` → admin, users → tenant-specific roles
- ✅ Tenants alignés avec Keycloak : `tenant-alpha/beta` → `oasis-gunters/ioi-sixers`
- ✅ OpenSearch Dashboards : login via Keycloak SSO (`opensearch_security.auth.type: ["openid"]`)
- ✅ Multi-tenancy Dashboards : saved objects isolation (`opensearch_security.multitenancy.enabled: true`)
- ✅ Init script : `securityadmin.sh` + auth curl + RGPD pipeline + tenant rename
- ✅ `extra_hosts: localhost:host-gateway` pour OIDC discovery depuis les containers Docker
- ✅ **Test script** : `test/test-tenant-isolation.sh` (6 assertions : 3 positifs, 3 négatifs)
- ✅ Nginx : cookie forwarding pour sessions OIDC
- **Fichiers clés** :
  - `config/opensearch/opensearch.yml` — Config principale avec TLS
  - `config/opensearch/security/` — 6 fichiers (config, internal_users, roles, roles_mapping, action_groups, tenants)
  - `config/opensearch-dashboards/opensearch_dashboards.yml` — OIDC + multitenancy
  - `init/keycloak-realm.json` — Client `opensearch-dashboards` ajouté
  - `init/init-opensearch.sh` — Rewrite complet Phase 1+2+3

---

### Phase 4 — Intégration Console STOA ✅

- ✅ `LogsEmbed.tsx` créé (iframe avec loading/error/fullscreen, thème amber)
- ✅ Route `/logs` dans `App.tsx` (lazy-loaded)
- ✅ Navigation sidebar "Logs" avec icône `ScrollText` + raccourci `g+l`
- ✅ `config.ts` : `logs.url` corrigé (`/logs/` via reverse proxy, remplace Grafana)
- ✅ SSO transparent : même domaine Keycloak, cookies forwarded par nginx (`proxy_set_header Cookie`)
- ✅ Nginx `/logs/*` : `X-Frame-Options` strippé + CSP `frame-ancestors` autorise Console
- ✅ Lint (0 errors) + TypeScript (0 errors)
- **Validation restante** : parcours complet Console → Logs → recherche appel erreur → payload masqué visible (nécessite `docker compose up`)

---

### Règle de fallback

- Phase 1 + 2 = démo RGPD crédible ✅✅
- Phase 1 + 2 + 3 = démo complète multi-tenant ✅✅✅
- Phase 1 + 2 + 3 + 4 = intégration produit complète ✅✅✅✅
- **Ne jamais commencer Phase N+1 si Phase N n'est pas 100% DoD**
