# Audit Console Observability — 2026-05-07

**Périmètre**: 3 pages console post-PR codex #2713 (`fix(ui): consolidate observability product navigation`) et #2715 (`fix(ui): consolidate Live Calls trace details`).

- `/observability/live-calls` → composant `pages/CallFlow/CallFlowDashboard.tsx`
- `/audit-log` → composant `pages/AuditLog.tsx`
- `/observability/security` → composant `pages/GatewayGuardrails/GuardrailsDashboard.tsx`

**Evidence**: captures dans `01-live-calls.png`, `02-audit-log.png`, `03-security.png`. Tenant testé: `free-aech` (CPI Admin role).

---

## Verdict global

Codex a fait le travail de **plomberie URL** (renommer les routes, ajouter redirects, breadcrumbs, sub-nav). Aucune **donnée nouvelle** n'a été câblée et aucun **mock résiduel** n'a été nettoyé. Le résultat est une "façade" propre devant des composants tels quels — d'où le sentiment de restitution faible.

Les trois pages remontent au moins une donnée incohérente, vide, ou trompeuse en environnement prod actuel.

---

## 1. `/observability/live-calls`

**Component**: `control-plane-ui/src/pages/CallFlow/CallFlowDashboard.tsx` (renommé via redirect, jamais retitré).

### Findings

| # | Sévérité | Symptôme observé | Cause racine | Fichier |
|---|---|---|---|---|
| L1 | **HIGH** | KPI affiche `Total Requests (1h) = 39.3K` et en bas Gateway/Link/Connect = "No traffic" pour les 3. | Per-mode breakdowns filtrent `job=~"stoa-gateway\|stoa-link\|stoa-connect"`. Le total agrège **toutes les séries `stoa_http_requests_total` sans filtre `job`** — donc inclut les métriques cp-api (préfixe `stoa_control_plane_*`, mais possible collision sur `stoa_http_requests_total`) et/ou des scrapes sous d'autres `job=`. Les breakdowns ne matchent rien. | `CallFlowDashboard.tsx:142-181` |
| L2 | **HIGH** | "Top Routes by Latency (P95)" et "Traffic Heatmap" affichent une seule ligne `unknown`. | `topk(8, histogram_quantile(0.95, sum by (le, path) (...)))` agrège par `path`. La métrique `stoa_http_request_duration_seconds_bucket` du gateway a bien le label `path` (`stoa-gateway/src/metrics.rs:32`), mais soit les scrapes ne le préservent pas, soit la valeur stockée est littéralement `"unknown"` (path par défaut quand le router Axum ne match pas). | `CallFlowDashboard.tsx:199-206`, `metrics.rs:28-36` |
| L3 | **HIGH** | "Throughput by Deployment Mode" → `No throughput data for 1h` alors que le KPI dit 39.3K. | Cohérent avec L1: les `query_range` filtrent par `job=` et ne matchent pas. Le banner bleu "Tempo service graph metrics not yet available" n'apparaît pas car `useServiceGraph = !error && scalarValue(totalRequests.data) !== null` → `true` (le total répond), donc on **n'entre pas dans le fallback** alors que les données détaillées sont vides. | `CallFlowDashboard.tsx:246-249, 482-490` |
| L4 | **HIGH** | "Live Traces 0/0" + message "ensure observability pipeline (Alloy, Tempo, OpenSearch) is active". | Endpoint `/v1/monitoring/transactions?limit=50&time_range=60` répond `200` mais retourne une liste vide. Aucun ingestion path actif côté trace. Le message est correct mais pousse l'utilisateur à débugger l'infra alors que le KPI Total Requests semble dire que le pipeline marche. **Contradiction visuelle.** | `CallFlowDashboard.tsx:103-120, 681-689` |
| L5 | **MED** | Heatmap est **synthétique** (pas réel). Code: `// For now, we use demo data since the range query returns aggregated series` (ligne 337) suivi d'une distribution heuristique business-hours via `hash(route, hour)`. | TODO non terminé: la heatmap dérive ses cellules d'un hash déterministe sur `topRoutes`, pas d'un range query Prometheus. Sur prod actuelle elle est triviale (1 seule route "unknown"), mais dès que les données arrivent elle restera **fake** sans correctif. | `CallFlowDashboard.tsx:336-361` |
| L6 | **MED** | KPI "Active Modes" = 1, libellé "Deployment modes". | Calculé via `count(count by (path) (stoa_http_requests_total))` — c'est un **comptage de paths**, pas de modes de déploiement. Avec `path="unknown"` unique → résultat = 1. Libellé trompeur. | `CallFlowDashboard.tsx:157-160, 584-590` |
| L7 | **MED** | Header `<h1>` du composant affiche **"Call Flow"** (`CallFlowDashboard.tsx:440`) alors que le breadcrumb et la sub-nav disent **"Live Calls"**. PR #2713 a renommé l'URL et la nav mais a oublié le header de la page. | Incohérence terminologique. | `CallFlowDashboard.tsx:440-444` |
| L8 | **LOW** | Sous-titre header: "Real-time request flow across deployment modes — Gateway, Link, Connect". Le snapshot console montre un sous-titre différent injecté ailleurs: "Recent calls, trace IDs, latency, and request flow across Gateway, Link, and Connect". Deux sous-titres coexistent ⇒ probable wrapper layout (Outlet/SubNav) avec second header. | Duplication header observée à l'écran (cf. `01-live-calls.png` ref `e351` + `e367` dans le snapshot Live Calls). | snapshot `e347-e445` |
| L9 | **LOW** | Bouton "Refresh" sur déploiement client mais auto-refresh par défaut activé à 15s ⇒ deux contrôles redondants (toggle Off/15s/30s/60s + bouton). | UX bruit. | `CallFlowDashboard.tsx:456-468` |
| L10 | **LOW** | Le sélecteur de service (`All Services`/Gateway/Link/Connect) ne reflète pas les jobs réellement scrapés. Aucune façon visuelle de savoir si "Connect" est inactif ou simplement filtré. | Manque d'état "no data for this service". | `CallFlowDashboard.tsx:446-455` |

