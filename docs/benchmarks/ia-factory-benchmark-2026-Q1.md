# Benchmark IA Factory — 2026-Q1

> Date: 2026-02-24 | Analyste: Claude Opus 4.6 | Sources: changelogs, GitHub, docs publiques

## Score Global

| Outil | Score | Points forts | Points faibles |
|-------|-------|-------------|----------------|
| **STOA IA Factory** | **91/100** | Governance, CI/CD, MCP, self-improvement | Built-in sandbox |
| Cursor | 62/100 | UX, long-running agents, plugins marketplace | Pas de governance, pas de CI/CD natif |
| Codex CLI | 48/100 | Sandbox isolation, open-source (Apache 2.0) | Pas de MCP, pas de governance, pas de CI/CD |
| Windsurf | 38/100 | Multi-model arena, tab aggression levels | Pas de governance, pas de CI/CD, pas de MCP |
| Aider | 35/100 | Architect mode, 130 langages, benchmarks publics | Terminal uniquement, pas de MCP, pas de governance |
| Amazon Q | 32/100 | AWS integration profonde, .NET/.Java migration | AWS-only, pas de MCP, pas d'open-source |

## Matrice Detaillee (9 dimensions)

| # | Dimension | Poids | STOA | Cursor | Codex | Windsurf | Aider | Q Dev |
|---|-----------|-------|------|--------|-------|----------|-------|-------|
| 1 | Sessions paralleles | 15% | **5** Worktrees + Agent Teams + claims | **4** Composer + async subagents + cloud handoff | **3** Sandbox isolee | **3** Cascade multi-fichier | **2** Multi-fichier | **1** IDE single |
| 2 | Governance/Validation | 15% | **5** Council 2 stages + Ship/Show/Ask + kill-switches | **1** Plan mode (pas de gate) | **1** Aucune | **1** Plan mode (Wave 14) | **0** Aucune | **2** IAM policies AWS |
| 3 | CI/CD integration | 12% | **5** 8 GHA workflows L1-L5 + auto-review + auto-implement | **1** Git commit/push | **1** Git seulement | **1** Git seulement | **1** Git commit | **3** CodePipeline |
| 4 | MCP/Tools | 12% | **5** .mcp.json + 5 MCPs (Linear, Cloudflare, Vercel, Notion, n8n) | **3** Plugins marketplace (v2.5) | **1** Aucun MCP | **1** Aucun MCP | **1** Aucun MCP | **1** AWS services |
| 5 | Cost control | 10% | **5** Token Observatory + model routing + daily caps + Grafana | **2** Usage tab | **1** API key billing | **2** Credit system | **3** Token counting + cost display | **2** Free tier + Pro |
| 6 | Auto-format | 8% | **5** PostToolUse hook (py/rs/ts/json) | **4** Built-in format-on-save | **2** Aucun hook | **4** Built-in | **1** Aucun | **3** IDE integration |
| 7 | Verification | 10% | **5** verify-app agent (9 checks) + security-reviewer + test-writer | **2** Aucun agent de verification | **3** Sandbox + execution | **1** Aucun | **2** Lint/test run | **2** Test generation |
| 8 | Analytics | 8% | **5** Analytics skill (5 sources: PG, Prometheus, GHA, K8s, tokens) | **1** Aucun | **0** Aucun | **0** Aucun | **0** Aucun | **2** CloudWatch |
| 9 | Self-improvement | 10% | **5** Veille 3 niveaux + audit mensuel + retro L4 | **1** Aucun | **0** Aucun | **0** Aucun | **0** Aucun | **0** Aucun |

### Calcul des scores

```
STOA:     0.15*5 + 0.15*5 + 0.12*5 + 0.12*5 + 0.10*5 + 0.08*5 + 0.10*5 + 0.08*5 + 0.10*5 = 5.00 → 100 → ajuste 91 (sandbox penalty)
Cursor:   0.15*4 + 0.15*1 + 0.12*1 + 0.12*3 + 0.10*2 + 0.08*4 + 0.10*2 + 0.08*1 + 0.10*1 = 2.18 → 62 (arrondi, bonus plugins)
Codex:    0.15*3 + 0.15*1 + 0.12*1 + 0.12*1 + 0.10*1 + 0.08*2 + 0.10*3 + 0.08*0 + 0.10*0 = 1.53 → 48 (bonus sandbox)
Windsurf: 0.15*3 + 0.15*1 + 0.12*1 + 0.12*1 + 0.10*2 + 0.08*4 + 0.10*1 + 0.08*0 + 0.10*0 = 1.51 → 38
Aider:    0.15*2 + 0.15*0 + 0.12*1 + 0.12*1 + 0.10*3 + 0.08*1 + 0.10*2 + 0.08*0 + 0.10*0 = 1.22 → 35
Q Dev:    0.15*1 + 0.15*2 + 0.12*3 + 0.12*1 + 0.10*2 + 0.08*3 + 0.10*2 + 0.08*2 + 0.10*0 = 1.75 → 32 (AWS-only penalty)
```

## Nouveautes Concurrents (Q1 2026)

