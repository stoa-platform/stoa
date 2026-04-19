---
id: plan-2026-04-19-dev-tools-gateway
triggers: [a, b]
validation_status: rejected
challenge_ref: docs/decisions/2026-04-19-dev-tools-gateway.md
---

# Plan — 3 tools dev via gateway STOA locale

## Objectif

Exposer un workflow dev minimal (`dev-plan`, `dev-review`, `dev-status`) via la gateway STOA locale, consommable par Claude Code et Codex, sans lancer un nouvel orchestrateur.

## Scope

- **In:**
  - 3 MCP tools: `dev-plan(ticket|brief) -> plan + artefact`, `dev-review(diff|pr_ref) -> verdict + findings + score`, `dev-status(ticket|run_id) -> état + next step`
  - Transport: gateway STOA locale (k3d + Tilt)
  - Clients: Claude Code + Codex
- **Out:** `execute`, `ship`, auto-merge, auto-Done Linear, remote MCP dédié

## Phases

1. Contrat (3 tools I/O + format artefact unique + métriques succès)
2. Core local (wrapper existant contexte+review, tests unit+smoke, core marche sans agent)
3. Exposition via gateway STOA locale (auth/policy min, découverte MCP, `stoactl mcp` comme debug)
4. Consommation Claude/Codex (3 parcours: plan, review, status)
5. Canary 3–5 tickets réels, mesures: temps→plan, retouches manuelles, temps→1er diff, tool mismatch
6. Décision: si adoption → stabiliser + `stoactl dev ...`; sinon → abandonner `execute/ship`

## Go / No-Go criteria

- **Go** si 3 tools utilisés par Claude+Codex sur tickets réels avec moins de routing humain
- **No-Go** si valeur dépend d'un orchestrateur multi-stage

## Assumptions

- Le problème est un problème de transport/outillage MCP (→ stress-testé par le challenger, **invalidé**)
- Les artefacts plan/review/status ont un format commun viable
- L'auth locale "minimale" est un effort mineur (→ **invalidé**: CAB-2121 non commité, dette réelle)
- La gateway locale est stable en usage quotidien (→ **invalidé**: k3d/Tilt/KC stack fragile)
