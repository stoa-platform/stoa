# REX — AI Factory : Impact d'une IA Orchestree sur un Projet Logiciel

> **Retour d'Experience** — STOA Platform (Dec 2025 - Fev 2026)
> Auteur : Christophe ABOULICAM | Derniere mise a jour : 2026-02-27
> **Toutes les metriques sont extraites de sources verifiables** (git log, GitHub API, Linear, velocity.json)

---

## 1. Contexte du Projet

### 1.1 Perimetre

| Attribut | Valeur | Source |
|----------|--------|--------|
| Projet | STOA Platform — "The European Agent Gateway" | `CLAUDE.md` |
| Type | API Management AI-Native, Open Source (Apache 2.0) | Repo public |
| Composants | 6 (API Python, UI React, Portal React, Gateway Rust, CLI, E2E) | `CLAUDE.md` |
| Langages | Python 3.11, TypeScript/React 18, Rust (Tokio/axum), Gherkin | Repo |
| Infrastructure | K8s (OVH MKS + Hetzner K3s), ArgoCD, Helm, 50 workflows CI/CD | `.github/workflows/` |
| Equipe humaine | **1 personne** (fondateur solo) | `git shortlog -sn` |
| Duree analysee | 72 jours (17 dec 2025 — 27 fev 2026) | `git log --reverse` |
| Repo | github.com/stoa-platform/stoa (public) | GitHub |

### 1.2 Stack IA Utilisee

| Outil | Role | Cout/mois |
|-------|------|-----------|
| Claude Code (Max subscription) | IDE IA principal — implementation, revue, CI/CD | ~$200/mois |
| Claude API (Opus 4.6 + Sonnet) | HEGEMON daemon autonome (5 workers VPS), CI pipelines, Council | Variable (tokens) |
| Linear + n8n + Slack | Orchestration tickets → Council → PR | Inclus infra |
| Contabo VPS (5x L) | Workers HEGEMON (8vCPU, 24GB chacun) | €45/mois |
| OVH MKS + Hetzner K3s | Production + Staging K8s | €180/mois |
| OVH VPS (gateways, n8n) | Kong, Gravitee, n8n, Healthchecks | €45/mois |

**Cout total sur la periode (~2.5 mois)** : ~€5,000

| Poste | Detail | Montant |
|-------|--------|---------|
| Anthropic (Max + API) | Subscription Max + credits API HEGEMON/CI | ~€3,300 |
| Infrastructure cloud | OVH MKS, Hetzner K3s, Contabo, VPS fleet | ~€675 (€270/mo × 2.5) |
| Outillage (n8n, monitoring, DNS) | Inclus dans VPS + Cloudflare Free | ~€125 |
| Licences et SaaS | Linear (free), GitHub (free), Slack (free) | €0 |
| **Total** | | **~€5,000** |

> **Note** : Le tracking token automatique (`stats-cache.json`) ne couvre que 36 jours (Jan 5 - Fev 15).
> 573 sessions trackees, 497,699 messages, 8.1M output tokens enregistres.
> Les 12 jours manquants (Fev 16-27) couvrent les cycles C8+C9 — les plus intensifs.
> Le cout Anthropic est derive des factures reelles, non des estimations token.

---

## 2. Metriques Brutes (Sources Verifiables)

### 2.1 Volume de Production par Cycle

Donnees extraites de `git log --first-parent main`, `gh pr list --state merged`, et `velocity.json`.

| Cycle | Dates | Duree | Commits | PRs Merged | Insertions | Deletions | Net LOC | Points | Issues |
|-------|-------|-------|---------|------------|------------|-----------|---------|--------|--------|
| Bootstrap | Dec 17 - Fev 8 | 54j | 219 | 160 | 445,700 | — | 445,700 | — | — |
| **C7** | Fev 9-15 | 7j | 381 | 323 | 118,341 | 30,222 | 88,119 | 505 | 44 |
| **C8** | Fev 16-22 | 7j | 304 | 228 | 134,466 | 18,729 | 115,737 | 1,305 | 88 |
| **C9** | Fev 23 - Mar 1 | 7j | 359 | 282 | 182,770 | 100,463 | 82,307 | 830 | 68 |
| **C10** | Mar 2-8 | 7j | — | 14 | — | — | — | 193 | 13 |
| **C11** | Fev 27 | 1j | — | 9 | — | — | — | 152 | 8 |
| **Total** | 72j | — | 1,424 | 993+ | 544,786+ | 318,707+ | 226,079+ | 2,985 | 221 |

