---
id: plan-2026-05-07-ai-factory-governance
triggers: [b, c]
validation_status: challenged
challenge_ref: "docs/decisions/2026-05-07-ai-factory-governance.md"
---

# Plan — AI Factory Governance Alignment

## Decision Gate #11 result

**Verdict: REFRAME.** The challenger rejected the framing "align a new playbook with stable canon" because the canon is already drifting: public governance docs, ADR-061, and local operating rules disagree on Council composition and thresholds. The retained signal is to canonize only the separation-of-powers principle for critical AI-assisted changes, not the full 5-category taxonomy.

This plan remains blocked until rewritten under the narrower frame: **minimal separation-of-powers doctrine for AI-assisted development**. No canon edit is authorized from this draft.

## Objectif

Aligner un nouveau playbook de gouvernance multi-agents (rôles, pattern Audit→Council→Plan→Execute→Review, doctrine PR, anti-patterns) avec la doctrine STOA déjà canonisée, **sans créer de seconde source de vérité concurrente**.

## Scope

- **In:**
  - Réconciliation explicite du draft fourni 2026-05-07 avec `HEGEMON/DECISION_GATE.md`, `ADR-061 council-multi-stage-review`, `docs/governance/review-loop.md`, `CLAUDE.md`, `.claude/docs/`, `.claude/skills/decompose/`.
  - Décision sur le modèle de rôles à canoniser (5 catégories proposées, voir §Modèle affiné).
  - Décision sur la cible de placement (HEGEMON interne / ADR-067 binding / `docs/governance/` public).
  - Décision sur la doctrine PR LOC (statu quo strict / assouplissement avec ADR séparé).
