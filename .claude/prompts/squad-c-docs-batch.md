Batch 4 tickets docs + scripts — CAB-1030 + CAB-1068 + CAB-550 + CAB-802.

Branch: `docs/cab-1030-admin-guide`

## Etat actuel (ce qui EXISTE deja)

### docs/
```
docs/
├── demo/
│   ├── DEMO-SCRIPT.md        (script demo 5 min, 6.5 KB)
│   ├── DEMO-CHECKLIST.md     (checklist pre-demo, 4.6 KB)
│   └── DRY-RUN-1.md          (rapport dry run #1, 12.4 KB)
├── templates/
│   └── MEGA-TICKET.md        (template mega-ticket existant)
├── runbooks/                  (6 runbooks ops)
├── guides/                    (guides utilisateur)
├── architecture/              (docs archi)
├── testing/                   (docs testing)
└── archive/phases/CAB-1068/plan.md  (plan AI Factory archive)
```

### scripts/
```
scripts/
├── ai-ops/
│   ├── ai-phase-runner.json   (config n8n)
│   ├── daily-digest.sh        (script digest)
│   ├── run-phase.sh           (runner de phase)
│   └── slack-notify.sh        (notification Slack)
├── demo/                      (12 scripts demo: seed, setup, reset, etc.)
├── backup/                    (scripts backup)
├── migration/                 (scripts migration)
└── tests/                     (scripts test)
```

### Ce qui N'EXISTE PAS
- `docs/admin/` — a creer
- `.stoa-ai/` — n'existe pas (abandonne dans CAB-1068 original)

## Ticket 1 — CAB-1030 Admin Guide (13 pts)

Creer `docs/admin/` avec 10 pages operationnelles.

IMPORTANT: ce sont des docs ops INTERNES (pas dans stoa-docs Docusaurus).
Les docs user-facing iront dans stoa-docs dans un PR separe.

### Fichiers a creer:

1. **docs/admin/README.md** — Overview
   - Architecture STOA (Control Plane + Data Plane)
   - Composants: API (FastAPI), Console (React), Portal (React), Gateway (Rust), Auth (Keycloak)
   - Prerequis: EKS 1.28+, Helm 3, PostgreSQL 15, Keycloak 24
   - Quick reference des URLs et ports

2. **docs/admin/installation.md** — Installation
   - Helm install step-by-step
   - Namespace `stoa-system`
   - CRDs: `kubectl apply -f charts/stoa-platform/crds/`
   - Post-install checks: health endpoints, pod status

