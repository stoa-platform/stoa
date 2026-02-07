---
name: ci-debug
description: Debug GitHub Actions CI pipeline failures. Analyse les logs de workflow, identifie la cause racine et propose un fix.
disable-model-invocation: true
context: fork
agent: general-purpose
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[PR-number ou workflow-run-url]"
---

# CI Debug — Analyse des echecs CI

## Contexte dynamique
- Checks PR en cours: !`gh pr checks 2>/dev/null | head -20`
- Workflows recents: !`gh run list --limit 5 --json name,status,conclusion,headBranch --template '{{range .}}{{.name}} | {{.status}} | {{.conclusion}} | {{.headBranch}}{{"\n"}}{{end}}' 2>/dev/null`

## Instructions

Analyser l'echec CI pour: $ARGUMENTS

### Step 1: Identifier le workflow en echec

Si c'est un numero de PR:
```bash
gh pr checks $0
gh run list --branch $(gh pr view $0 --json headRefName -q .headRefName) --limit 3
```

Si c'est une URL de workflow run:
```bash
gh run view $0 --log-failed
```

### Step 2: Extraire les logs d'erreur

```bash
gh run view <run-id> --log-failed 2>&1 | head -100
```

Chercher les patterns:
- `error`, `Error`, `ERROR`
- `FAIL`, `FAILED`
- `exit code 1`, `exit code 2`
- `denied`, `forbidden`, `unauthorized`

### Step 3: Diagnostiquer

Causes frequentes dans STOA CI:

| Pipeline | Erreur frequente | Cause | Fix |
|----------|-----------------|-------|-----|
| Python CI | `I001` import order | isort non respecte | `ruff check --fix` |
| Python CI | `mypy` type error | Type hints manquants | Ajouter les annotations |
| Node CI | `vitest` fail | Mock MSW manquant | Ajouter handler MSW |
| Node CI | `eslint` warnings | Max warnings depassé (0 pour UI, 20 pour portal) | Fixer les warnings |
| Docker | `buildx` fail | Cache layer miss ou multi-arch | Verifier `--platform linux/amd64,linux/arm64` |
| Helm | `helm lint` fail | Values manquantes, indentation | Verifier `values.yaml` |
| Security | `dependency-review` | GitHub Advanced Security non active | Connu, non-bloquant |
| K8s deploy | `kubectl apply` fail | Selector immutable, Kyverno block | Voir `.claude/rules/k8s-deploy.md` |
| K8s deploy | `rollout timeout` | maxSurge/maxUnavailable deadlock | `maxUnavailable: 1, maxSurge: 0` |

### Step 4: Proposer le fix

Pour chaque erreur identifiee:
1. Fichier exact a modifier (chemin complet)
2. Diff propose (old → new)
3. Commande de verification locale
4. Impact sur les autres workflows

### Step 5: Rapport

```markdown
## CI Debug: [workflow-name] — [branch]

### Echec
- **Job**: [nom du job]
- **Step**: [nom du step]
- **Erreur**: [message d'erreur exact]

### Cause racine
[Explication]

### Fix propose
[Diff exact]

### Verification locale
```bash
[commande pour reproduire/verifier]
```

### Impact
[Autres workflows potentiellement impactes]
```

## Regles
- Toujours lire les logs complets avant de diagnostiquer
- Ne pas confondre: erreur intermittente vs erreur structurelle
- Si `dependency-review` echoue seul → ignorer (connu, GitHub Advanced Security)
- Si `container-scan` / `codeql` echoue seul → verifier si intermittent
- Toujours proposer une verification locale