- **Out:**
  - Édition de `HEGEMON/DECISION_GATE.md` pendant son gel discipline (jusqu'à ~2026-05-22).
  - Refonte des 8 logs Decision Gate déjà actés (#1–#8).
  - Création d'un nouveau framework Council (le 8-personas existe — HEG-PAT-003 / CAB-2054).

## Triggers (justification)

- **(b) Business impact** — la gouvernance multi-agents conditionne tout le rythme de livraison STOA + le signal OSS public ; un changement de doctrine impacte release engineering, cycle planning, et perception communauté.
- **(c) Irreversible** — une fois canonisée dans `HEGEMON/` ou un ADR, la doctrine devient pattern persistant cité par d'autres docs ; un retour arrière coûte une vague de PR de réconciliation.
- (a) non déclenché — temps Claude < 5h sur ce plan.

## Phases

1. **Plan canonique** (ce document) — draft + tensions + options + matrice de réconciliation à blanc. Aucune édition de canon existant.
2. **Decision Gate #11 — challenger GPT** — sujet : *AI Factory Governance Alignment*. Prompt en §Decision Gate prompt. Verdict consigné dans `docs/decisions/2026-05-07-ai-factory-governance.md` + log dans `HEGEMON/DECISION_GATE.md` (post-gel ou append-only seed).
3. **Réconciliation explicite** — pour chaque doc impacté, marquer COMPLEMENTS / SUPERSEDES / REPLACES / ALIGNS WITH. Matrice §Reconciliation matrix remplie. Aucun "doc magique" qui contourne les références existantes.
4. **Choix de placement** — selon verdict :
   - GO sans amendement majeur → `HEGEMON/AI_FACTORY_AGENT_ROLES.md` (1 page, sœur de `DECISION_GATE.md`).
   - GO avec normativité forte → ADR-067 dans `stoa-docs/docs/architecture/adr/`.
   - GO public-facing → `stoa-docs/docs/governance/agent-roles.md`.
   - REFRAME → boucle vers Phase 1 v2.
   - NO-GO → archivage du plan + reopen conditions.
5. **Rollout** — édition synchronisée des références (`CLAUDE.md`, `.claude/docs/*.md`, skills) avec PR atomique unique. Aucune dérive doctrinale partielle.

## Go / No-Go criteria

- **Go si** : challenger valide la sémantique des rôles, la matrice de réconciliation est complète, et le placement choisi ne crée aucune contradiction avec les 8 logs Decision Gate antérieurs.
- **No-Go si** : challenger conclut que le draft duplique sans ajouter, OU les tensions ne peuvent pas être résolues sans réviser la doctrine gelée (`DECISION_GATE.md`).
- **Reframe si** : challenger valide l'intention mais propose un repositionnement (ex : "ce n'est pas un playbook de rôles, c'est une charte de séparation des pouvoirs").

## Assumptions

- Le draft 2026-05-07 reflète une intention de **clarification**, pas une réécriture du canon existant.
- Le 8-personas Council reste valide tel quel (HEG-PAT-003, ADR-061, `review-loop.md`).
- La règle PR ≤300 LOC tient comme baseline ; un assouplissement éventuel passe par ADR-067 séparé, pas par ce playbook.
- Codex `run_in_background` est un pattern d'exécution établi (Decision Gate #7, démo CAB-2148) et reste tel quel.
- Le gel de `DECISION_GATE.md` (30 jours sans édition, jusqu'à ~2026-05-22) est respecté ; toute évolution des triggers est différée.

---

## Tensions à arbitrer

### Tension #1 — Council vs Challenger (sémantique inversée)

**Constat**
Le draft Section 3.2 écrit *"ChatGPT — Council / Arbitrage / Doctrine"*.

Or `stoa-docs/HEGEMON/DECISION_GATE.md:21-24` est explicite :

| Rôle | Source | Owns |
|------|--------|------|
| Internal Council | Claude, 8 personas (HEG-PAT-003) | Architecture, security, governance |
| External Challenger | **GPT** (ou autre non-Claude) | ROI, simplicity, reframe |

Hard rule : *"The challenger must NOT receive personas or Council rubric. A persona-fed challenger is a digital twin, not a challenger."*

Confirmé aussi par `ADR-061 council-multi-stage-review` et `docs/governance/review-loop.md` (judges = Archi 50x50 + Team Coca + OSS Killer + Better Call Saul).

**Impact**
8 logs Decision Gate (#1–#8) sont actés sur cette sémantique. Inverser créerait rétro-incohérence.

**Options**
- **a)** Réécrire le draft pour utiliser la sémantique canon (recommandé).
- **b)** Garder l'ambiguïté du draft → 2 canons concurrents (rejeté).
- **c)** Demander au challenger si la sémantique canon doit être révisée (improbable, gel `DECISION_GATE.md` actif).

---

### Tension #2 — Doctrine PR ≤300 LOC

**Constat**
Le draft Section 6 propose : *"Review slice ≤300 LOC. PR globale autorisée si architecture cohérente, commits structurés, validations explicites, rollback clair, scope maîtrisé."*

La règle « PR > 300 LOC interdit » est référencée à **9 endroits** :
- `stoa/CLAUDE.md:168` (règle binaire GO/NOGO)
- `.claude/docs/git-workflow.md:226`
- `.claude/docs/phase-ownership.md:120`
- `.claude/docs/ai-factory.md:97,108`
- `.claude/docs/workflow-essentials.md:36`
- `.claude/skills/decompose/SKILL.md:117,199`
- `docs/audits/2026-04-17-mcp-claude-ai-connector/HANDOFF.md:96,211`

**Impact**
Assouplissement = changement de règle binaire avec impact tooling (skill `/decompose` calibré sur seuil), CI (regression-guard est insensible au LOC mais les revues humaines en dépendent), perception PR (audit trail historique).

**Options**
- **a)** Garder la règle binaire dans ce playbook ; ouvrir ADR-067 séparé pour formaliser exceptions (recommandé).
- **b)** Intégrer l'assouplissement dans le playbook → édition de 9 docs en cascade sans Decision Gate dédié (rejeté).
- **c)** Différer la question : le playbook ne mentionne pas du tout la doctrine PR.

---

### Tension #3 — Decision Gate trigger expansion

**Constat**
`HEGEMON/DECISION_GATE.md` a 3 triggers abstraits : (a) temps Claude > 5h, (b) business impact, (c) irreversible.

Le draft Section 10 liste 9 triggers concrets : sécurité, release engineering, gouvernance Git, versioning, suppression historique, exposition publique, breaking changes, architecture transverse, workflows CI/CD critiques.

