---
name: competitive-watch
description: Veille concurrentielle IA Factory — sources, digest format, audit scoring.
argument-hint: "[digest | audit | benchmark]"
---

# Competitive Watch Skill

Veille concurrentielle integree a l'IA Factory STOA. 3 niveaux d'execution.

## Sources (par priorite)

### 1. Boris Cherny (@bcherny) — Createur Claude Code
- X/Twitter : https://x.com/bcherny
- Threads : https://threads.net/@boris_cherny
- Agregateur : https://howborisusesclaudecode.com
- Frequence : ~1 thread majeur / 2 semaines

### 2. Anthropic Engineering Blog
- https://www.anthropic.com/engineering
- https://www.anthropic.com/news
- Claude Code changelog : `claude --version` + release notes

### 3. Claude Code Docs & Releases
- https://code.claude.com/docs
- https://github.com/anthropics/claude-code/releases
- Version check : `npm view @anthropic-ai/claude-code version`

### 4. Concurrence directe
| Outil | Changelog | Focus |
|-------|-----------|-------|
| Cursor | https://cursor.com/changelog | Composer, multi-file, AI rules |
| Windsurf (Codeium) | https://codeium.com/blog | Cascade, flows |
| Aider | https://aider.chat/HISTORY.html | Modes, benchmarks |
| OpenAI Codex CLI | https://github.com/openai/codex | Sandbox, autonomie |
| Amazon Q Developer | https://aws.amazon.com/q/developer/ | AWS integration |
| Google Jules / Gemini CLI | https://developers.googleblog.com | Workspace integration |

### 5. Communaute
- Reddit r/ClaudeAI : top posts semaine
- Reddit r/cursor : top posts semaine
- Hacker News : recherche "Claude Code" ou "AI coding"
- Dev.to / Medium : tags "claude-code", "ai-coding-assistant"

### 6. MCP Ecosystem
- https://github.com/modelcontextprotocol
- Nouveaux MCP servers populaires
- Patterns d'integration emergents

## Format du Digest (L1 — hebdomadaire)

```
:telescope: VEILLE IA FACTORY — Semaine du [DATE]

:loudspeaker: BREAKING (action requise)
- [changement majeur qui impacte notre setup]

:new: NOUVEAUTES
- Claude Code vX.X.X : [features notables]
- Boris tip : [resume si nouveau thread]
- [autre nouveaute]

:crossed_swords: CONCURRENCE
- Cursor : [mouvement notable]
- [autre concurrent] : [mouvement notable]

:bulb: PATTERNS A TESTER
- [pattern vu dans la communaute qu'on n'utilise pas encore]

:bar_chart: NOTRE SCORE
- Setup actuel : XX/100 (dernier audit)
- Ecart identifie : [si applicable]

:dart: ACTION ITEMS
- [ ] [action concrete si necessaire]
```

## Execution

| Niveau | Cadence | Declencheur | Outil |
|--------|---------|-------------|-------|
| L1 Digest | Hebdo (lundi 8h CET) | n8n schedule | `scripts/ai-ops/competitive-watch.sh` (CLI) ou n8n workflow |
| L2 Audit | Mensuel (1er du mois 8h UTC) | GHA cron | `.github/workflows/monthly-ia-factory-audit.yml` |
| L3 Benchmark | Trimestriel | Manuel | `/benchmark-competitors` slash command |

## Usage

```
User: /competitive-watch digest     → lance le script CLI de veille
User: /competitive-watch audit      → affiche le dernier score audit
User: /competitive-watch benchmark  → lance le benchmark trimestriel complet
```

## Regles

- **Objectivite** : chercher ce que les concurrents font MIEUX, pas moins bien
- **Factuel** : toujours citer la source et la date
- **Actionnable** : chaque observation doit mener a une action concrete ou un "no action needed"
- **Pas de veille passive** : si rien de notable, le digest le dit explicitement
