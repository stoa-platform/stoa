CAB-1103 Phase 6D: Test Loop Automation — smoke tests en CI + audit hebdo.

Branch: `feat/cab-1103-6d-test-loop` (creer depuis main)

## Contexte
Les smoke tests existent (`e2e/`) mais ne sont pas integres dans le CI post-deploy.
Pas d'audit de securite automatise periodique.

## Taches

### 1. Smoke test integration dans CI
Modifier les workflows de deploy pour ajouter un step post-deploy:

Fichier: `.github/workflows/reusable-k8s-deploy.yml` (ou les workflows specifiques)

Ajouter un job `smoke-test` apres le job `deploy`:
```yaml
smoke-test:
  needs: deploy
  runs-on: ubuntu-latest
  if: success()
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    - name: Install dependencies
      run: cd e2e && npm ci
    - name: Install Playwright browsers
      run: cd e2e && npx playwright install chromium --with-deps
    - name: Run smoke tests
      run: cd e2e && npx playwright test --grep @smoke
      env:
        BASE_URL: https://console.gostoa.dev
        PORTAL_URL: https://portal.gostoa.dev
      continue-on-error: true  # Smoke tests are informational post-deploy
    - name: Upload smoke test results
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: smoke-test-results
        path: e2e/test-results/
```

### 2. Ajouter `npm run test:smoke` dans `e2e/package.json`
```json
{
  "scripts": {
    "test:smoke": "npx playwright test --grep @smoke"
  }
}
```
Verifier que le script existe deja ou le creer.

### 3. Weekly audit workflow
Fichier: `.github/workflows/weekly-audit.yml`

```yaml
name: Weekly Security Audit

on:
  schedule:
    - cron: '0 8 * * 1'  # Lundi 8h UTC
  workflow_dispatch:       # Declenchement manuel

jobs:
  python-audit:
    name: Python Dependency Audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install pip-audit
        run: pip install pip-audit
      - name: Audit control-plane-api
        run: cd control-plane-api && pip-audit -r requirements.txt
      - name: Audit mcp-gateway
        run: cd mcp-gateway && pip-audit -r requirements.txt

  node-audit:
    name: Node Dependency Audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Audit control-plane-ui
        run: cd control-plane-ui && npm audit --audit-level=high
      - name: Audit portal
        run: cd portal && npm audit --audit-level=high
      - name: Audit e2e
        run: cd e2e && npm audit --audit-level=high

  rust-audit:
    name: Rust Dependency Audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install cargo-audit
        run: cargo install cargo-audit
      - name: Audit stoa-gateway
        run: cd stoa-gateway && cargo audit

  gitleaks:
    name: Secrets Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  helm-lint:
    name: Helm Chart Validation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Helm
        uses: azure/setup-helm@v4
      - name: Lint charts
        run: helm lint charts/stoa-platform/

  report:
    name: Audit Summary
    needs: [python-audit, node-audit, rust-audit, gitleaks, helm-lint]
    runs-on: ubuntu-latest
    if: always()
    steps:
      - name: Summary
        run: |
          echo "## Weekly Audit Results" >> $GITHUB_STEP_SUMMARY
          echo "- Python: ${{ needs.python-audit.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- Node: ${{ needs.node-audit.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- Rust: ${{ needs.rust-audit.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- Gitleaks: ${{ needs.gitleaks.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- Helm: ${{ needs.helm-lint.result }}" >> $GITHUB_STEP_SUMMARY
```

### 4. Verifier
- Le workflow `weekly-audit.yml` est syntaxiquement valide
- Le smoke test step est correctement integre dans le deploy pipeline
- `npm run test:smoke` fonctionne dans `e2e/`

## DoD
- [ ] `npm run test:smoke` defini dans `e2e/package.json`
- [ ] Smoke test step integre dans le CI post-deploy
- [ ] `.github/workflows/weekly-audit.yml` cree (Python + Node + Rust + gitleaks + Helm)
- [ ] Commit: `ci: add smoke test integration and weekly audit workflow (CAB-1103)`

## Contraintes
- Smoke tests en `continue-on-error: true` (informatifs, ne bloquent pas le deploy)
- Weekly audit: declenche aussi manuellement (`workflow_dispatch`)
- Ne PAS push
