---
id: decision-2026-04-19-dev-tools-gateway
plan_ref: docs/plans/2026-04-19-dev-tools-gateway.md
challenger: "GPT-5 (Codex, background exec)"
verdict: NO-GO
decision_gate_log: "#7"
decision_gate_log_url: "https://github.com/stoa-platform/stoa-docs/blob/0f6022b/HEGEMON/DECISION_GATE.md"
---

# Decision — 3 tools dev via gateway STOA locale

## Challenger prompt (verbatim)

````markdown
# Décision Challenge — Plan "3 tools dev via gateway STOA locale"

Tu es le challenger externe non-aligné pour un Decision Gate HEGEMON (framework STOA). Mission: **défoncer le plan ci-dessous**, pas le valider. Objectif: exposer les blindspots avant que l'équipe n'engage des points de sprint dessus.

## Contexte plateforme (à prendre en compte avant de challenger)

- **STOA Platform** = "European Agent Gateway" — API Management AI-Native. Kill feature: UAC (Universal API Contract) via MCP Gateway (`stoa-gateway`, Rust).
- **Flux de travail actuel des devs** (humain + IA): Claude Code (CLI Anthropic) et Codex (CLI OpenAI) sont utilisés directement dans le repo, sans gateway intermédiaire. Chacun a son propre contexte via CLAUDE.md / .codex/config.toml et MCP servers (Linear, Notion, etc.).
- **État actif cycle C15 (2026-04-19)**:
  - CAB-2088 démo committee arch EU en préparation (J-6, dry-run #2 vendredi 25).
  - CAB-2116 Phase 0.5 bench vient de sortir **RED/RED sur le coût**: per-op expansion +703% tokens, enriched-single +68%. Décision: Phase 1 CRDs per-op annulée, contract scenario abandonné. Log Decision Gate #6 publié.
  - CAB-2121 MCP auth gate **pas encore commité** (sur mauvaise branche), CAB-2109 contract matrix pending.
  - CAB-2113 Phase 0 complete mais admin-API visibility bug encore ouvert.
  - CAB-2123 public DynamicTool discovery shipped (15→89 tools anonymes, banking API per-op visibles).
- **Gateway locale**: k3d + Tilt, gateway tourne via `stoa-gateway` image + chart. Auth Keycloak. Découverte via `/mcp/v1/tools`.
- **Règle "1 MEGA par session"**: ajouter un nouveau MEGA dilue les priorités actives (démo + auth gate + audit catalog).
- **Décision Gate framework (HEGEMON)**: triggers = (a) Claude > 5h, (b) impact business direct, (c) irréversible. Challenger externe non-aligné obligatoire.

## Plan proposé

**Objectif**: exposer un workflow dev minimal via la gateway STOA locale, consommable par Claude Code et Codex, sans lancer un nouvel orchestrateur.

**Scope**:
- 3 tools MCP: `dev-plan(ticket|brief) -> plan + artefact`, `dev-review(diff|pr_ref) -> verdict + findings + score`, `dev-status(ticket|run_id) -> état + next step`
- Transport: gateway STOA locale
- Clients: Claude Code + Codex
- Hors scope: `execute`, `ship`, auto-merge, auto-Done Linear, remote MCP dédié

**Phases**:
1. Contrat (3 tools I/O + format artefact unique + métriques succès)
2. Core local (wrapper existant contexte+review, tests unit+smoke, core marche sans agent)
3. Exposition via gateway STOA locale (auth/policy min, découverte MCP, stoactl mcp comme debug)
4. Consommation Claude/Codex (3 parcours: plan, review, status)
5. Canary 3-5 tickets réels, mesures: temps→plan, retouches manuelles, temps→1er diff, tool mismatch
6. Décision: si adoption → stabiliser + `stoactl dev ...`; sinon → abandonner execute/ship

**Go/No-Go**: Go si 3 tools utilisés par Claude+Codex sur tickets réels avec moins de routing humain. No-Go si valeur dépend d'un orchestrateur multi-stage.

## Ton mandat

Challenge dur. Pas de politesse, pas de "c'est un bon plan mais...". Structure ta réponse en 5 blocs:

### 1. Le vice caché
Quelle est l'hypothèse *non formulée* qui tient tout le plan debout ? Si elle tombe, qu'est-ce qui casse ?

### 2. Les coûts que le plan ne chiffre pas
- Maintenance des schémas MCP (x2 clients, x2 schémas à synchroniser)
- Auth/policy sur la gateway locale qui n'existe pas (pas juste "minimales")
- Latence ajoutée vs appel CLI direct
- Dette: qu'est-ce qu'on doit maintenir quand la gateway crash, quand Claude/Codex bumpent leur MCP spec, quand les artefacts format change ?
- Quel est le **coût d'opportunité** vs les priorités actives (démo CAB-2088, auth gate CAB-2121, bench fallout CAB-2116) ?

### 3. L'alternative que le plan n'explore pas
Propose au moins **2 alternatives** qui atteignent le même objectif sans gateway. Par exemple:
- Un CLI local simple (`stoactl dev plan|review|status`) appelé par Claude et Codex via Bash tool (pas MCP)
- Un template de prompt partagé + script hook post-commit
- Ou laisser Claude/Codex faire nativement ce qu'ils font déjà

Pour chaque alternative: effort, risque, valeur comparée.

### 4. Les trous dans les métriques
Phase 5 mesure "temps→plan acceptable", "gain net ou parité", "fréquence d'échec". Qu'est-ce qui manque ?
- Baseline avant phase 1 ?
- Seuils chiffrés ?
- Mesure du coût token/latence ajouté par la gateway ?
- Critère d'arrêt explicite si phase 2 ou 3 dérape ?

### 5. Le verdict brutal
- **GO / NO-GO / REFRAME** ?
- Si REFRAME: en 3 bullets max, quelle est la forme la plus petite qui mérite d'être tentée ?
- Si NO-GO: quel est le signal qui devrait faire revenir ce plan dans 1-3 mois ?

## Contraintes de sortie

- Max 600 mots.
- Pas de disclaimers.
- Pas de reformulation du plan.
- Français.
- Ne valide **rien** par défaut. Ton job est de trouver pourquoi ça échouerait.
````

## Challenger output (verbatim)

Executed via `codex exec --skip-git-repo-check` (OpenAI Codex v0.121.0, model `gpt-5.4`, reasoning effort `xhigh`). Tokens used: 88 563. Session id: `019da744-3050-7220-a1b3-fcb8abd2b2d1`.

````markdown
### 1. Le vice caché

L'hypothèse non dite: **le problème est un problème de transport/outillage MCP**, alors qu'il ressemble surtout à un problème de **discipline de workflow et de format de sortie**. Claude Code et Codex savent déjà faire plan/review/status dans le repo avec leur contexte natif. Le plan suppose qu'un habillage gateway rendra ces comportements plus fiables et plus adoptés.

Si cette hypothèse tombe, tout casse:
- la gateway ne crée aucune valeur, elle **interpose** juste une couche entre deux outils qui fonctionnent déjà ;
- le "format artefact unique" devient une fiction, parce que plan/review/status n'ont pas les mêmes besoins et Claude/Codex ne consomment pas pareil ;
- le critère Go/No-Go est biaisé: les agents contourneront le tool dès qu'il ralentit ou rigidifie.

### 2. Les coûts que le plan ne chiffre pas

- **Schémas**: ce n'est pas "x2". C'est au minimum **3 tools x input/output x 2 clients**, plus la compatibilité de l'artefact. À la moindre dérive de wording, un client dégrade sans casser franchement: le pire type de bug.
- **Auth/policy locale**: "minimales" est un mensonge. CAB-2121 n'est même pas commité. Donc il faut concevoir, brancher, tester et documenter: Keycloak, scopes, policy mapping, fallback local, erreurs 401/403, rotation, debug.
- **Latence**: direct CLI = process local. Gateway = discovery MCP, auth, sérialisation, hop réseau local, wrapper, réponse structurée. Vous ajoutez du délai sur des actions à forte fréquence et faible tolérance au frictionnel.
- **Dette d'exploitation**: qui dépanne quand k3d/Tilt/gateway/Keycloak cassent ? Qui tient la matrice de smoke tests Claude/Codex après bump MCP spec ? Qui versionne l'artefact quand `dev-review` a besoin d'un nouveau champ ?
- **Coût d'opportunité**: vous ouvrez un nouveau front alors que le cycle est déjà saturé: CAB-2088 à J-6, CAB-2121 non sécurisé, CAB-2116 vient de prouver que les intuitions "contract-first/per-op" explosent au coût, CAB-2109 pending. Avec la règle "1 MEGA par session", ce plan n'est pas un side quest, c'est une collision frontale.

### 3. L'alternative que le plan n'explore pas

- **CLI local `stoactl dev plan|review|status`**
  - Effort: 2-4 jours.
  - Risque: faible.
  - Valeur: 80% de l'objectif sans gateway, sans auth, sans MCP drift. Claude et Codex peuvent l'appeler via shell et récupérer un JSON stable.
- **Prompt contract partagé + script repo**
  - Effort: 1-2 jours.
  - Risque: faible à moyen.
  - Valeur: moyenne, mais excellente pour tester si le besoin est réel. Un template strict + un parseur de sortie suffit pour mesurer adoption/qualité.
- **Ne rien interposer, observer l'existant**
  - Effort: <1 jour.
  - Risque: minimal.
  - Valeur: potentiellement supérieure, parce que vous mesurez le vrai usage natif avant d'inventer une couche.

### 4. Les trous dans les métriques

- Aucune **baseline** sur tickets comparables avant phase 1.
- Aucun **seuil chiffré**: "moins de routing humain" ne veut rien dire. Combien: 20%, 50% ?
- Aucun suivi explicite de **coût token/latence** ajouté par la gateway.
- Rien sur la **qualité**: taux de faux findings en review, plans inutilisables, statuts obsolètes, taux de contournement manuel.
- Aucun **stop-loss**: si phase 2 dépasse X jours, si phase 3 dépend de CAB-2121, si Claude/Codex divergent sur 1 tool sur 3, on arrête quand ?

### 5. Le verdict brutal

**NO-GO.**

À reconsidérer dans 1-3 mois seulement si trois signaux existent:
- CAB-2088 est passé, CAB-2121 est mergé et stable, le fallout CAB-2116 est absorbé.
- Un pilote **sans gateway** prouve une demande réelle sur 10+ tickets avec baisse mesurée du routing humain.
- La gateway locale a déjà démontré sa stabilité auth/discovery sur un use case moins fragile que le workflow dev.
````

## Arbitrage

- **Verdict:** NO-GO
- **Rejected because:** the plan mis-frames a workflow-discipline problem as an MCP transport problem, and under-prices auth + ops-debt + opportunity cost against active C15 priorities.

## Reopen conditions

Revisit in 1–3 months only if **all three** hold:

1. CAB-2088 demo shipped, CAB-2121 MCP auth gate merged stable, CAB-2116 cost fallout absorbed
2. A no-gateway pilot (alternative 1 or 2 above) proves real demand on 10+ tickets, with a measured drop in human routing
3. The STOA gateway locale has demonstrated auth + discovery stability on a less fragile use case than the dev workflow itself

## Meta-signal

The Claude → Codex challenge itself was executed during this gate via `codex exec --skip-git-repo-check` + `run_in_background: true` — proving the intended use case (cross-LLM challenge for plan validation) is already achievable with **zero new MCP surface**.

## External index

Registered in `stoa-docs/HEGEMON/DECISION_GATE.md` as log #7 (merged in commit [`0f6022b`](https://github.com/stoa-platform/stoa-docs/blob/0f6022b/HEGEMON/DECISION_GATE.md) on 2026-04-19) as a one-line entry. **This file in `docs/decisions/` is the self-contained source of truth**; the stoa-docs log is the cross-repo index.