**Discipline en vigueur** : *"30 days without editing this framework. Use it, don't optimise it."* (gel jusqu'à ~2026-05-22).

**Impact**
Édition de `DECISION_GATE.md` = violation explicite de sa propre discipline. Risque d'inflation des triggers (chaque sujet "important" devient une exception).

**Options**
- **a)** Présenter Section 10 comme **exemples non-normatifs** sous (b)/(c), pas comme remplacement (recommandé).
- **b)** Attendre fin du gel (~2026-05-22) puis proposer un patch séparé à `DECISION_GATE.md` via Decision Gate #12 dédié.
- **c)** Supprimer Section 10 du playbook.

---

### Tension #4 — Rigidité des rôles vs réalité du système

**Constat**
Le draft modélise 3 agents (Claude / ChatGPT / Codex) + Humain. Réalité actuelle :

- 7 sous-agents Claude spécialisés (`security-reviewer`, `test-writer`, `k8s-ops`, `docs-writer`, `content-reviewer`, `verify-app`, `competitive-analyst`)
- Codex utilisé en `run_in_background` comme exécutant async (pattern Decision Gate #7 lui-même)
- `/pr-guardian` skill = advisory three-axis review, **jamais bloquant**
- Workflows hybrides (Claude audit + Claude exec via subagent + Codex async + GPT challenge)

**Impact**
La règle Section 4 *"Aucun agent ne doit être à la fois auteur, reviewer, décideur"* interdit le modus operandi actuel sans plan de transition. À scoper aux changements **critiques** explicitement.

**Modèle affiné proposé** (5 catégories au lieu de 3 rôles figés) :

| Catégorie | Source | Responsibility | Boundaries |
|-----------|--------|----------------|------------|
| **Internal Council** | Claude personas (8 — HEG-PAT-003) | Architecture, security, governance, robustness | Convergent robustness ; PAS le challenger |
| **External Challenger** | GPT-5 / Codex / non-Claude LLM | Simplicity, ROI, reframing, bullshit detector | Divergent reframe ; jamais persona-fed |
| **Execution Agents** | Codex (run_in_background), Claude implémentation | Implementation, refactor, multi-fichiers, scripts | Une PR logique à la fois ; jamais "tout le plan" |
| **Advisory Agents** | Sub-agents (security-reviewer, test-writer, k8s-ops…), `/pr-guardian` | Review spécialisé, audit ciblé, recommandations | Advisory only ; jamais bloquant ; jamais décideur |
| **Human Decision Owner** | Christophe / mainteneur | Merge, release, risk acceptance, signal public | Décisions irréversibles + exposition publique |

Cette taxonomie remplace le triplet Claude/ChatGPT/Codex du draft Section 3.

**Options**
- **a)** Adopter le modèle 5 catégories (recommandé).
- **b)** Garder le triplet du draft → contredit `.claude/agents/` existant (rejeté).
- **c)** Rédiger un mapping de transition (modèle 5 cat. avec note "consolide les sous-agents et patterns émergents").

---

## Reconciliation matrix

> À remplir après verdict challenger. Pour chaque doc impacté : action explicite (COMPLEMENTS / SUPERSEDES / REPLACES / ALIGNS WITH) + rationale 1 ligne.

| Doc | Section | Action proposée | Rationale |
|-----|---------|-----------------|-----------|
| `stoa-docs/HEGEMON/DECISION_GATE.md` | Cognitive Roles (l.21-24) | ALIGNS WITH | Playbook reprend la sémantique Council interne / Challenger externe sans la modifier |
| `stoa-docs/HEGEMON/DECISION_GATE.md` | Trigger (l.7-15) | COMPLEMENTS | Playbook §10 = exemples non-normatifs sous (b)/(c), pas remplacement |
| `stoa-docs/docs/architecture/adr/adr-061-council-multi-stage-review.md` | Tout | ALIGNS WITH | Playbook réfère explicitement au 8-personas, ne le redéfinit pas |
| `stoa-docs/docs/governance/review-loop.md` | Tout | COMPLEMENTS | Playbook ajoute la chaîne Audit→Council→Plan→Execute→Review au-dessus du review-loop |
| `stoa/CLAUDE.md:168` ("PR > 300 LOC interdit") | Règle PR | ALIGNS WITH (option a) **ou** SUPERSEDES via ADR-067 (option b) | Décision tension #2 |
| `stoa/.claude/docs/git-workflow.md:226` | LOC limit | ALIGNS WITH | Identique à CLAUDE.md |
| `stoa/.claude/docs/phase-ownership.md:120` | Stripe micro-PR | ALIGNS WITH | Identique |
| `stoa/.claude/docs/ai-factory.md:97-108` | Sub-agents | COMPLEMENTS | Playbook nomme la catégorie "Advisory Agents" qui couvre les sub-agents existants |
| `stoa/.claude/skills/decompose/SKILL.md` | Calibration LOC | ALIGNS WITH | Skill reste calibré 100-300 LOC |
| `stoa/.claude/agents/*` (7 sub-agents) | Tout | COMPLEMENTS | Playbook les classe sous "Advisory Agents" sans modifier leur définition |
| `stoa/docs/plans/_template.md` | Frontmatter triggers | ALIGNS WITH | Playbook valide le workflow plan-validation existant |

