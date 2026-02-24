# Benchmark Competitif IA Factory

Lance un benchmark trimestriel de notre IA Factory vs la concurrence.

## Etape 1 : Collecter les donnees

Pour chaque outil, verifie les dernieres features :

### Claude Code (notre stack)
- Version actuelle : `claude --version`
- Features : worktrees, agent teams, skills, hooks, subagents, MCP
- Notre score audit : `cat .claude/audit-score.txt`

### Cursor
- Cherche les dernieres features sur https://cursor.com/changelog
- Focus : ce qu'ils font qu'on ne fait pas

### Windsurf (Codeium)
- Cherche les dernieres features sur https://codeium.com/blog
- Focus : flows, cascade, multi-file editing

### Aider
- Cherche sur https://aider.chat/HISTORY.html
- Focus : integrations, benchmarks, modes

### OpenAI Codex CLI
- Cherche sur https://github.com/openai/codex
- Focus : sandbox, autonomie, pricing

### Amazon Q Developer
- Focus : AWS integration, enterprise features

### Google Gemini CLI / Jules
- Focus : BigQuery integration, workspace integration

## Etape 2 : Matrice de comparaison

Produis un tableau :

| Capacite | STOA IA Factory | Cursor | Windsurf | Aider | Codex | Score STOA |
|----------|----------------|--------|----------|-------|-------|------------|
| Sessions paralleles | Worktrees + Agent Teams | Composer | Cascade | Multi-fichier | Sandbox | /5 |
| Governance/Validation | Council 2 stages | Non | Non | Non | Non | /5 |
| CI/CD integration | 8 GHA L1-L5 | Git | Git | Git | Non | /5 |
| MCP/Tools | .mcp.json + 5 MCPs | Non | Non | Non | Non | /5 |
| Cost control | Token Observatory | Usage tab | ? | Token counting | ? | /5 |
| Auto-format | PostToolUse hook | Built-in | Built-in | Non | Non | /5 |
| Verification | verify-app agent | Non | Non | Lint | Sandbox | /5 |
| Analytics | Analytics skill | Non | Non | Non | Non | /5 |
| Veille/Self-improve | competitive-watch | Non | Non | Non | Non | /5 |

## Etape 3 : Recommandations

Liste 3-5 features des concurrents qu'on devrait adopter, avec :
- Feature description
- Quel concurrent la fait
- Effort d'implementation (1h / 1 jour / 1 semaine)
- Impact estime sur la productivite

## Etape 4 : Rapport

Sauvegarde le rapport dans `docs/benchmarks/ia-factory-benchmark-YYYY-QX.md`
Notifie via Slack si le webhook est configure.