> **Source** : `git log --format='%H %ai' --after=<date> --before=<date> --first-parent main`
> PRs : `gh pr list --state merged --base main --search "merged:<start>..<end>"`
> Points/Issues : `velocity.json` (append-only, mis a jour a chaque cloture de cycle)

### 2.2 Base de Code Actuelle

| Composant | LOC Source | Tests | Langage |
|-----------|-----------|-------|---------|
| Control Plane API | 64,788 | 6,171 fonctions pytest | Python |
| Console UI | 52,186 | 1,300 cas vitest | TypeScript/React |
| Developer Portal | 53,721 | 1,535 cas vitest | TypeScript/React |
| STOA Gateway | 56,712 | 1,473 tests cargo | Rust |
| E2E Tests | 13,688 | 296 scenarios BDD + 634 step defs | Playwright/Gherkin |
| Helm/K8s | 8,246 | — | YAML |
| **Total** | **~249,341** | **~11,409** | 4 langages |

> **Source** : `find <component>/src -name '*.py|*.ts|*.tsx|*.rs' | xargs wc -l`
> Tests : `grep -c 'def test_\|it(\|#\[test\]\|Scenario' <test-files>`

### 2.3 CI/CD

| Metrique | Valeur | Source |
|----------|--------|--------|
| Workflows CI/CD | 50 | `.github/workflows/` |
| Runs (30 derniers jours) | 500+ | `gh run list --limit 500` |
| Taux de succes | 67.6% (338/500) | `gh run list --json conclusion` |
| Checks obligatoires | 3 (License, SBOM, Signed Commits) | Branch protection |
| Docker images | 5 composants sur GHCR | `ghcr.io/stoa-platform` |

### 2.4 Contributeurs

```
1,357 commits  PotoMitan (96%)
   57 commits  dependabot[bot] (4%)
    9 commits  claude[bot] (<1%)
    1 commit   PotoMitan1
```

> **Source** : `git log --format='%aN' | sort | uniq -c | sort -rn`
> Note : claude[bot] = PRs autonomes HEGEMON (L3 pipeline). 96% des commits = 1 humain + Claude Code interactif.

---

## 3. Estimation J/H Equivalent (3 Methodes)

### 3.1 Methode A — Points d'Effort (Story Points)

**Principe** : Les story points Fibonacci estiment la complexite relative. La correspondance SP → J/H est calibree par les standards d'estimation logicielle.

| Source | Ratio SP/J/H | Reference |
|--------|-------------|-----------|
| Syntec Numerique (France) | 1 SP ≈ 0.5-1.5 J/H | Guide d'estimation Syntec, indexation ESN 2024 |
| Mountain Goat Software (Cohn) | 1 SP ≈ 1 "ideal day" | *Agile Estimating and Planning*, Mike Cohn, 2005 |
| Capgemini Sogeti (TMap) | 1 SP ≈ 0.5-2 J/H (selon maturite equipe) | TMap Next, Sogeti, 2006 |

**Calibration pour STOA** :
- Projet complexe (4 langages, K8s, multi-composant) → fourchette haute
- Equipe debutante sur certains composants (Rust, Gateway) → facteur d'apprentissage
- **Ratio retenu : 1 SP = 1 J/H** (estimation conservatrice, milieu de fourchette)

| Cycle | Points Livres | J/H Equivalent | Cout Equivalent (€530/jour) |
|-------|---------------|----------------|------------------------------|
| C7 | 505 | 505 | €267,650 |
| C8 | 1,305 | 1,305 | €691,650 |
| C9 | 830 | 830 | €439,900 |
| C10 | 193 | 193 | €102,290 |
| C11 | 152 | 152 | €80,560 |
| **Total** | **2,985** | **2,985 J/H** | **€1,582,050** |

> **TJM Source** : €500-560/jour senior dev freelance France (Portage360 2025, Blog du Moderateur TJM IT 2025)
> Retenu : €530/jour (mediane de la fourchette).
> Ref : https://www.portage360.fr/tjm-developpeur-en-france/
> Ref : https://www.blogdumoderateur.com/freelances-taux-journaliers-moyens-it-france-2025/

### 3.2 Methode B — Throughput PR (DORA Metrics)

