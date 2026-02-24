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

## Architecture L1 — Mode Accumulation

L1 fonctionne en 2 phases (collect + digest) avec accumulation JSONL:

```
watch-collect.sh (2x/jour)           watch-digest.sh (lundi)
  Sources → JSONL append      →     Dedup + tri + format digest
  .claude/watch/signals-YYYY-WNN.jsonl
```

### Phase 1: Collect (`watch-collect.sh`)
- Cadence: 2x/jour (08:00 + 18:00 CET)
- Append-only: chaque signal = 1 ligne JSONL
- Dedup a l'ecriture: source+title (case-insensitive)
- Fichier par semaine ISO: `signals-2026-W09.jsonl`
- 6 sources: Anthropic blog, npm, Reddit, HN, Cursor, Aider

### Phase 2: Digest (`watch-digest.sh`)
- Cadence: lundi 08:00 CET
- Lit les signaux de la semaine courante
- Deduplique (source+title), trie par score
- Produit le digest formate (voir format ci-dessous)
- Optionnel: poste sur Slack via `$SLACK_WEBHOOK`

### Format JSONL (un signal)

```json
{"ts":"2026-02-24T08:00:00+00:00","source":"reddit","title":"...","url":"...","score":142,"meta":{}}
```

### L'ancien one-shot (`competitive-watch.sh`) reste disponible pour affichage rapide en CLI.

## Format du Digest (L1 — hebdomadaire)

```
:telescope: VEILLE IA FACTORY — Semaine YYYY-WNN

:loudspeaker: BREAKING (action requise)
- [changement majeur qui impacte notre setup]

:new: NOUVEAUTES
- Claude Code vX.X.X : [features notables]
- Boris tip : [resume si nouveau thread]

:crossed_swords: CONCURRENCE
- Cursor : [mouvement notable]
- [autre concurrent] : [mouvement notable]

:speech_balloon: COMMUNAUTE (top signaux)
- [Reddit/HN posts classes par score]

:bulb: PATTERNS A TESTER
- [pattern vu dans la communaute qu'on n'utilise pas encore]

:bar_chart: NOTRE SCORE
- Setup actuel : XX/100 (dernier audit)

:dart: ACTION ITEMS
- [ ] [action concrete si necessaire]
```

## Execution

| Niveau | Cadence | Declencheur | Outil |
|--------|---------|-------------|-------|
| L1 Collect | 2x/jour (8h + 18h CET) | cron / launchd / n8n | `scripts/ai-ops/watch-collect.sh` |
| L1 Digest | Hebdo (lundi 8h CET) | cron / launchd / n8n | `scripts/ai-ops/watch-digest.sh` |
| L1 One-shot | Manuel (CLI) | Utilisateur | `scripts/ai-ops/competitive-watch.sh` |
| L2 Audit | Mensuel (1er du mois 8h UTC) | GHA cron | `.github/workflows/monthly-ia-factory-audit.yml` |
| L3 Benchmark | Trimestriel | Manuel | `/benchmark-competitors` slash command |

Setup cron/launchd/n8n: voir `scripts/ai-ops/CRON-SETUP.md`

## Usage

```
User: /competitive-watch digest     → lance le digest de la semaine courante
User: /competitive-watch collect    → lance une collecte manuelle
User: /competitive-watch audit      → affiche le dernier score audit
User: /competitive-watch benchmark  → lance le benchmark trimestriel complet
```

## Regles

- **Objectivite** : chercher ce que les concurrents font MIEUX, pas moins bien
- **Factuel** : toujours citer la source et la date
- **Actionnable** : chaque observation doit mener a une action concrete ou un "no action needed"
- **Pas de veille passive** : si rien de notable, le digest le dit explicitement
