# STOA Rewrite — Guardrails

> **Statut**: v1.0 — 2026-04-24. Ces garde-fous s'appliquent à TOUTE PR tant que `demo-smoke-test.sh` n'est pas `REAL_PASS` en CI.
> **Objectif unique**: protéger la démo minimale pendant que le rewrite (GW-*, GO-*, UI-*, CP-*) continue.

## 1. Principe directeur

**Chaque PR doit rapprocher ou préserver le verdict `REAL_PASS` du smoke démo.** Aucune autre mesure de qualité (coverage, clippy, tests ajoutés) ne prime si la démo régresse.

Décision tree à appliquer pour chaque PR :

```
demo-smoke AVANT = REAL_PASS ?
 ├─ OUI → demo-smoke APRÈS doit rester REAL_PASS. Sinon NO-GO.
 └─ NON → demo-smoke APRÈS doit rester au même verdict OU améliorer vers REAL_PASS.
           Régression (REAL_PASS→FAIL/MOCK_PASS/CONTRACT_DRY_RUN ou étapes réelles qui deviennent mockées) = NO-GO.
```

## 2. Freeze list (composants / fichiers / contrats figés)

Les éléments suivants sont **figés** : toute modification demande Council 8/10 + ADR :

### 2.1 Contrats code (tests de régression à écrire si absents)
- Schéma URL des endpoints listés dans `architecture-rules.md` §2.1
- Format métriques Prometheus `proxy_requests_total` / `mcp_tool_calls_total`
- Header `X-Api-Key` accepté par gateway `/apis/{api_name}/{*path}`
- Header de réponse `X-Stoa-Request-Id` injecté par gateway
- Contrat UAC démo `specs/uac/demo-httpbin.uac.json` et chemin dérivé `/apis/demo-httpbin/get`
- Datasources Grafana `prometheus`, `loki`, `opensearch-traces`, `tempo` si la stack observabilité est touchée
- Compatibilité DB consommée par le smoke (§2.6 de `architecture-rules.md`)

### 2.2 Scripts critiques
- `scripts/demo-smoke-test.sh` (v1 = ce sprint)
- `Makefile` targets : `run-api`, `run-gateway`, `seed-dev`, `lint-*`, `test-*`
- `deploy/docker-compose/docker-compose.yml` (services : postgres, keycloak, cp-api, gateway, mock-backend)

### 2.3 Dépendances
- Gateway : pas de nouvelle crate majeure (tokio, axum, serde, figment, reqwest) en version X → Y pendant le rewrite hors Council
- cp-api : pas de changement FastAPI / SQLAlchemy / Alembic major
- stoa-go : pas de migration keyring / cobra major

## 3. Règles actives sur les rewrites en cours

### 3.1 GW-* (stoa-gateway Rust)
- GW-2 (split `config.rs`) : OK car plan respecte §1 amendement 1 (façade conservée, contrat TOML/env intact). **Autoriser** tant que `cargo test` vert + `insta` snapshot `Config::default()` inchangé.
- Tout GW-3+ doit commencer par : "ce changement affecte-t-il `/apis/{api_name}/{*path}`, `/health`, `/metrics`, `X-Api-Key` handling ?" → si oui, Council obligatoire.
- Feature flags Cargo : démo tourne en build **default**. Pas de dépendance runtime à `kafka` ou `k8s` dans le chemin démo.

### 3.2 GO-* (stoa-go / stoactl + stoa-connect)
- GO-2 (hardening `internal/connect/`) : OK tant que le polling `GET /v1/internal/gateways/routes` reste fonctionnel (fallback démo si SSE down).
- stoactl commands minimales nécessaires à la démo : `auth login`, `apply`, `get`, `subscription list|create`. Les autres peuvent bouger librement.

### 3.3 CP-* (control-plane-api)
- CP-2 (batch de fixes) : OK si aucun rename de colonne DB ni breaking de routes §2.1.
- Tout nouveau middleware obligatoire sur routes démo → test smoke vérifie qu'il passe avec les credentials démo.

### 3.4 UI-*
- Hors chemin démo (démo pilotée en CLI). UI peut bouger librement.
- **Exception** : si la démo pivote vers un chemin UI (non prévu v1), `demo-scope.md` §2 doit être mis à jour EN MÊME TEMPS.

## 4. PR template : section "démo impact" obligatoire

Chaque PR touchant cp-api, stoa-gateway, stoa-go, charts, deploy/ doit inclure dans sa description :

```markdown
## Demo impact

- [ ] Vérifié : aucune modification de `specs/architecture-rules.md` §2 (contrats figés)
- [ ] `DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json ./scripts/demo-smoke-test.sh` exécuté avant cette PR : REAL_PASS / CONTRACT_DRY_RUN / MOCK_PASS / FAIL (préciser)
- [ ] `DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json ./scripts/demo-smoke-test.sh` exécuté après cette PR : REAL_PASS / CONTRACT_DRY_RUN / MOCK_PASS / FAIL (préciser)
- [ ] Si non-REAL_PASS ou régression : quelle étape AT-N échoue ou est mockée et pourquoi est-ce acceptable ?
```

PR sans cette section = NO-GO automatique si touche un composant listé §2.

## 5. Interdits pendant la période rewrite (défaut NO-GO)

1. **Rewrite cosmétique** : rename global, reflow imports, nettoyage sans impact démo → merge plus tard, pas maintenant.
2. **Nouvelles features** (MCP expansion, federation, LLM router enrichi, OPA policies nouvelles) → queue dans le backlog, pas dans le sprint démo.
3. **Refactor d'architecture** non cité dans un REWRITE-PLAN.md validé → stop.
4. **"Tant que j'y suis..."** → stop. 1 PR = 1 intention.
5. **Suppression d'un endpoint ou colonne** listé §2 → Council + ADR + période de dépréciation.
6. **Changement de port démo** (8000, 8081, 9090) → casse smoke, stop.

## 6. Exceptions tolérées (pas de Council)

- Bug fix P0 prod (documenté en commit message)
- Typo / comment / docstring
- Dependabot mineur (patch-level)
- Test ajouté sans toucher code prod
- ADR nouvelle (stoa-docs)

Ces PR peuvent sauter la section §4 mais doivent mentionner "demo-impact: none" dans le titre ou la description.

## 7. Escalade et décision humaine

Tout désaccord sur "cette PR est-elle acceptable démo-wise ?" remonte à humain (Christophe). Pas d'interprétation agent.

Signes qui déclenchent escalade automatique :
- PR modifie `specs/*.md`
- PR modifie une route §2 ou un nom de métrique §2.3
- PR modifie `scripts/demo-smoke-test.sh`
- PR touche `Makefile` target `run-*` ou `test-*`

## 8. Journal des breaches (à alimenter)

| Date | PR | Type breach | Décision | Follow-up |
|------|-----|-------------|----------|-----------|
| 2026-04-24 | — | — | Création initiale | — |

Chaque entrée sert de jurisprudence pour calibrer les décisions futures.

## 9. Sortie du régime guardrails

Conditions pour relâcher ces règles :
1. `./scripts/demo-smoke-test.sh` `REAL_PASS` en CI ≥ 5 jours consécutifs
2. Une démo réelle a été exécutée avec succès devant un témoin humain
3. `specs/demo-readiness-report.md` conclut GO en verdict final sans blockers

Avant ces 3 conditions = garde-fous actifs.