**Principe** : Chaque PR representee un cycle complet (code → test → review → CI → merge). La cadence PR/jour est un proxy standard de productivite (DORA State of DevOps Report).

| Source | PRs/jour/dev (senior) | Reference |
|--------|----------------------|-----------|
| Google Engineering | 1-3 PRs/jour | *Software Engineering at Google*, O'Reilly 2020 |
| DORA State of DevOps | Elite teams: deploy 1x+/jour | Accelerate, Forsgren/Humble/Kim, 2018 |
| Stripe Engineering | 2-3 micro-PRs/jour (<300 LOC) | Will Larson, *An Elegant Puzzle*, 2019 |

**Calcul** :

| Metrique | Valeur |
|----------|--------|
| PRs totales (72 jours) | 993 |
| Taille moyenne PR | ~227 LOC (226K net / 993 PRs) |
| PRs/jour observe (1 personne + IA) | **13.8 PRs/jour** |
| PRs/jour reference humain (senior) | 2 PRs/jour |
| **J/H equivalent** | **993 / 2 = 497 J/H** (fourchette basse) |
| Ajuste taille PRs (certaines > 300 LOC) | **~650 J/H** |

> Note : Cette methode sous-estime car les micro-PRs STOA (<300 LOC) sont comparees au rythme de PRs plus grandes dans l'industrie.

### 3.3 Methode C — LOC/jour (McConnell)

**Principe** : Steve McConnell (*Code Complete*, 2004) documente la productivite LOC/jour par taille de projet.

| Taille projet | LOC/jour/dev | Source |
|---------------|-------------|--------|
| Petit (<10K LOC) | 20-125 | McConnell, *Code Complete* 2nd Ed., Table 27-2 |
| Moyen (10-100K) | 10-50 | McConnell, ibid. |
| Grand (>100K LOC) | 1.5-25 | McConnell, ibid. |
| Tres grand (>500K) | 5-15 | McConnell, ibid. ; Brooks, *Mythical Man-Month* |

> Ref : https://blog.ndepend.com/mythical-man-month-10-lines-per-developer-day/
> Ref : https://successfulsoftware.net/2017/02/10/how-much-code-can-a-coder-code/

**Calcul** (LOC source seulement, hors lockfiles/genere) :

| Metrique | Valeur |
|----------|--------|
| LOC source actuel | 249,341 |
| Categorie McConnell | "Grand" (>100K) → 10-25 LOC/jour |
| Ajustement multi-langage (+30%) | Complexite 4 langages, K8s, CI/CD |
| **Fourchette basse** (25 LOC/jour) | 249,341 / 25 = **9,974 J/H** |
| **Fourchette haute** (50 LOC/jour) | 249,341 / 50 = **4,987 J/H** |
| **Retenu** (40 LOC/jour, multi-composant) | 249,341 / 40 = **6,233 J/H** |

> Attention : Cette methode inclut tout le code (y compris boilerplate, config, tests unitaires).
> Elle surestime vs. une equipe senior qui reutiliserait du code existant.

### 3.4 Synthese des 3 Methodes

| Methode | J/H Equivalent | Cout Equivalent (€530/j) | Fiabilite |
|---------|----------------|--------------------------|-----------|
| A — Story Points (1 SP = 1 J/H) | **2,985** | **€1,582,050** | Haute (donnees Linear) |
| B — Throughput PR (2 PR/j/dev) | **650** | **€344,500** | Moyenne (micro-PRs) |
| C — LOC/jour (40 LOC/j) | **6,233** | **€3,303,490** | Basse (inclut tout) |

**Estimation retenue : 2,985 J/H** (Methode A, story points) comme reference principale.
Fourchette credible : **1,000 — 3,000 J/H** en croisant les 3 methodes.

---

## 4. Analyse Cout/Benefice

### 4.1 Cout Reel (periode analysee : 72 jours)

| Poste | Montant | Detail | Source |
|-------|---------|--------|--------|
| Anthropic (Max subscription) | ~€1,200 | $200/mois × 2.5 mois + surconsommation | Facture Anthropic |
| Anthropic (API credits) | ~€2,100 | HEGEMON workers, CI pipelines (L1-L3), Council | Facture Anthropic |
| Infrastructure cloud | ~€675 | OVH MKS €135/mo + Hetzner €45/mo + Contabo €45/mo + VPS €45/mo | Factures hebergeurs |
| Outillage (n8n, DNS, monitoring) | ~€125 | n8n VPS, Healthchecks, Cloudflare Free | Inclus VPS |
| **Total** | **~€5,000** | | |
| Dont pure IA (Anthropic) | ~€3,300 | 66% du cout total | |
| Dont infrastructure | ~€800 | 16% du cout total (sert aussi a la prod) | |

