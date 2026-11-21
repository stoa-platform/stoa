# BOOTSTRAP PROMPT — Session 1

Copie ce prompt dans Claude Code (terminal ou VS Code).

---

## INSTRUCTIONS

Tu es le dev principal de STOA Platform. Objectif: produit revenue-ready pour le **24 février 2026** (dans 20 jours).

Tu travailles en **sessions isolées** avec état persistant via fichiers markdown.

### ÉTAPE 1 : BACKUP + BRANCHE

```bash
git checkout main && git pull
git checkout -b backup/pre-claude-$(date +%Y%m%d-%H%M%S)
git push origin HEAD
git checkout -b feat/claude-sprint-feb24
```

### ÉTAPE 2 : CRÉE LES FICHIERS DE CONTEXTE

Crée ces 3 fichiers **à la racine du repo** :

---

**Fichier 1: CLAUDE.md**

```markdown
# STOA Platform — AI Dev Context

## Mission
Produit revenue-ready pour le **24 février 2026**.

## Architecture
- Control Plane: Python 3.11 + FastAPI + SQLAlchemy
- MCP Gateway: Python 3.11 + FastAPI + OPA
- Portal/Console: React + TypeScript + Vite
- CLI stoa: Python + Typer + Rich
- CLI stoactl: Go + Cobra (repo github.com/stoa-platform/stoactl)
- Auth: Keycloak (OIDC, Token Exchange)
- DB: PostgreSQL, OpenSearch
- Secrets: HashiCorp Vault
- Observability: Prometheus, Grafana, Loki

## Stack Rules
- Python partout côté backend — JAMAIS Node.js
- Async par défaut
- Pydantic v2 pour validation
- Type hints obligatoires
- pytest pour tests, coverage > 80%

## Repos
| Repo | Stack | URL |
|------|-------|-----|
| stoa | Python | github.com/stoa-platform/stoa |
| stoactl | Go | github.com/stoa-platform/stoactl |
| stoa-docs | Docusaurus | github.com/stoa-platform/stoa-docs |
| stoa-web | Astro | github.com/stoa-platform/stoa-web |
| stoa-quickstart | Docker Compose | github.com/stoa-platform/stoa-quickstart |

## API Endpoints (Control Plane)
Base: http://localhost:8000/v1

| Method | Path | Description |
|--------|------|-------------|
| GET | /apis | List APIs |
| POST | /apis | Create API |
| GET | /apis/{id} | Get API |
| GET | /tenants | List tenants |
| POST | /tenants | Create tenant |
| GET | /subscriptions | List subscriptions |
| POST | /subscriptions | Create subscription |
| GET | /mcp/tools | List MCP tools |
| POST | /mcp/call | Call MCP tool |
| GET | /health | Health check |

## Commit Convention
- feat: nouvelle feature + CAB-XXXX
- fix: bug fix + CAB-XXXX  
- docs: documentation
- test: tests
- refactor: refactoring

## Session Rules
1. Lis CLAUDE.md + memory.md + plan.md au début
2. Focus sur UN seul MEGA-ticket par session
3. Update memory.md à la fin avec ta progression
4. Commit souvent, messages clairs
5. /clear entre sessions pour contexte fresh
```

---

**Fichier 2: memory.md**

```markdown
# STOA Memory

> Dernière MAJ: 2026-02-04

## ✅ DONE
(vide)

## 🔴 IN PROGRESS
CAB-1052: Fix 4 bugs critiques
- [ ] CAB-1044: API Search → HTTP 500
- [ ] CAB-1040: Gateway Routes → HTTP 404  
- [ ] CAB-1042: Vault sealed → credentials fail
- [ ] CAB-1041: E2E BDD auth → tests fail

## 📋 NEXT
- CAB-1060: Docs 20 pages (docs.gostoa.dev)
- CAB-1061: Demo script 5 min
- CAB-1062: Final polish + dry-runs
- CAB-1066: Landing gostoa.dev + Stripe

## 🚫 BLOCKED
(rien)

## 📝 NOTES
- Demo: mardi 24 février 2026
- Présentation "ESB is Dead" même jour
- 2 design partners à closer
- Stack = Python (pas Node)
```

---

**Fichier 3: plan.md**

```markdown
# Sprint Plan — 24 Février 2026

## 🎯 KPIs
| Métrique | Cible |
|----------|-------|
| Demo sans bug | ✅ |
| Docs pages | 20+ |
| Landing live | gostoa.dev |
| Stripe checkout | Fonctionnel |
| Design partners | 2 LOI |

## Semaine 1 (4-7 fév) — STABILISATION
- [ ] CAB-1052: Fix 4 bugs critiques
- [ ] CLI stoa complète (login, get apis, apply)
- [ ] E2E tests 100% pass
- [ ] Loki: 0 errors sur 5 min

## Semaine 2 (10-14 fév) — CONTENU  
- [ ] CAB-1060: 20 pages docs Docusaurus
- [ ] Getting Started < 5 min read
- [ ] MCP Gateway deep-dive
- [ ] API Reference complète
- [ ] FAQ + Troubleshooting

## Semaine 3 (17-21 fév) — GO TO MARKET
- [ ] CAB-1066: Landing + Pricing + Stripe
- [ ] CAB-1061: Demo script 5 min chronométré
- [ ] CAB-1062: 2 dry-runs sans bug
- [ ] Video backup (si réseau fail)
- [ ] One-pager PDF final

## Règles Anti-Dérive
1. 1 MEGA par session — pas de scope creep
2. Si bloqué > 30 min → note dans memory.md, passe au suivant
3. Commit toutes les 30 min minimum
4. Push avant /clear
```

---

### ÉTAPE 3 : COMMIT LA STRUCTURE

```bash
git add CLAUDE.md memory.md plan.md
git commit -m "feat: bootstrap AI dev context for sprint feb24"
git push origin feat/claude-sprint-feb24
```

### ÉTAPE 4 : COMMENCE LE TRAVAIL

**Focus: CAB-1052 — Fix les 4 bugs critiques**

1. Explore le code, trouve les fichiers concernés
2. Reproduis chaque bug localement (docker compose up ou pytest)
3. Fix avec test qui prouve le fix
4. Commit: `fix: CAB-XXXX description`
5. Répète pour les 4 bugs
6. Update memory.md avec ce qui est DONE

**DoD Session 1:**
- Zero HTTP 500 sur /apis/search
- Zero HTTP 404 sur /mcp/routes  
- Vault unsealed automatiquement
- E2E auth tests passent
- memory.md mis à jour

Go.
