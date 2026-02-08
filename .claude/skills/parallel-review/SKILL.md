---
name: parallel-review
description: Orchestrer une review parallele multi-angle d'une PR ou d'un composant, en deleguant a des subagents specialises (securite, tests, k8s).
disable-model-invocation: true
argument-hint: "[PR-number ou component-path]"
---

# Parallel Review — Review multi-angle orchestree

Executer une review parallele complete sur: $ARGUMENTS

## Workflow

### Step 1: Charger le contexte

Si c'est un numero de PR:
```bash
gh pr view $0
gh pr diff $0 --name-only
gh pr checks $0
```

Si c'est un chemin de composant:
```bash
git diff main --name-only -- $0
```

### Step 2: Determiner les reviewers necessaires

| Fichiers modifies | Subagent a lancer |
|-------------------|-------------------|
| `*.py`, `*.tsx`, `*.ts`, `*.rs` (code applicatif) | **security-reviewer** (toujours) |
| `*.test.*`, `test_*`, `*.spec.*` | **test-writer** (evaluer couverture) |
| Tout code sans tests correspondants | **test-writer** (identifier les manques) |
| `Dockerfile`, `k8s/`, `*.yaml` (k8s), `nginx*`, `charts/` | **k8s-ops** |
| `docs/`, `*.md`, `CLAUDE.md`, `memory.md` | **docs-writer** |
| `docs/*.md`, `blog/**`, `*.astro` (contenu public) | **content-reviewer** |

**Minimum**: security-reviewer est TOUJOURS lance.
**Maximum**: 4 subagents en parallele (budget tokens).

### Step 3: Deleguer aux subagents

Lancer les subagents en parallele via le Task tool:

1. **security-reviewer**: "Analyse de securite des changements de la PR $0"
2. **test-writer**: "Evaluer la couverture de tests pour les fichiers modifies dans la PR $0. Identifier les tests manquants."
3. **k8s-ops** (si applicable): "Valider les changements infra/k8s de la PR $0 contre la checklist k8s-deploy.md"
4. **content-reviewer** (si contenu public): "Audit conformite du contenu public de la PR $0 contre content-compliance.md"

### Step 4: Synthetiser les resultats

Combiner les rapports des subagents en un rapport unifie:

```markdown
## Review Parallele: $ARGUMENTS

### Date: [date]
### Branche: [branch]
### Fichiers modifies: [count]

---

### Securite (security-reviewer)
**Verdict**: Go / Fix / Refaire
[Resume des findings]

### Tests (test-writer)
**Verdict**: Go / Fix / Refaire
[Resume: couverture actuelle, tests manquants]

### Deployment (k8s-ops)
**Verdict**: Go / Fix / Refaire / N/A
[Resume ou "Pas de changements infra detectes"]

### Conformite Contenu (content-reviewer)
**Verdict**: Go / Fix / Refaire / N/A
[Resume: concurrents, clients, prix, reglementations, disclaimers — ou "Pas de contenu public modifie"]

---

### Verdict global: **Go** / **Fix** / **Refaire**

### Actions requises
1. [Action specifique avec fichier et ligne]
2. ...

### Actions suggerees (non-bloquantes)
1. ...
```

### Step 5: Poster (si PR GitHub)

Si l'argument est un numero de PR:
```bash
gh pr comment $0 --body "[rapport]"
```

## Regles de verdict

- **Go**: Tous les subagents donnent Go
- **Fix**: Au moins un subagent donne Fix ET aucun P0 critique non-resolvable
- **Refaire**: Au moins un subagent donne Refaire OU un P0 critique sur l'approche
- Verdict binaire — pas de "peut-etre" ou "a discuter"
- Minimum 2 subagents sur 3 doivent donner Go pour un verdict global Go