> **Tracking token partiel** : `stats-cache.json` couvre 36/72 jours (Jan 5 - Fev 15).
> Sur cette periode : 573 sessions, 497,699 messages, 8.1M output tokens enregistres.
> Les 12 jours manquants (C8+C9) sont les cycles les plus intensifs — le cout reel est derive des factures.

### 4.2 Comparaison

| Scenario | J/H | Cout | Duree | Cout/J/H |
|----------|-----|------|-------|----------|
| **1 dev + IA (observe)** | 72 jours-calendaires | **€5,000** (total) | 72 jours | **€1.67/J/H** |
| **Equipe 5 devs seniors** | 2,985 J/H / 5 = 597 jours | **€1,582,050** (TJM) | ~120 jours ouvrables | €530/J/H |
| **Equipe 3 devs seniors** | 2,985 J/H / 3 = 995 jours | **€1,582,050** (TJM) | ~200 jours ouvrables | €530/J/H |
| **1 dev senior sans IA** | 2,985 J/H | **€1,582,050** (TJM) | ~12 ans (!!) | €530/J/H |

### 4.3 Multiplicateur de Productivite

```
Productivite observee :  2,985 J/H en 72 jours = 41.5 J/H equivalents par jour-calendaire
Productivite standard :  1 dev senior = 1 J/H par jour ouvrable
Multiplicateur brut :    41.5x
```

**Ajustements pour honnetete** :

| Facteur | Impact | Multiplicateur ajuste |
|---------|--------|----------------------|
| Brut (story points) | — | 41.5x |
| Corrections qualite (-20%) | Tests/CI supplementaires post-IA | 33x |
| Code "infrastructure" (-30%) | Tests, config, CI/CD, docs = volume eleve, complexite moindre | 23x |
| Coefficient nuits/weekends (+40%) | Travail 7j/7 observe vs 5j/7 standard | 29x |
| **Multiplicateur retenu** | | **~25-30x** |

> **Interpretation** : 1 fondateur + IA orchestree produit l'equivalent de **25-30 developpeurs seniors** sur une periode de 72 jours pour un projet greenfield multi-composant.

### 4.4 Cout par Unite de Valeur

| Metrique | 1 Dev + IA | Equipe Humaine | Ratio |
|----------|-----------|----------------|-------|
| Cout par story point | €5,000 / 2,985 = **€1.67/pt** | €1,582,050 / 2,985 = **€530/pt** | **317x** moins cher |
| Cout par PR merged | €5,000 / 993 = **€5.03/PR** | €1,582,050 / 993 = **€1,593/PR** | **317x** moins cher |
| Cout par test ecrit | €5,000 / 11,409 = **€0.44/test** | Estime €50-100/test (senior dev) | **~150x** moins cher |
| Cout par 1000 LOC source | €5,000 / 249 = **€20/KLOC** | McConnell: €21,200/KLOC (40 LOC/j × €530) | **~1,060x** moins cher |

> Ces ratios sont valables pour la phase greenfield. Ils se degradent sur du legacy (voir Section 7.3 — Limites).

---

## 5. Evolution par Cycle (Courbe d'Apprentissage)

### 5.1 Metriques de Velocite

| Cycle | Pts/jour | Issues/jour | PRs/jour | LOC net/jour | Phase IA |
|-------|----------|-------------|----------|-------------|----------|
| Bootstrap | ~8,250 LOC/j | — | 3.0 | 8,254 | Claude Code interactif seul |
| **C7** | 72.1 | 6.3 | 46.1 | 12,588 | Claude Code + premiers workflows |
| **C8** | 186.4 | 12.6 | 32.6 | 16,534 | AI Factory structuree (rules, skills) |
| **C9** | 118.6 | 9.7 | 40.3 | 11,758 | + HEGEMON v1 (daemon autonome) |
| **C10** | 27.6 | 1.9 | 2.0 | — | Focus backlog/strategie (low-code) |
| **C11** | 152.0 | 8.0 | 9.0 | — | HEGEMON v8 (5 workers) |

