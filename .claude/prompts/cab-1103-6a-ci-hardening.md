CAB-1103 Phase 6A: CI Hardening — zero tolerance sur les erreurs silencieuses.

Branch: `feat/cab-1103-6a-ci-hardening` (creer depuis main)

## Contexte
Le CI a des `|| true` qui masquent des erreurs. Les charts Helm ne sont pas valides en CI. Les seuils de coverage ne sont pas enforces partout.

## Taches

### 1. Supprimer tous les `|| true` des workflows
- Scanner `.github/workflows/*.yml` pour `|| true`, `|| echo`, `continue-on-error: true`
- Supprimer chaque occurrence sauf si documentee comme intentionnelle (ex: `kubectl delete --ignore-not-found`)
- Pour les steps qui echouent legitimement (dependency-review, container scan), utiliser `continue-on-error` avec un commentaire expliquant pourquoi

### 2. Ajouter `helm lint` dans le CI
- Creer ou modifier `.github/workflows/helm-ci.yml`
- Step: `helm lint charts/stoa-platform/`
- Trigger: push/PR qui modifie `charts/**`
- S'assurer que le chart lint passe: `cd charts/stoa-platform && helm lint .`
- Fixer les erreurs de lint si necessaire

### 3. Enforcer les seuils de coverage
- `control-plane-ui/`: verifier que `vitest.config.ts` a `coverage.thresholds` (doit etre ~50%)
- `portal/`: verifier le seuil (doit etre ~70%)
- `control-plane-api/`: verifier `pyproject.toml` `[tool.pytest.ini_options]` `--cov-fail-under` (doit etre 53)
- S'assurer que les CI workflows utilisent `npm run test:coverage` (pas juste `npm test`)

### 4. Valider
- `grep -r '|| true' .github/workflows/` doit retourner 0 resultats (hors commentaires)
- `helm lint charts/stoa-platform/` doit passer
- Les 3 coverage thresholds sont configures et documentes

## DoD
- [ ] Zero `|| true` dans les workflow files (sauf exceptions documentees)
- [ ] `helm lint charts/stoa-platform/` passe
- [ ] Coverage thresholds enforces: console-ui 50%, portal 70%, api 53%
- [ ] Commit: `ci: harden CI pipelines and enforce coverage thresholds (CAB-1103)`

## Contraintes
- Ne PAS toucher au code applicatif (src/)
- Ne PAS modifier les seuils de coverage a la baisse
- Ne PAS push
