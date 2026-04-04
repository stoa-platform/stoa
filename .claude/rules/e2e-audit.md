# E2E Audit Standard

## One Rule

All Playwright outputs (screenshots, videos, reports) go in **one place** per audit:

```
docs/audits/YYYY-MM-DD-<topic>/
├── README.md                # Rapport (template ci-dessous)
├── results.json             # Playwright JSON
├── report/index.html        # HTML report (ouvrir dans browser = screenshots + vidéos inline)
└── .gitignore               # Exclut *.webm
```

**Rien dans `e2e/test-results/`** (éphémère). **Rien dans `audit/<TICKET>/`** (legacy supprimé).

## Comment

```bash
# 1. Run
cd e2e && npx playwright test --config playwright.local.config.ts tests/local-<topic>.spec.ts

# 2. Archive
AUDIT=docs/audits/$(date +%Y-%m-%d)-<topic>
mkdir -p "$AUDIT/report"
cp -r reports/local/* "$AUDIT/report/"
cp reports/local/results.json "$AUDIT/results.json"
echo -e '*.webm\nvideos/' > "$AUDIT/.gitignore"

# 3. Commit
git add "$AUDIT" e2e/tests/local-<topic>.spec.ts
git commit -m "docs(e2e): <topic> audit"
```

## Ce qui est commité

| Fichier | Git | Pourquoi |
|---------|-----|----------|
| `README.md` | oui | Rapport lisible |
| `report/index.html` + `report/data/*.png` | oui | Preuves visuelles |
| `results.json` | oui | Machine-readable |
| `.gitignore` | oui | Protège le repo |
| `report/data/*.webm` | **non** | Trop lourd — re-générer avec le run |

## README.md template

```markdown
# Audit: <Title>

**Date**: YYYY-MM-DD | **Ticket**: CAB-XXXX | **PR**: #NNNN

## Scope
1-3 phrases.

## Results
**N pass, M skip, K fail** (durée)

## Bugs Found
| # | Sev | Component | Issue | Fix |
|---|-----|-----------|-------|-----|

## How to reproduce
\`\`\`bash
cd e2e && npx playwright test --config playwright.local.config.ts tests/local-<topic>.spec.ts
\`\`\`
```

## Test file

`e2e/tests/local-<topic>.spec.ts` — idempotent, timestamps dans les noms, pas de skip, pas de fake data.