---

## Decision Gate #11 — Challenger prompt

À envoyer à GPT-5 (Codex en background ou ChatGPT direct), **sans personas, sans rubric Council**.

```
Plan: AI Factory Governance Alignment (STOA).
Source: stoa/docs/plans/2026-05-07-ai-factory-governance.md (annexe A = draft original).

Context (3 bullets):
- STOA a déjà une doctrine de gouvernance canonisée (HEGEMON/DECISION_GATE.md,
  ADR-061 council-multi-stage-review, docs/governance/review-loop.md).
- Un draft de playbook a été proposé qui collide sur 4 points (sémantique
  Council/Challenger inversée, règle PR 300 LOC, expansion triggers DG, rigidité
  des rôles vs 7 sous-agents existants).
- Le plan propose d'écrire le playbook en alignant sur la doctrine canon, avec un
  modèle 5 catégories (Internal Council / External Challenger / Execution Agents /
  Advisory Agents / Human Decision Owner).

You are NOT a persona and NOT a consultant. You are a non-aligned challenger.
Challenge the FRAMING, not the execution. Return:

1. Is the problem correctly formulated? (Le problème est-il "aligner ce draft
   sur le canon" ou "le canon mérite-t-il d'être révisé à la lumière du draft" ?)
2. Which biases or assumptions are baked in? (Notamment : le 8-personas Council
   est-il vraiment plus utile que le triplet Claude/GPT/Codex pour piloter la
   gouvernance ? Le gel `DECISION_GATE.md` est-il une discipline ou une rigidité ?)
3. Where is this over-engineered? What would a 20% version achieve? (Une simple
   note dans CLAUDE.md ferait-elle le job ?)
4. What missing context would break this plan? (Y a-t-il un signal externe —
   audit OSS, PR Guardian feedback, incident — qui devrait rouvrir la doctrine
   canon plutôt que la protéger ?)

Refuse to score. Prose only.
```

---

## Open questions for challenger

1. Le draft est-il **un playbook de rôles** ou **une charte de séparation des pouvoirs** ? Les deux framings impliquent des placements différents.
2. La règle "Aucun agent ne doit être à la fois auteur, reviewer, décideur" est-elle un principe absolu ou conditionnel à la criticité ? Si conditionnel, quel seuil ?
3. Le modèle 5 catégories (Council / Challenger / Execution / Advisory / Human) capture-t-il bien la réalité, ou faut-il une 6e catégorie (ex : "Continuous Monitoring" pour `verify-app`, `monitor-cd`) ?
4. Le placement final doit-il être HEGEMON (interne, doctrine vivante), ADR-067 (binding, daté), ou `docs/governance/` (public-facing, pédagogique) ?
5. Le gel discipline de `DECISION_GATE.md` doit-il être maintenu strictement ou peut-on faire une exception pour "append-only" (ajouter section "Examples" sans modifier les triggers) ?

---

## Annexe A — Draft original (verbatim, 2026-05-07)

> Reproduit ici pour traçabilité. Toute future référence au playbook doit pointer vers la version réconciliée post-Decision Gate, pas vers cette annexe.

### A.1 Philosophy

STOA est un projet complexe : monorepo multi-langages, CI/CD transverse, gouvernance GitOps, release engineering, sécurité, observabilité, exposition publique OSS.