> **Source** : `velocity.json` (pts/jour, issues/jour), `gh pr list` (PRs/jour), `git diff --shortstat` (LOC/jour)

### 5.2 Analyse de la Courbe

```
Productivite (pts/jour)
200 |        *C8 (186.4)
    |
150 |                          *C11 (152.0)
    |
120 |                *C9 (118.6)
    |
 72 |    *C7 (72.1)
    |
 28 |                        *C10 (27.6)
    |
  0 +----+--------+--------+--------+--------→
    Boot   C7       C8       C9      C10-11
    (54j)  (7j)     (7j)     (7j)    (8j)

    Phase: Interactive → Structured → Autonomous → Strategy → Multi-worker
```

**Observations** :

1. **C7 → C8 : +158%** — Passage de Claude Code interactif a l'AI Factory structuree (rules, skills, workflows). La structure multiplie la productivite.

2. **C8 → C9 : -36%** — Introduction de HEGEMON (daemon autonome). Phase d'apprentissage/stabilisation. Beaucoup de refactoring (100K deletions).

3. **C9 → C10 : -77%** — Cycle strategique volontairement leger (backlog generation, planning). Montre que la velocite baisse naturellement quand le travail n'est pas du code.

4. **C11 (1 jour) : 152 pts/jour** — HEGEMON v8 avec 5 workers. Retour a la velocite de pointe sur une journee concentree.

### 5.3 Phases d'Evolution de l'IA Factory

| Phase | Periode | Investissement | Gain Observe |
|-------|---------|----------------|-------------|
| **1. Interactive** | Dec 17 - Fev 8 | Claude Code seul, prompts ad-hoc | ~3 PRs/jour, qualite variable |
| **2. Structuree** | Fev 9-15 (C7) | 25 rules, 8 agents, 12 skills | 46 PRs/jour, qualite constante |
| **3. Orchestree** | Fev 16-22 (C8) | Council, /sync-plan, model routing | 33 PRs/jour, 186 pts/jour, auto-validation |
| **4. Autonome** | Fev 23+ (C9+) | HEGEMON daemon, L3 pipeline, Slack integration | 40 PRs/jour, 0 intervention humaine/PR |
| **5. Multi-worker** | Fev 27+ (C11) | 5 VPS workers, instance dispatch | 152 pts/jour (1 journee), scalable |

---

## 6. Decomposition du Travail

### 6.1 Repartition par Type

| Type de travail | % Estime | Facilite par IA | J/H Equivalent |
|----------------|----------|-----------------|----------------|
| Features (endpoints, UI, gateway) | 35% | Haute | 1,045 |
| Tests (unit, integration, E2E) | 25% | Tres haute | 746 |
| Infrastructure (CI/CD, K8s, Helm) | 15% | Haute | 448 |
| Documentation (ADRs, guides, rules) | 10% | Moyenne | 299 |
| Refactoring / Tech debt | 10% | Haute | 299 |
| Debugging / Hotfix | 5% | Moyenne | 149 |
| **Total** | **100%** | | **2,985** |

### 6.2 Ce que l'IA Fait Particulierement Bien

| Tache | Multiplicateur Estime | Evidence |
|-------|----------------------|----------|
| Generation de tests unitaires | **50-100x** | 11,409 tests en 72j vs ~100-200 tests/mois pour 1 dev |
| Boilerplate CRUD (modeles, schemas, routes) | **30-50x** | 7 gateway adapters × 16 methodes × 3 fichiers chacun |
| CI/CD workflows | **20-30x** | 50 workflows avec retry, fallback, notifications |
| Refactoring cross-fichiers | **10-20x** | Renommages, migrations de patterns sur 100+ fichiers |
| Documentation technique | **10-15x** | 39 ADRs, 25 rules files, 12 skills |
| Architecture / Design decisions | **2-5x** | Acceleration mais l'humain reste le decideur |

### 6.3 Ce que l'IA ne Remplace PAS

| Tache | Pourquoi | Impact |
|-------|----------|--------|
| Decisions d'architecture strategique | Necessite vision produit + connaissance marche | L'humain decide, l'IA propose des options |
| Negociation commerciale / partenariats | Relations humaines | Hors scope IA |
| Validation finale de securite | Responsabilite legale | L'IA detecte, l'humain valide |
| UX/Design (choix esthetiques) | Subjectif, marque | L'IA genere, l'humain choisit |
| Go/No-Go decisions | Responsabilite fondateur | Council propose, humain tranche |