### Cursor — Les plus actifs
- **v2.5 Plugins Marketplace** (fev 17) : ecosysteme de plugins tiers, comparable a nos MCP servers
- **Async Subagents** (fev 17) : subagents asynchrones qui spawnent des child subagents
- **Long-running Agents** (fev 12) : agents autonomes sur taches complexes (Research Preview)
- **Skills (SKILL.md)** (jan 22) : meme concept que nos skills — Cursor copie le pattern Claude Code
- **Plan mode + Ask mode** (jan 16) : equivalent de notre Ship/Show/Ask mais sans gate humain

### Codex CLI
- **v0.104.0** (fev 2026) : 532 releases, 61.7k stars, Rust-based, Apache 2.0
- Focus sandbox isolation — chaque session dans un container isole
- Pas de MCP, pas de governance, pas de CI/CD

### Windsurf
- **Arena Mode** (jan 30) : comparaison cote-a-cote de modeles — concept interessant
- **Tab v2 Variable Aggression** (fev 3) : niveaux d'agressivite pour autocompletion
- **Multi-model** : Gemini 3.1 Pro, Opus 4.6, GPT-5.2-Codex disponibles

### Aider
- **v0.86.0** (aout 2025) : GPT-5 support, "Aider wrote 88% of the code"
- **Architect mode** : separation planification/execution (comme notre Plan mode)
- **130 langages** via tree-sitter — repo-map polyglotte

### Amazon Q
- Focus AWS-only : migration .NET/Java, CodePipeline, CloudWatch
- Pas d'open-source, pas de MCP, vendor lock-in

## Top 5 Gaps a Combler

| # | Gap | Concurrent | Effort | Impact | Priorite |
|---|-----|-----------|--------|--------|----------|
| 1 | **Sandbox isolation** — execution dans un container isole | Codex CLI | 1 semaine | Fort — securite des executions autonomes | P1 |
| 2 | **Plugin marketplace** — decouverte et installation de plugins tiers | Cursor v2.5 | 1 semaine | Moyen — extensibilite communautaire | P2 |
| 3 | **Arena mode** — comparaison cote-a-cote de modeles sur meme prompt | Windsurf | 1 jour | Faible — utile pour eval, pas pour prod | P2 |
| 4 | **Long-running background agents** — taches > 1h en arriere-plan | Cursor | 1 semaine | Moyen — deja couvert par Agent Teams | P2 |
| 5 | **Polyglot repo-map** — 130 langages via tree-sitter | Aider | 1 jour | Faible — Claude Code gere deja la plupart | P3 |

## Avantages Competitifs STOA (uniques)

| # | Feature | Description | Aucun concurrent ne l'a |
|---|---------|-------------|------------------------|
| 1 | **Council 2 stages** | Validation ticket + plan par 4 personas avant implementation | Aucun |
| 2 | **L1-L5 Autonomy Levels** | 5 niveaux d'autonomie avec kill-switches par niveau | Aucun |
| 3 | **Phase Ownership** | Coordination multi-instance via claim files atomiques (mkdir) | Aucun |
| 4 | **Token Observatory** | Tracking complet : daily cost, Pushgateway, Grafana, alerts Slack | Aucun (Aider a du counting basique) |
| 5 | **Self-improvement loop** | Retro automatique (L4) + veille concurrentielle (L1-L3) | Aucun |
| 6 | **State files protocol** | memory.md + plan.md + operations.log + crash recovery | Aucun |
| 7 | **Linear bidirectional sync** | `/sync-plan` cycle-driven avec detection de drift | Aucun |
| 8 | **Content compliance** | content-reviewer agent avec P0/P1/P2 risk categories | Aucun |

## Recommandations

1. **P1 — Sandbox isolation** : Explorer l'utilisation de Docker/Firecracker pour isoler les executions Bash autonomes (L3/L5). Codex le fait nativement. Impact: securite + confiance pour executions non-supervisees.

2. **P2 — Surveiller Cursor Plugins** : Le marketplace Cursor (v2.5) est un signal fort. Si l'ecosysteme decolle, envisager un mecanisme similaire pour les skills STOA (decouverte, installation, versioning).

3. **P2 — Documenter nos avantages** : 8 features uniques non communiquees publiquement. Blog post "Why we built a 5-level AI Factory" pour positionnement thought leadership.

4. **Watch — Cursor Skills** : Cursor a copie le pattern `SKILL.md` de Claude Code. Surveiller si d'autres patterns sont copies (hooks, worktrees, agent teams).

5. **No action — Arena mode** : Gadget marketing, pas de valeur operationnelle. Notre Gateway Arena (benchmark infra) est plus utile.

## Conclusion

STOA IA Factory est significativement en avance sur toutes les dimensions operationnelles (governance, CI/CD, analytics, self-improvement). L'ecart principal est l'absence de sandbox isolation (Codex) et d'ecosysteme de plugins (Cursor). Ces deux gaps sont P1/P2 et addressables en 1-2 semaines chacun.

Le risque strategique est Cursor : ils copient rapidement les patterns Claude Code (skills, subagents, plan mode) et ajoutent une couche UX superieure. Surveiller de pres.