Aucun agent IA unique ne doit être responsable à lui seul du diagnostic, de la décision, de l'implémentation, et de la validation. Le système doit fonctionner comme une chaîne de responsabilité.

**Principe central** : Le bon agent au bon moment.

### A.2 Canonical Pattern

```
1. Audit → 2. Council/Arbitrage → 3. Canonical Plan → 4. Controlled Execution → 5. Independent Review → 6. Human Decision
```

### A.3 Official Agent Roles (draft original — à réconcilier)

- **Claude Code** — Auditor / Architect / Challenger : audit read-only, analyse architecture, diagnostic transversal, review PR, rédaction ADR/plans.
- **ChatGPT** — Council / Arbitrage / Doctrine : challenger externe, council de décision, arbitre process. *(NOTE : terminologie inversée vs canon STOA — voir Tension #1.)*
- **Codex** — Executor / Integrator : exécution technique, refactors, CI/CD, workflows GH Actions.
- **Human** — Decision Owner : merges, releases, signal public, risque accepté.

### A.4 Critical Governance Rule

> Aucun agent ne doit être à la fois auteur du changement, reviewer du changement, et décideur du merge.

Pour les changements critiques :
```
Claude → audit
ChatGPT → arbitrage  (NOTE : à remplacer par "Internal Council Claude personas + External Challenger GPT" — Tension #1/#4)
Codex → implémentation
Claude → review
Human → merge
```

### A.5 Canonical Workflow Example — Release Governance Refactor

Step 1 (Audit) → Step 2 (Council) → Step 3 (Canonical Plan dans `docs/plans/`) → Step 4 (Controlled Execution PR par PR) → Step 5 (Independent Review : ACCEPT / ACCEPT WITH NITS / REQUEST CHANGES) → Step 6 (Human Merge).

### A.6 PR Doctrine (draft — Tension #2)

Ancienne règle : *PR >300 LOC interdit*.
Nouvelle doctrine proposée : *Review slice ≤300 LOC. PR globale autorisée si architecture cohérente, commits structurés, validations explicites, rollback clair, scope maîtrisé.*

### A.7 Governance Levels

- **L1 Internal Integration** — vélocité, commits fréquents, branches MEGA. Pas de releases publiques auto.
- **L2 Public Review** — PR cohérente, narrative claire, acceptance.
- **L3 Product Release** — release curée, changelog éditorialisé, migration notes.

### A.8 Release Governance Principles

> Le repo public ne doit pas refléter l'intensité du chantier. Il doit refléter la maturité du produit.

Public releases : intentionnelles, curées, lisibles, démontrables.
Internal cadence : peut rester élevée. Mais commits ≠ releases, PRs ≠ produit.
Pre-1.0 discipline : `-alpha`, `-beta`, `-rc` obligatoires.

### A.9 Recommended Repository Structure

```
HEGEMON/
  AI_FACTORY_AGENT_ROLES.md
  DECISION_GATE.md
docs/plans/
docs/audits/
docs/adr/
```

### A.10 Decision Gate Triggers (draft — Tension #3)

Les sujets suivants déclenchent automatiquement un Decision Gate : sécurité, release engineering, gouvernance Git, versioning, suppression historique, exposition publique, breaking changes, architecture transverse, workflows CI/CD critiques.

### A.11 Anti-Patterns

- ❌ "Codex, applique tout le plan" (trop risqué).
- ❌ Audit + implémentation par le même agent sans review indépendante.
- ❌ Releases publiques automatiques sur chaque merge main.
- ❌ PR artificiellement micro-découpées sans cohérence fonctionnelle.

### A.12 Final Principle

> L'objectif de l'AI Factory n'est pas seulement de produire du code. L'objectif est de produire des décisions traçables, challengeables, réversibles, et cohérentes avec la maturité réelle du produit.

---

## Reopen conditions (si NO-GO post-Decision Gate)

- Évolution majeure du fonctionnement multi-agents (ex : ajout d'un orchestrateur tiers, refonte des sub-agents).
- Incident de gouvernance documenté (un changement critique passé sans review indépendante).
- Demande explicite d'un mainteneur OSS externe (signal communauté).
- Fin du gel `DECISION_GATE.md` (~2026-05-22) si la doctrine canon évolue.