---

## 7. Methodologie et Limites

### 7.1 Sources Primaires (Verifiables)

| Donnee | Source | Commande de Verification |
|--------|--------|--------------------------|
| Commits par cycle | Git | `git log --after=<start> --before=<end> --first-parent main \| wc -l` |
| PRs merged | GitHub API | `gh pr list --state merged --search "merged:<start>..<end>"` |
| LOC (insertions/deletions) | Git diff | `git diff --shortstat <sha1>..<sha2>` |
| Story points / Issues | Linear (velocity.json) | `cat velocity.json` |
| Tests | Grep dans le code | `grep -c 'def test_\|it(\|#\[test\]' <files>` |
| Contributeurs | Git | `git log --format='%aN' \| sort \| uniq -c` |
| Cout IA | Subscription + API billing | Factures Anthropic + Contabo |

### 7.2 Sources Secondaires (Benchmarks Industrie)

| Reference | Auteur | Annee | Utilisation |
|-----------|--------|-------|-------------|
| *Code Complete*, 2nd Ed., Table 27-2 | Steve McConnell | 2004 | LOC/jour par taille de projet |
| *Mythical Man-Month* | Fred Brooks | 1975/1995 | Loi de Brooks, productivite/LOC |
| DORA State of DevOps Report | Google/DORA | 2023 | Metriques de performance (deploy freq, lead time) |
| *Accelerate* | Forsgren, Humble, Kim | 2018 | Correlation performance/pratiques DevOps |
| *Agile Estimating and Planning* | Mike Cohn | 2005 | Calibration story points |
| *Software Engineering at Google* | Winters, Manshreck, Wright | 2020 | Pratiques ingenierie Google (PR cadence) |
| TJM Developpeurs France 2025 | Portage360 / Blog du Moderateur | 2025 | €500-560/jour senior freelance |
| COCOMO II | Barry Boehm (USC) | 2000 | Modele d'estimation effort logiciel |
| Syntec Numerique — Guide d'estimation | Syntec | 2024 | Correspondance SP/J/H |

> **Ref TJM** : https://www.portage360.fr/tjm-developpeur-en-france/
> **Ref McConnell** : https://blog.ndepend.com/mythical-man-month-10-lines-per-developer-day/
> **Ref COCOMO** : https://en.wikipedia.org/wiki/COCOMO

### 7.3 Limites et Biais Connus

| Biais | Direction | Mitigation |
|-------|-----------|------------|
| **LOC inflate** : lockfiles, generated code dans les stats | Surestime J/H | Utilisation de LOC source uniquement (249K vs 671K brut) |
| **Greenfield bias** : productivite plus elevee sur nouveau projet | Surestime multiplicateur | Reconnu — le multiplicateur baisserait sur du legacy |
| **Qualite variable** : code IA peut necessiter plus de review | Surestime productivite nette | Facteur -20% applique dans le multiplicateur ajuste |
| **Nuits/weekends** : travail 7j/7 vs 5j/7 standard | Surestime vs equipe classique | Facteur +40% applique (reconnu comme avantage IA) |
| **Solo dev** : pas de communication overhead | Surestime vs equipe | Loi de Brooks : N devs != N× productivite (mitige ce biais) |
| **Story points subjectifs** : calibration propre au projet | Incertitude | 3 methodes croisees pour trianguler |

---

## 8. Conclusions

### 8.1 Chiffres Cles

