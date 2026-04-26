---
id: plan-2026-04-26-uac-v2-mcp-projection
triggers: [a, b]
validation_status: executed
challenge_ref: docs/decisions/2026-04-26-uac-v2-mcp-projection.md
---

> **Reframed after Decision Gate #9** (2026-04-26). Original draft proposed Python+Rust parity in lockstep. Reframe: Python first, smoke/canary second, Rust **only if usage confirmed**. See `challenge_ref` for full arbitrage.
>
> **Status (2026-04-26, end of day) : EXECUTED.** PR 1 merged (`82c5ebb49`, #2585). PR 2 merged (`d368ae4a4`, #2588). PR 3 closed by signal #1 audit (NOGO Rust parity — gateway is a consumer of cp-api projection, not a generator). Go criteria atteint. Voir la section "Audit du signal #1" dans `challenge_ref`.

# Plan — UAC V2, projection MCP de la metadata `endpoint.llm`

## Objectif

Faire arriver la metadata `endpoint.llm` (summary, intent, side_effects, requires_human_approval, examples) jusqu'aux agents qui appellent `tools/list` côté gateway, **sans changer le schéma UAC ni la doctrine V1**. Bénéficiaire : tout LLM/agent consommant la gateway STOA — il voit aujourd'hui une description pauvre (`"GET /catalog/items/{id} — Example Catalog"`) et devra voir une description structurée portant l'intent et les side_effects.

## Scope

- **In** :
  - Modifier le générateur Python `control-plane-api/src/services/uac_tool_generator.py` pour enrichir `description` à partir de `endpoint.llm.*`. Format simple : `description = summary + intent + side_effects` (texte concaténé, pas de champ structuré). Fallback inchangé si `endpoint.llm` absent.
  - Tests unitaires : 2 cas dans cp-api (avec/sans `endpoint.llm`).
  - Ajouter un step "LLM-readiness" à `scripts/demo-smoke-test.sh` qui valide que la description projetée contient `Intent:` + `Side effects:`.
  - Enrichir `specs/uac/demo-httpbin.uac.json` avec un bloc `endpoint.llm` (sinon le smoke ne prouve rien).

- **Out** :
  - **PR Rust generator (parité `stoa-gateway/src/uac/`)** — déféré à *si nécessaire* (cf. conditions de réouverture dans `challenge_ref`). Tant que le chemin gateway réellement utilisé n'est pas vérifié, on ne touche pas Rust.
  - **Champ `examples[]` structuré au niveau tool MCP** — la spec MCP n'est pas confirmée sur ce point. En V1, on n'expose pas d'`examples` comme contrat normatif. Éventuellement `Examples: ...` en texte dans la `description`, jamais comme champ MCP séparé.
  - Champs V2 listés dans `.claude/docs/uac-llm-ready.md` mais non normatifs (`do_not_use_when`, `permissions`, `rate_limit_policy`, `approval_policy`, `test_generation_hints`) — V2.1.
  - Endpoint `/uac/<contract>/<endpoint>/metadata` LLM-optimisé séparé — déféré.
  - Toute modification du schéma `UacEndpointLlmSpec`.
  - Migration des contrats existants pour ajouter `endpoint.llm` rétroactivement (V1 reste : warning si absent, pas d'erreur).

## Phases

1. **PR 1 — Generator Python (cp-api)** *(prouve la mécanique)*
   - Modifier `uac_tool_generator.py:108-111` pour enrichir `description` quand `endpoint.llm` est présent. Format : `summary` + `\nIntent: <intent>` + `\nSide effects: <side_effects>` (+ mention `HUMAN APPROVAL REQUIRED` si applicable).
   - 2 tests unitaires (avec/sans metadata).
   - Pas de changement de signature ni d'`inputSchema` MCP. Pas de champ `examples` au niveau tool.
   - **Critère d'acceptance** : tests passent, fallback legacy inchangé sur les contrats sans `endpoint.llm`.

2. **PR 2 — Smoke + canary** *(prouve la chaîne utile)*
   - Enrichir `specs/uac/demo-httpbin.uac.json` avec un bloc `endpoint.llm` (un seul endpoint, conforme aux exemples canoniques de `specs/uac/examples/`).
   - Ajouter un step au `scripts/demo-smoke-test.sh` qui exerce `tools/list` et grep `Intent:` + `Side effects:`.
   - **Critère d'acceptance** : `bash scripts/demo-smoke-test.sh` passe en local k3d, le step LLM-readiness sort vert, les tools sans metadata gardent leur description legacy intacte.

3. **PR 3 — Rust parity** *(seulement si nécessaire)*
   - **Pré-requis avant ouverture** : confirmer que le chemin gateway → `tools/list` en prod/démo consomme effectivement la projection Rust (lecture du code d'appel + test runtime).
   - Si confirmé : miroir de PR 1 dans `stoa-gateway/src/uac/` + test cross-langage.
   - Si non confirmé : ticket backlog, pas d'ouverture cycle. Décision tracée par un commentaire dans la décision liée.

## Go / No-Go criteria

- **Go** si : `tools/list` expose `Intent:` + `Side effects:` sur le contrat canary (`demo-httpbin`), sans casser les tools legacy (qui restent sur leur description fallback). C'est le critère unique. Le calendrier n'est pas un critère.
- **No-Go** si : le protocole MCP tronque ou rejette la description multi-lignes côté un client cible (Claude Code, Codex, Inspector) — découvert au step canary. Réversion = revert PR 1 + ré-ouverture du plan avec contrainte de format.

## Assumptions

À stress-tester par le challenger :

1. **La vraie valeur est lisible côté agent, pas côté humain.** Si aucun agent en prod (Claude, Codex, autres) ne consomme aujourd'hui `tools/list` STOA, le ROI immédiat est nul et le travail compte pour la démo juin uniquement.
2. **Le protocole MCP supporte des descriptions multi-lignes** sans tronquage côté client. Non vérifié — c'est une affirmation que j'ai faite plus tôt sans certitude. À confirmer en lisant la spec MCP avant PR 1.
3. **Le protocole MCP supporte un champ `examples` au niveau tool.** Idem — non vérifié. Si non supporté, on ne pousse les `examples` que via `description` (texte) et on perd le bénéfice "few-shot structuré".
4. **Les deux générateurs (Python + Rust) doivent être modifiés en parité.** Si le Rust generator est en réalité dead code aujourd'hui (la projection prod passe par cp-api → cache → gateway sans regénération côté Rust), on peut faire seulement Python et économiser PR 2.
5. **Modifier la description des MCP tools n'est pas un breaking change** pour les clients existants. Si un client downstream parse la description en regex (peu probable mais possible), enrichir = casser.
6. **Le smoke test démo accepte un step supplémentaire** sans dépasser le budget temps actuel du runner CI/local.
7. **Les contrats existants en prod (s'il y en a)** restent valides en V1 (warning, pas erreur) — le validator confirme ça aujourd'hui mais à re-vérifier si on touche le smoke.
8. **La démo juin (multi-client UAC 5 étapes)** bénéficie réellement de cette enrichissement. Si la démo se concentre sur le parcours REST (déclarer → router → souscrire → appeler → métriques) sans toucher MCP/agent, ce travail est hors-chemin critique.

## Risques mineurs (pas des assumptions, juste des points d'attention)

- Le `description` enrichi peut faire passer `tools/list` d'une réponse compacte à une réponse plus volumineuse. Pas de risque fonctionnel mais à mesurer si on a des tools count élevés (>50).
- Le smoke step ajouté augmente le temps total du smoke démo de quelques secondes. Acceptable.
- Le Rust generator pourrait avoir un test snapshot qui casse. Refresh trivial mais à anticiper.

## Estimation grossière (post-reframe)

- PR 1 (cp-api generator + tests) : ~3h
- PR 2 (smoke + canary + contrat démo enrichi) : ~2h
- PR 3 (Rust parity, conditionnelle) : ~6h **si activée**, sinon 0h
- Total chemin critique (PR 1 + PR 2) : **~5h**. PR 3 sort du chemin critique tant que l'usage Rust n'est pas confirmé.