### Recommandations Live Calls

1. **L1+L3** Ajouter un filtre `job` cohérent au KPI Total: soit `job=~"stoa-gateway\|stoa-link\|stoa-connect"`, soit décider explicitement que cette page ne couvre PAS cp-api. Sinon, faire apparaître une bannière "Données partielles: 39.3K ne correspondent à aucun mode reconnu".
2. **L2** Ajouter un `path != "unknown"` à `topRoutes` ou afficher un état dédié quand le seul path retourné est `unknown` (probablement un fallback de l'instrumentation Axum). Alternative: demander à l'équipe gateway de retirer `path` du label quand il n'est pas connu plutôt que renvoyer `"unknown"`.
3. **L5** Soit ré-écrire la heatmap sur un vrai range query (`sum by (path) (rate(stoa_http_requests_total[5m]))` × 24h step=1h), soit la cacher tant que le query n'est pas implémenté. Le mock est un piège pour les démos.
4. **L6** Renommer en "Tracked Routes" avec subtitle "Distinct path labels" — ou lier au vrai concept de mode via `count(count by (job) (stoa_http_requests_total{job=~"stoa-(gateway|link|connect)"}))`.
5. **L7** Renommer `<h1>Call Flow</h1>` → `<h1>Live Calls</h1>` (`CallFlowDashboard.tsx:440`).
6. **L8** Vérifier qu'aucun layout parent n'injecte un second `<h1>` (likely `App.tsx` Outlet / Layout wrapper a ajouté un title à partir de la breadcrumb).

---

## 2. `/audit-log`

**Component**: `control-plane-ui/src/pages/AuditLog.tsx`. Backend: `routers/audit.py` (3 sources fallback: PG → OpenSearch → demo).

### Findings

| # | Sévérité | Symptôme observé | Cause racine | Fichier |
|---|---|---|---|---|
| A1 | **HIGH** | Tenant `free-aech` retourne **42 events** total, dont 100% sont **`chat conversation create` ou `chat tool call`**. **Aucune** action `create`/`update`/`delete` API, deploy, login, access_denied, config_change. | Beaucoup de `kafka_service.emit_audit_event(...)` côté cp-api (apis.py, tenants.py, users.py, deployment_service.py, promotion_service.py — 20+ call sites). Soit le consumer Kafka qui écrit dans la table `audit_events` est down/non câblé en prod, soit ces événements vont ailleurs. **L'audit DORA/NIS2 mentionné dans le router (`audit.py:12`) est de facto absent en prod**. | `routers/audit.py:1-15`, `services/audit_service.py`, `services/kafka_service.py:206` |
| A2 | **HIGH** | Colonne "Actor" affiche un UUID brut (`2fefc656-8725-4761-95bb-1ae2e24db96e`) pour ~25 events, et un email pour les autres (`cpi-admin@gostoa.dev`). Pas de fallback sur le username/displayName Keycloak. | `AuditLog.tsx:431` fait `entry.user_email \|\| entry.user_id \|\| 'system'`. L'API ne joinit pas avec Keycloak pour résoudre l'UUID en email/displayName quand `user_email` est null. | `AuditLog.tsx:430-433` |
| A3 | **MED** | KPIs "Successful 19", "Failed 1", "Unique Actors 2" — sous-titre "On this page" → **comptés sur les 20 entrées de la page courante**, pas sur les 42 totales. "Total Events 42" est lui le vrai total. | `AuditLog.tsx:197-199`: `entries.filter(...)` parcourt seulement la page chargée. Les 3 KPIs sont donc trompeurs (ils suggèrent des agrégats globaux). | `AuditLog.tsx:197-199, 270-291` |
| A4 | **MED** | `apiService.get('/v1/audit/{tenant_id}', { params: { date_from, date_to } })` côté UI mais l'API attend `start_date` / `end_date` (cf. `audit.py:203-204`). | Naming mismatch: UI envoie `date_from`/`date_to`, l'API ignore silencieusement (FastAPI Query non-strict) → filtres par date **inopérants**. | `AuditLog.tsx:127-128, 360-371` vs `audit.py:203-204` |
| A5 | **MED** | Pas d'export JSON visible — bouton "Export" hard-coded sur CSV (`handleExport('csv')` ligne 218), alors que `/v1/audit/{tenant_id}/export/json` existe et est annoncé dans le router. | UX incomplet: split-button ou menu manquant. | `AuditLog.tsx:217-225` |
| A6 | **MED** | Quand `error` est set (ligne 240-247), la table reste affichée avec les anciennes données. Le user ne sait pas si les données sont stale. | `AuditLog.tsx:143-148` ne reset pas `entries` en cas d'erreur 4xx (seulement `setEntries([])` puis `setTotal(0)`). Mais la bannière d'erreur ne stoppe pas l'auto-refresh ⇒ "thrashing" silencieux. | `AuditLog.tsx:143-150, 162-166` |
| A7 | **LOW** | Le filtre "Action" propose `create/update/delete/deploy/login/access_denied`. Or les actions réelles en base sont `chat conversation create`, `chat tool call`. Le filtre **ne matchera rien** en prod actuelle. | Filtres front/back désaligné avec la réalité Kafka. | `AuditLog.tsx:336-343` |
| A8 | **LOW** | Pas de colonne "Tenant" alors qu'un cpi-admin peut voir des events cross-tenant via `/v1/audit/{tenant_id}` répété. Il existe `audit.py:GET /global/summary` (cpi-admin only) mais aucune UI ne l'expose. | Capacité backend non exploitée. | `audit.py` (cpi-admin endpoint), pas dans UI |
| A9 | **LOW** | Le `formatTimestamp` est en `fr-FR` (DD/MM/YYYY HH:mm:ss) hard-codé alors que la console a un sélecteur EN/FR. | i18n incohérent. | `AuditLog.tsx:90-100` |

### Recommandations Audit Log

1. **A1** P0: vérifier que le consumer Kafka `audit-events` → `audit_events` PG est UP en prod OVH. Aujourd'hui le router de prod tombe probablement en mode "PostgreSQL retourne 0 → OpenSearch retourne 0 → demo data" — sauf que les 42 entrées chat sont vraies, donc une partie écrit. À diagnostiquer en priorité, sinon DORA/NIS2 est en réalité non satisfait.
2. **A2** Joindre côté API ou côté UI Keycloak pour résoudre `user_id` (UUID) → email/displayName. Ou stocker `user_email` à l'émission.
3. **A3** Soit faire un endpoint `/v1/audit/{tenant_id}/stats` qui renvoie successCount/failCount/uniqueActors agrégés sur la fenêtre filtrée, soit retirer ces KPIs ambiguës. "On this page" est nul d'un point de vue métier.
4. **A4** Renommer côté UI `date_from`→`start_date`, `date_to`→`end_date` (`AuditLog.tsx:127-128`).
5. **A5** Split-button Export CSV / Export JSON.
6. **A7** Faire une `GET /v1/audit/{tenant_id}/actions` qui retourne la liste distincte des actions vues (top 50) → populer le filter dynamiquement.

---

## 3. `/observability/security`

**Component**: `control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.tsx`. Backend: `/v1/admin/gateways/metrics` + `/v1/admin/gateways/metrics/guardrails/events`.

### Findings

| # | Sévérité | Symptôme observé | Cause racine | Fichier |
|---|---|---|---|---|
| S1 | **HIGH** | **Le titre & sub-nav disent "Security & Guardrails"** mais le `<h1>` interne du composant dit **"Gateway Guardrails"** (`GuardrailsDashboard.tsx:191`). Idem que L7 ci-dessus: codex a renommé la route et la sub-nav mais pas l'intérieur du composant. | Refactor incomplet PR #2713. | `GuardrailsDashboard.tsx:189-196` |
| S2 | **HIGH** | "Guardrail Configuration" affiche **uniquement les noms d'env vars** (`GUARDRAILS_PII_ENABLED`, `POLICY_ENABLED`, etc.). **Aucune valeur réelle** ON/OFF. C'est une checklist sans état. | `ConfigRow` (l. 322-331) écrit le `envVar` en `<code>` sans appel API à un endpoint qui retourne l'état réel. Inutilisable pour un opérateur. | `GuardrailsDashboard.tsx:303-330` |
| S3 | **HIGH** | Tous les compteurs à 0 (`PII Detection 0`, `Injection Blocks 0`, `Prompt Guard 0`, `Content Filters 0`, `Rate Limit 0`) avec "Recent Events: 0 events". Aucun moyen de distinguer "**guardrails désactivés**" de "**guardrails activés mais aucun événement**" de "**source de données cassée**". | `getGatewayAggregatedMetrics()` répond 200 → `metrics?.guardrails?.pii_detections \|\| 0` masque silencieusement un null/undefined. Pas de "data source unhealthy" indicator. | `GuardrailsDashboard.tsx:100-110` |
| S4 | **MED** | Pas de **time range selector** (la page Live Calls en a un — `1h/6h/24h/7d`). Tous les compteurs sont implicitement "all time" ou la fenêtre par défaut côté API. | Inconsistance UX entre les 3 onglets observability. | `GuardrailsDashboard.tsx:184-205` (header) |
| S5 | **MED** | Le sous-titre dit "Audit, **policy decisions**, PII protection, prompt guard, and rate limiting events" — mais aucune section "policy decisions OPA" n'est visible. La carte `OPA Policy Engine` apparaît juste comme un env var. | Sous-titre vend plus que le composant ne livre. | `GuardrailsDashboard.tsx` (sous-titre invisible dans le code, suggère override layout) |
| S6 | **MED** | Click sur une carte `pii/injection/content/prompt` filtre le tableau d'événements → bonne idée. Mais la carte "Rate Limit" a `filter: 'all'` (`GuardrailsDashboard.tsx:181`) ⇒ click sans effet. Bug subtil. | Filter typage incomplet. | `GuardrailsDashboard.tsx:175-182` |
| S7 | **MED** | Click sur un event renvoie sur `/call-flow/trace/${trace_id}` (l. 276) — **route legacy, redirige** depuis PR #2715 vers `/observability/live-calls/trace/...`. Fonctionne mais surcoût d'un round-trip. | URL hard-codée non mise à jour. | `GuardrailsDashboard.tsx:276` |
| S8 | **LOW** | "Security Posture" (page séparée sous Governance) et "Security & Guardrails" (cette page sous Observability) coexistent — IA confuse: l'utilisateur ne sait pas où chercher quoi. Codex a déplacé Security & Guardrails sous Observability mais a laissé Security Posture sous Governance. | IA double, mêmes mots, périmètres différents non documentés. | nav: `App.tsx:381` + `App.tsx:357-359` |
| S9 | **LOW** | Sidebar a TOUJOURS `Gateway → Security` et `Gateway → Guardrails` qui pointent vers `/gateway-security` et `/gateway-guardrails` — qui redirigent vers `/observability/security`. Trois entrées de menu vers la même page finale. | Nettoyage de nav incomplet. | snapshot sidebar refs `e183`, `e188`, `e226` |

### Recommandations Security & Guardrails

1. **S1+S5** Renommer `<h1>Gateway Guardrails</h1>` → `<h1>Security & Guardrails</h1>`. Couper le sous-titre à la liste réellement supportée (retirer "policy decisions" si OPA n'est pas branché).
2. **S2** P0 fonctionnel: ajouter une vraie route `GET /v1/admin/gateways/guardrails/config` qui retourne `{pii_enabled: true, injection_enabled: false, ...}` et afficher un toggle vert/rouge. Sans valeurs, le panel est cosmétique.
3. **S3** Ajouter un health indicator (vert/orange/rouge) sur chaque carte basé sur la fraîcheur des metrics côté API (e.g. `metrics_age_seconds`). "0" doit être lisible: "0 (last sample 12s ago)" vs "0 (no data 47m)".
4. **S4** Ajouter `TimeRangeSelector` aligné sur Live Calls.
5. **S6** Carte Rate Limit: soit lui donner son propre filter `'rate-limit'`, soit la rendre non-cliquable.
6. **S7** Mettre à jour l'URL de navigation: `navigate(\`/observability/live-calls/trace/${event.trace_id}\`)`.
7. **S8+S9** Décision IA à prendre: **fusionner** Security Posture et Security & Guardrails en une seule page Security sous Observability, OU clarifier les périmètres (Posture = score statique/findings, Guardrails = events runtime). Supprimer les liens Gateway→Security/Guardrails de la sidebar (s'ils redirigent, autant les enlever).

---

## Constats transverses (codex post-mortem)

1. **Les composants n'ont pas été retitré** alors que les routes l'ont été. `<h1>` hard-codé dans CallFlowDashboard et GuardrailsDashboard contredit le breadcrumb/sub-nav dans 100% des pages auditées. → ajouter un test de regression simple: `expect(h1.textContent).toMatch(breadcrumb.last())`.
2. **Aucune nouvelle donnée câblée**. Le PR #2713 décrit explicitement en non-goals: pas de rewire OTel/Loki/Tempo/OpenSearch, pas de nouveau backend storage. C'est cohérent. Ce que l'utilisateur perçoit comme "pas à la hauteur" tient au fait que les *données sous-jacentes sont brisées* (path=unknown, audit Kafka sink HS, guardrails config sans valeurs) — et codex n'a pas attaqué ces racines.
3. **Mock résiduel**: la heatmap (L5) et les KPIs "On this page" de l'audit (A3) sont des dettes techniques que codex aurait pu nettoyer. → MEGA dédié "Observability data integrity" à instruire avec impact-check.
4. **Routes legacy → redirect**: cohérent et propre. Mais 3 entrées sidebar pointent vers `/gateway-security`/`/gateway-guardrails`/`/security-posture` ⇒ retirer les 2 premières (redirects), garder la troisième (page distincte).

---

## Priorités proposées

| Rank | Action | Effort | Impact |
|---|---|---|---|
| P0 | A1 — diagnostiquer pourquoi `audit_events` ne contient que les events `chat`. Conformité DORA/NIS2 en jeu. | 0.5j | High |
| P0 | L2 — corriger `path="unknown"` dans le scrape gateway (label cardinality). Sans ça, Top Routes & Heatmap inutilisables. | 1j | High |
| P1 | S2 — endpoint guardrails config réel (booléens). | 1j | Med |
| P1 | L1+L3 — aligner les filtres `job` du dashboard Live Calls pour cohérence KPI ↔ breakdowns. | 0.5j | Med |
| P2 | L7+S1 — cohérence titre/breadcrumb (3 lignes de code). | 0.1j | Low |
| P2 | A3+A4 — KPIs audit globaux + fix `date_from`/`date_to` mismatch. | 0.5j | Med |
| P2 | S8 — décision IA Security Posture vs Security & Guardrails. | 0.2j (décision) | Med |
| P3 | L5 — heatmap réelle ou cachée. | 1j | Low |

---

## Annexes

- Captures: `01-live-calls.png`, `02-audit-log.png`, `03-security.png`
- PR codex en cause: #2713 (`b65397083`), #2715 (`c4c6a55c8`)
- Métriques source: `stoa-gateway/src/metrics.rs:18-36`, `control-plane-api/src/middleware/metrics.py:35-46`
- Audit emission sites: 20+ dans `control-plane-api/src/routers/{users,apis,tenants}.py` + `services/{deployment,promotion}_service.py`