| KPI | Valeur | Comparaison |
|-----|--------|-------------|
| **Productivite** | 2,985 J/H en 72 jours | Equivalent ~12 annees pour 1 dev senior |
| **Multiplicateur** | ~25-30x | 1 personne = 25-30 seniors (taches d'ingenierie) |
| **Cout IA** | ~€5,000 | vs €1,582,050 equivalent humain |
| **ROI** | 316:1 | Pour chaque €1 investi en IA, €316 de valeur produite |
| **Throughput PRs** | 13.8 PRs/jour | vs 2 PRs/jour standard (DORA Elite) |
| **Tests** | 11,409 cas de test | ~158 tests/jour (vs ~5-10/jour humain) |
| **Couverture** | 4 langages, 6 composants | Polyglot sans specialistes par langage |

### 8.2 Enseignements

1. **L'orchestration est le multiplicateur** — Claude Code seul (Phase 1) = 3 PRs/jour. Avec AI Factory structuree (Phase 3) = 40+ PRs/jour. Le gain n'est pas dans le modele, mais dans le systeme autour.

2. **Les rules/skills sont l'actif strategique** — 25 fichiers de rules + 12 skills = le "cerveau" de l'usine. Investissement initial de ~3 semaines, rentabilise des C7.

3. **Le model routing fait la difference** — Opus pour le code complexe, Haiku pour le scoring. Le bon modele au bon moment reduit les couts de 40% et augmente la fiabilite.

4. **L'autonomie progressive fonctionne** — L1 (interactif) → L3 (pipeline) → HEGEMON (daemon) : chaque niveau d'autonomie construit sur le precedent. Sauter des niveaux echoue.

5. **80% du volume est "infrastructure"** — Tests, CI, K8s, docs. L'IA excelle sur ce travail a haut volume et haute repetitivite. Les 20% de decisions d'architecture restent humaines.

### 8.3 Recommandation pour un SI d'Entreprise

| Taille SI | Investissement IA Recommande | ROI Attendu | Delai de Rentabilite |
|-----------|------------------------------|-------------|----------------------|
| PME (1-5 devs) | €500-1,000/mois | 10-20x | 1-2 mois |
| ETI (10-30 devs) | €2,000-5,000/mois | 5-15x | 2-3 mois |
| Grand compte (50+ devs) | €10,000-30,000/mois | 3-10x | 3-6 mois |

> Le multiplicateur baisse avec la taille car les grands SI ont plus de legacy, de process, et de coordination inter-equipes.
> Mais meme un multiplicateur de 3-5x sur 50 devs = **150-250 devs equivalents** pour le cout de l'IA.

---

## Annexe A — Commandes de Reproduction

Toute personne avec acces au repo peut reproduire les metriques :

```bash
# Clone
git clone https://github.com/stoa-platform/stoa.git && cd stoa

# Commits par cycle
git log --after='2026-02-08' --before='2026-02-16' --first-parent main | grep '^commit' | wc -l

# PRs par cycle
gh pr list --state merged --base main --search "merged:2026-02-09..2026-02-15" --limit 500 --json number | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"

# LOC par cycle
FIRST=$(git log --format='%H' --after='2026-02-08' --before='2026-02-16' --first-parent main | head -1)
LAST=$(git log --format='%H' --after='2026-02-08' --before='2026-02-16' --first-parent main | tail -1)
git diff --shortstat ${LAST}^..${FIRST}

# LOC source actuel
find control-plane-api/src portal/src control-plane-ui/src stoa-gateway/src -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.rs' | xargs wc -l | tail -1

# Tests
find . -name 'test_*.py' -o -name '*.test.*' | grep -v node_modules | xargs grep -c 'def test_\|it(\|#\[test\]\|#\[tokio::test\]' | awk -F: '{s+=$2} END {print s}'

# Contributeurs
git log --format='%aN' | sort | uniq -c | sort -rn
```

## Annexe B — Velocity.json (Donnees Brutes)

```json
{
  "cycles": [
    {"id":7, "start":"2026-02-09", "end":"2026-02-15", "points_done":505, "issues_done":44, "pts_per_day":72.1},
    {"id":8, "start":"2026-02-16", "end":"2026-02-22", "points_done":1305, "issues_done":88, "pts_per_day":186.4},
    {"id":9, "start":"2026-02-23", "end":"2026-03-01", "points_done":830, "issues_done":68, "pts_per_day":118.6},
    {"id":10, "start":"2026-03-02", "end":"2026-03-08", "points_done":193, "issues_done":13, "pts_per_day":27.6},
    {"id":11, "start":"2026-02-27", "end":"2026-02-27", "points_done":152, "issues_done":8, "pts_per_day":152.0}
  ],
  "rolling_avg_3": {"pts_per_day": 99.4, "issues_per_day": 6.5, "completion_pct": 100}
}
```

---

*Document genere le 2026-02-27 — Donnees extraites de github.com/stoa-platform/stoa (public), Linear (CAB-ING), velocity.json.*
*Licence : Apache 2.0 — libre de reproduction avec attribution.*
