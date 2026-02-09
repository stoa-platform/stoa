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
| `content-reviewer` | sonnet | Read, Grep, Glob, Bash (RO) | Audit contenu public: concurrents, prix, clients, reglementations |

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

### Pattern 3: Feature development (Ship/Show/Ask)
```
1. [Inline] Explorer + planifier (Plan mode)
2. [Inline] Branch: git checkout -b feat/CAB-XXXX-description
3. [Inline] Implementer le code + micro-commits (<150 LOC chacun)
4. [test-writer] Generer les tests
5. [security-reviewer] Review securite
6. [docs-writer] Documenter si ADR ou guide necessaire
7. [Inline] Local quality gate (ci-quality-gates.md)
8. [Inline] Push + PR (gh pr create)
9. [Inline] CI green (gh pr checks --watch)
10. [Inline] Ship/Show → merge auto | Ask → attendre "merge"
11. [Inline] Verify CD: CI main ✅ → ArgoCD sync ✅ → Pod healthy ✅
12. [k8s-ops] Si ArgoCD OutOfSync ou pod CrashLoop → diagnostiquer
13. [Inline] Cleanup branch + update memory.md
```
Usage: implementation complete d'un ticket CAB-XXXX. Voir `git-workflow.md` pour Ship/Show/Ask + CD verification map.

### Pattern 4: Agent Teams (experimental)
```bash
# Prerequis: tmux installe
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```
Usage: refactoring multi-composants, migration majeure, debugging avec hypotheses concurrentes.

### Pattern 5: CI-first development (always-green main)
```
1. [Inline] Branch + implementer la feature + micro-commits
2. [Inline] Executer le pre-commit checklist (voir ci-quality-gates.md)
3. [test-writer] Generer les tests + verifier coverage seuil
4. [security-reviewer] Review securite + secrets
5. [Inline] Push + PR + CI green + merge (voir git-workflow.md)
6. [Inline] Verify CD: CI main + ArgoCD + Pod (voir git-workflow.md step 7)
7. [k8s-ops] Si probleme CD → diagnostiquer et proposer fix
```
Usage: tout changement de code. Objectif: zero surprise en CI, always-green main.

### Pattern 6: Content compliance review
```
1. [docs-writer] Rediger le contenu
2. [content-reviewer] Scanner conformite (concurrents, prix, clients, reglementation)
3. [security-reviewer] Si contenu touche securite/RBAC
4. [Inline] Corrections + commit + PR
```
Usage: tout contenu public avec mentions concurrents, reglementations ou clients.

## Contraintes

- **Maximum 3-4 subagents actifs simultanement** (au-dela, le cout explose et le temps de review aussi)
- **security-reviewer, k8s-ops et content-reviewer** sont read-only — ils ne modifient JAMAIS le code
- **test-writer et docs-writer** modifient le code — verifier leurs outputs
- Chaque subagent qui review donne un **verdict binaire**: Go / Fix / Refaire
- Un seul P0 (critique) de n'importe quel subagent → verdict global **Fix**
- **Toujours consulter `ci-quality-gates.md`** AVANT de committer du code
- **Toujours consulter `secrets-management.md`** quand un env var ou credential est ajoute/modifie
- **Toujours consulter `content-compliance.md`** quand du contenu public mentionne concurrents, prix, clients ou reglementations
