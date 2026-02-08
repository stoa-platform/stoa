---
description: Multi-agent workflow patterns and subagent delegation guide for STOA AI Factory
---

# AI Factory — Multi-Agent Workflow

## Subagents disponibles

| Agent | Modele | Outils | Quand utiliser |
|-------|--------|--------|----------------|
| `security-reviewer` | sonnet | Read, Grep, Glob, Bash (RO) | Apres chaque modification de code, PR review, fichiers auth/crypto/secrets/RBAC |
| `test-writer` | sonnet | Read, Grep, Glob, Write, Edit, Bash | Generation de tests, augmentation de couverture, CAB-1116 |
| `k8s-ops` | sonnet | Read, Grep, Glob, Bash (RO) | Debug deployment, validation manifests k8s, Helm, nginx, rollout |
| `docs-writer` | sonnet | Read, Grep, Glob, Write, Edit | ADRs, guides, runbooks, memory updates |

## Quand deleguer vs travailler inline

### Deleguer a un subagent quand:
- La tache produit beaucoup d'output (logs k8s, rapports securite, analyse de couverture)
- On veut isoler le contexte (ne pas polluer la conversation principale)
- La tache est auto-contenue (ecrire des tests, analyser une PR, diagnostiquer un deploy)
- On a besoin d'outils restreints (securite et k8s = read-only par design)

### Travailler inline quand:
- La tache necessite des allers-retours frequents avec l'utilisateur
- Plusieurs phases partagent du contexte significatif
- Le changement est rapide et cible (< 5 fichiers)
- La latence compte (les subagents demarrent avec un contexte frais)

## Patterns de delegation

### Pattern 1: Review sequentielle
```
1. security-reviewer analyse les changements
2. Resultats → test-writer genere les tests manquants
3. k8s-ops valide si des fichiers infra sont modifies
```
Usage: feature development standard, PR review approfondie.

### Pattern 2: Review parallele (/parallel-review)
```
Lancer security-reviewer + test-writer + k8s-ops en parallele
Synthetiser les resultats dans le thread principal
Produire un verdict global Go / Fix / Refaire
```
Usage: PR review rapide, validation pre-merge.

### Pattern 3: Feature development
```
1. [Inline] Explorer + planifier (Plan mode)
2. [Inline] Implementer le code
3. [test-writer] Generer les tests
4. [security-reviewer] Review securite
5. [docs-writer] Documenter si ADR ou guide necessaire
6. [Inline] Commit + PR
```
Usage: implementation complete d'un ticket CAB-XXXX.

### Pattern 4: Agent Teams (experimental)
```bash
# Prerequis: tmux installe
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```
Usage: refactoring multi-composants, migration majeure, debugging avec hypotheses concurrentes.

### Pattern 5: CI-first development
```
1. [Inline] Implementer la feature
2. [Inline] Executer le pre-commit checklist (voir ci-quality-gates.md)
3. [test-writer] Generer les tests + verifier coverage seuil
4. [security-reviewer] Review securite + secrets
5. [Inline] Commit + push → CI green first try
```
Usage: tout changement de code. Objectif: zero surprise en CI.

## Contraintes

- **Maximum 3-4 subagents actifs simultanement** (au-dela, le cout explose et le temps de review aussi)
- **security-reviewer et k8s-ops** sont read-only — ils ne modifient JAMAIS le code
- **test-writer et docs-writer** modifient le code — verifier leurs outputs
- Chaque subagent qui review donne un **verdict binaire**: Go / Fix / Refaire
- Un seul P0 (critique) de n'importe quel subagent → verdict global **Fix**
- **Toujours consulter `ci-quality-gates.md`** AVANT de committer du code
- **Toujours consulter `secrets-management.md`** quand un env var ou credential est ajoute/modifie