3. **docs/admin/configuration.md** — Configuration
   - `BASE_DOMAIN` = single source of truth
   - Env vars par composant (reference deploy/config/)
   - Secrets: Vault paths (secret/apim/{env}/*)
   - ESO: ExternalSecret → K8s Secret sync

4. **docs/admin/rbac.md** — RBAC
   - 4 roles: cpi-admin, tenant-admin, devops, viewer
   - Scopes: stoa:admin, stoa:write, stoa:read
   - Keycloak realm config: realm roles, client scopes
   - Mapping role → permissions (table)

5. **docs/admin/secrets-rotation.md** — Rotation des secrets
   - Procedure: update Vault → ESO sync → pod restart
   - Force sync: `kubectl annotate externalsecret <name> force-sync=$(date +%s)`
   - Verification: `kubectl get externalsecret -n stoa-system`
   - Liste des secrets a rotater (DB, Keycloak, Gateway API key)

6. **docs/admin/monitoring.md** — Monitoring
   - Stack: Prometheus + Grafana + OpenSearch
   - Metriques cles par composant
   - Alertes recommandees (latency, error rate, pod restarts)
   - OpenSearch: pipeline RGPD, retention, index patterns

7. **docs/admin/backup-restore.md** — Backup/Restore
   - PostgreSQL: pg_dump/pg_restore
   - Keycloak: realm export/import
   - MinIO: bucket sync
   - Procedure disaster recovery

8. **docs/admin/troubleshooting.md** — Troubleshooting
   - Common issues: CrashLoopBackOff, ImagePullBackOff, OOM
   - Kyverno blocks: missing securityContext
   - Nginx envsubst issues (reference k8s-deploy.md rule #8)
   - Gateway: CB tripped, token validation failed
   - Logs: `kubectl logs -f deploy/<name> -n stoa-system`

9. **docs/admin/upgrade.md** — Upgrade
   - Procedure: Helm upgrade + Alembic migrate + verify
   - Pre-upgrade checklist (backup DB, check Kyverno policies)
   - Rollback: `helm rollback stoa-platform <revision>`
   - Post-upgrade: verify pods, run smoke tests

10. **docs/admin/openshift-delta.md** — OpenShift specifics
    - SCC (Security Context Constraints) vs PSP
    - Routes vs Ingress
    - Internal registry vs ECR
    - Non-root enforcement (deja compatible)
    - `oc` equivalents des commandes `kubectl`

### Compliance
- ZERO nom de client (pas de "Acme Corp", "BNP", etc.)
- ZERO prix de concurrent
- ZERO claim "compliant" ou "certified"
- Utiliser des exemples generiques: "tenant-acme", "api-weather"

---

## Ticket 2 — CAB-1068 AI Factory (3 pts)

Les scripts existent deja dans `scripts/ai-ops/`. Verifier et completer.

### Taches:
1. Lire `scripts/ai-ops/run-phase.sh` — verifier qu'il est fonctionnel, ajouter `set -euo pipefail`
2. Lire `scripts/ai-ops/slack-notify.sh` — verifier, ajouter error handling
3. Lire `scripts/ai-ops/daily-digest.sh` — verifier
4. Verifier `docs/templates/MEGA-TICKET.md` — existe, lire et confirmer complet
5. Creer `docs/templates/PHASE-PLAN.md` s'il n'existe pas:
   - Template: Phase #, Objectif, Taches (checklist), Criteres de validation, Dependances
6. `chmod +x scripts/ai-ops/*.sh` (s'assurer executable)

---

## Ticket 3 — CAB-550 Error Snapshot Demo (3 pts)

### Taches:
1. Lire `docs/demo/DEMO-SCRIPT.md` pour comprendre le flow existant
2. Creer `docs/demo/error-snapshot-demo.md`:
   - Scenario 2 min: "Error Correlation in Real-Time"
   - Setup: 3 services (API → Gateway → Backend)
   - Trigger: API call qui genere erreur cascade
   - Show: OpenSearch dashboard avec correlation trace_id
   - Talking points pour le presentateur
   - Timing par etape

3. Creer `scripts/demo/seed-error-snapshot.py`:
   - Python 3.11, pas de deps externes (requests seulement si dispo, sinon urllib)
   - Genere des appels API qui produisent des erreurs controlees:
     - 400 Bad Request (invalid payload)
     - 500 Internal Server Error (simulated backend failure)
     - 504 Gateway Timeout (slow upstream)
   - Chaque erreur avec un `trace_id` unique pour correlation
   - Mode: `--dry-run` (print sans executer) ou `--execute` (envoie les requetes)
   - Target configurable: `--api-url http://localhost:8000`

---

## Ticket 4 — CAB-802 Demo Dry Run Script (3 pts)

### Taches:
1. Lire `docs/demo/DRY-RUN-1.md` pour comprendre le format
2. Creer `scripts/demo/demo-dry-run.sh`:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   ```
   - Pre-flight checks: curl health endpoints de chaque service
   - Test sequentiel de chaque segment demo:
     1. Auth (Keycloak token fetch)
     2. API (list APIs, create subscription)
     3. Portal (health check)
     4. Gateway (MCP tool call)
     5. Console (health check)
   - Timing par segment: `time curl ...`
   - Output: markdown PASS/FAIL avec timing
   - Exit code: 0 si all pass, 1 si any fail

3. Creer `docs/demo/DEMO-PLAN-B.md`:
   - Tableau: composant → symptome → fallback
   - Ex: "Keycloak down" → "Utiliser token pre-genere dans .env"
   - Ex: "OpenSearch down" → "Skip error snapshot segment, montrer screenshots"
   - Ex: "Gateway timeout" → "Switch sur mock backend"
   - Contacts urgence (pas de vrais noms — roles generiques)

---

## Regles globales

- Lis les fichiers existants AVANT de creer pour eviter duplication
- Markdown bien formate, headers hierarchiques
- Scripts: shebang `#!/usr/bin/env bash`, `set -euo pipefail`
- Python: type hints, docstrings, `if __name__ == "__main__"`
- ZERO nom de client dans TOUT le contenu (compliance P0)
- 4 commits separes par ticket:
  1. `docs(admin): add operational admin guide — 10 pages (CAB-1030)`
  2. `chore(ai-factory): verify and complete automation scripts (CAB-1068)`
  3. `docs(demo): error snapshot demo scenario + seed script (CAB-550)`
  4. `docs(demo): dry run automation + plan B fallback (CAB-802)`
