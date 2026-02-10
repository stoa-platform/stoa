# Plan: Demo Design Partner — Banque Europeenne (24 fev 2026)

> **Last updated:** 2026-02-10 12:00 (mardi midi)
> **Status:** Ready for Phase 1 execution (pending Q1-Q2 responses)
> **Next action:** Answer Q1 (langue) + Q2 (staging) → launch Phase 1 parallel execution
> **Previous plan:** Cycle 7 scoreboard (225 pts / 22 PRs) — archived below

---

## Executive Summary

**Mission:** Preparer presentation 5 min "Design Partner" pour banque europeenne (DSI + architectes senior)
**Deadline critique:** Vendredi 14 fev EOD (2.5 jours restants)
**Livrables urgents:** Email Khalil + Script verbal 5min + Slides presentation
**Strategy:** 3 instances CLI paralleles (Phase 1) → gain 45 min, delivre 3 docs en ~1h
**Cost:** ~$30 total (Phase 1-4), ~$15 pour urgent track
**Dependencies:** Q1 (langue francais/anglais) + Q2 (staging local/cloud) AVANT Phase 1

---

## Comprehension Mission

Preparer une presentation 5 min "Design Partner" pour une banque europeenne (DSI + architectes senior). Ce n'est PAS une vente client, c'est une proposition de co-creation produit. L'audience utilise webMethods (gateway legacy) + Oracle OAM/OIM (IDP rigide), souffre de catalogue Excel et souscription 5-10j. L'objectif: convaincre la banque de devenir Design Partner gratuit (POC 4 semaines + 6-12 mois) en echange de feedback + reference + case study. Livrables: script verbal chrono, 6 slides, email Khalil, staging preview, dry-run 3x.

---

## Livrables Prioritaires

| # | Livrable | Ticket | Deadline | Bloquant? |
|---|----------|--------|----------|-----------|
| 1 | **Script verbal 5min** (chrono, transitions, messages cles) | CAB-1128 | 14 fev | Oui — base de tout |
| 2 | **Slides presentation** (6 slides + 4 backup) | CAB-1129 | 14 fev | Oui — support visuel |
| 3 | **Email Khalil** (preview staging + 5 questions feedback) | CAB-1130 | 14 fev EOD | Oui — feedback avant pitch |
| 4 | **Staging environment** (Portal + Console + comptes test + guide) | — | 16 fev | Non-bloquant (demo peut etre locale) |
| 5 | **MOU draft** 2 pages (Design Partner terms) | CAB-1124 | 21 fev | Non — post-demo follow-up |
| 6 | **Dry-run 3x** (chrono, objections, feedback) | CAB-1131 | 23 fev | Oui — pratique avant jour J |

### Dependances

```
CAB-1128 (script) ──┐
                     ├──> CAB-1131 (dry-run) ──> Demo Day 24 fev
CAB-1129 (slides) ──┘
                             │
CAB-1130 (email Khalil) ────┘ (feedback informe ajustements)
                             │
Staging env ─────────────────┘ (Khalil preview + demo backup)
```

---

## Binary Definition of Done (DoD)

### L1: Email Khalil (CAB-1130) — URGENT, deadline 14 fev EOD

**Binary DoD:**
- [ ] File created: `docs/demo/EMAIL-KHALIL.md`
- [ ] Objet email present (clair, design partner)
- [ ] Corps email structure: intro + lien staging + 5 questions feedback
- [ ] Ton francais professionnel (pas marketing)
- [ ] Lien staging guide inclus (local ou cloud selon Q2)
- [ ] 5 questions feedback strategiques (pertinentes banque)
- [ ] Signature Christophe presente
- [ ] Content compliance scan: zero P0/P1 violations
- [ ] File committed to main branch

**Livrable:** `docs/demo/EMAIL-KHALIL.md`
**Execution:** Instance CLI 1 (sonnet), ~15 min
**Bloquant:** Oui — feedback Khalil conditionne ajustements script/slides

---

### L2: Script Verbal 5min (CAB-1128) — URGENT, deadline 14 fev

**Binary DoD:**
- [ ] File created: `docs/demo/DESIGN-PARTNER-SCRIPT.md`
- [ ] Timing sections: 0:00-1:00 intro, 1:00-4:00 demo, 4:00-4:30 AI Factory, 4:30-5:00 close
- [ ] Total duration ≤ 5:00 (verifie par addition timings)
- [ ] Texte teleprompter-style (exact words to say)
- [ ] Transitions explicites entre sections
- [ ] Stage notes: quand cliquer, quand changer slide
- [ ] Q&A backup: 5 objections + reponses preparees
- [ ] References DEMO-SCRIPT.md scenarios 1-5 (condenses)
- [ ] Langue francais OU anglais (selon Q4, coherent avec slides)
- [ ] Content compliance scan: zero P0/P1 violations
- [ ] File committed to main branch

**Livrable:** `docs/demo/DESIGN-PARTNER-SCRIPT.md`
**Execution:** Instance CLI 2 (sonnet), ~45 min
**Bloquant:** Oui — fondation dry-runs

---

### L3: Slides Presentation (CAB-1129) — URGENT, deadline 14 fev

**Binary DoD:**
- [ ] File created: `docs/demo/DESIGN-PARTNER-SLIDES.md`
- [ ] 10 slides content: 6 main + 4 backup
- [ ] Slide 1: Probleme (3-5 douleurs banque webMethods/Oracle OAM)
- [ ] Slide 2: Proposition Design Partner (co-creation, pas vente)
- [ ] Slides 3-4: [demo live] — stage notes seulement
- [ ] Slide 5: AI Factory (timeline feedback → prod, 4 semaines POC)
- [ ] Slide 6: Design Partnership Terms (phases, gratuit, MOU simple)
- [ ] Backup slides 1-4: Standards, Architecture Hybride, Comparison, MOU detail
- [ ] Chaque slide: titre + 3-5 bullets + visuals suggeres
- [ ] Langue francais OU anglais (selon Q4, coherent avec script)
- [ ] Content compliance scan: zero P0/P1 violations
- [ ] File committed to main branch

**Livrable:** `docs/demo/DESIGN-PARTNER-SLIDES.md`
**Execution:** Instance CLI 3 (sonnet), ~30 min
**Bloquant:** Oui — support visuel demo

---

### L4: Staging Preview Guide (Non-bloquant, deadline 16 fev)

**Binary DoD:**
- [ ] File created: `docs/demo/STAGING-PREVIEW.md`
- [ ] Guide navigation 15 min structure
- [ ] URLs staging (local OU cloud selon Q2)
- [ ] Comptes test Keycloak (username/password)
- [ ] Parcours Khalil: login → discovery → subscribe → API call
- [ ] Screenshots strategiques identifies (Christophe ajoute)
- [ ] Verification seed-all.sh fonctionne (reference D11)
- [ ] Fallback docker-compose local documente
- [ ] File committed to main branch

**Livrable:** `docs/demo/STAGING-PREVIEW.md`
**Execution:** Instance CLI 1 (sonnet), ~20 min
**Bloquant:** Non — demo peut etre locale

---

### L5: MOU Draft (CAB-1124) — Non-urgent, deadline 21 fev

**Binary DoD:**
- [ ] File created: `docs/demo/MOU-DESIGN-PARTNER.md`
- [ ] Document 2 pages max
- [ ] Section 1: Parties (STOA Platform + Banque Europeenne)
- [ ] Section 2: Objet (co-creation, Design Partner, POC 4 semaines + 6-12 mois)
- [ ] Section 3: Duree (POC + phase longue + sortie)
- [ ] Section 4: Obligations (STOA: support + features, Banque: feedback + testing)
- [ ] Section 5: IP (STOA garde IP, banque licence perpetuelle)
- [ ] Section 6: Confidentialite (NDA mutuel)
- [ ] Section 7: Sortie (resiliation, transition)
- [ ] Disclaimer: "document non-juridique, a valider par avocat"
- [ ] Ton francais juridique simple
- [ ] Content compliance scan: zero P0/P1 violations
- [ ] File committed to main branch

**Livrable:** `docs/demo/MOU-DESIGN-PARTNER.md`
**Execution:** Instance CLI 1 (sonnet), ~25 min
**Bloquant:** Non — post-demo follow-up

---

### L6: Dry-Run 3x (CAB-1131) — CRITIQUE, deadline 23 fev

**Binary DoD:**
- [ ] Dry-run 1: chrono < 5:30, notes problemes
- [ ] Ajustements script/slides selon dry-run 1
- [ ] Dry-run 2: chrono < 5:15, notes problemes
- [ ] Ajustements script/slides selon dry-run 2
- [ ] Dry-run 3: chrono < 5:00 confirme, zero probleme
- [ ] Objections Q&A testees (5 scenarios)
- [ ] Video backup enregistree (selon Q3)
- [ ] Script + slides finalises committed

**Livrable:** Script + slides finalises
**Execution:** Christophe (hors Claude)
**Bloquant:** Oui — validation avant Demo Day

---

## Risques Identifies

| # | Risque | Impact | Probabilite | Mitigation |
|---|--------|--------|-------------|------------|
| 1 | **Demo live plante** (docker service down, token fail) | Demo ruinee | Moyen | Video backup pre-enregistree + slides screenshot |
| 2 | **Khalil feedback tardif** (apres 16 fev) | Pas de temps ajuster | Moyen | Email vendredi 14, deadline dimanche 16, call lundi backup |
| 3 | **Audience attend vente classique** (procurement, SLA, pricing) | Deconnexion Design Partner | Faible | Anticiper dans Q&A: "Design Partner ≠ vendor, gratuit, MOU simple" |
| 4 | **Questions techniques profondes** (mTLS, Oracle token exchange) | Christophe seul (Cedric backup) | Faible | Backup slides Standards + Architecture Hybride |
| 5 | **5 min trop court** pour demo live | Demo rushing, impression brouillon | Moyen | Chronometrer 3x, couper scenarios si besoin (garder Discovery + Subscribe seulement) |
| 6 | **Staging pas pret** (domaine non configure) | Khalil ne peut pas tester | Moyen | Fallback: docker-compose local + video screencast |
| 7 | **Content compliance violation** (claim concurrent, prix mentionne) | Risque legal | Faible | Scanner tous livrables via content-reviewer avant publication |

---

## Pre-Execution Questions (BLOCKER — repondre avant Phase 1)

Ces questions impactent la generation des livrables. Reponses necessaires AVANT de lancer Phase 1.

### Q1: Langue presentation (CRITIQUE — impacte script + slides)
**Question:** Le pitch est en francais ou anglais?
**Context:** Email Khalil est en francais, DEMO-SCRIPT.md existant est en anglais
**Impact:** Tous les livrables doivent etre dans la meme langue (coherence)
**Reponse attendue:** `francais` OU `anglais`

### Q2: Staging environment (impacte guide + email)
**Question:** La demo du 24 fev sera sur docker-compose local ou EKS cloud?
**Context:** Guide Khalil pointe des URLs differentes (localhost vs portal.staging.gostoa.dev)
**Impact:** URLs dans EMAIL-KHALIL.md + STAGING-PREVIEW.md
**Reponse attendue:** `local` OU `cloud (portal.staging.gostoa.dev)`

### Q3: Outil slides (low priority — n'impacte pas generation)
**Question:** Quel outil pour creer les slides visuels?
**Context:** Claude genere DESIGN-PARTNER-SLIDES.md (markdown), Christophe cree slides visuels
**Impact:** Aucun — le markdown genere est universel
**Reponse attendue:** Google Slides / Keynote / PowerPoint / Canva / reveal.js

### Q4: Video backup (low priority — post-dry-run)
**Question:** Faut-il preparer un script de recording (OBS, Loom)?
**Context:** Mitigation risque "demo live plante"
**Impact:** Aucun sur Phase 1-2, relevant pour Phase 4 (dry-runs)
**Reponse attendue:** `oui (script OBS/Loom)` OU `non (Christophe gere)`

---

## Decision: Execution Immediate (reponse Q5 implicite)

**Q5 resolved:** Les 3 livrables urgents en **parallele** (Phase 1) — email + script + slides simultanement.
**Rationale:** Deadline 14 fev = 2.5 jours. Parallelisation gagne 45 min. Cost acceptable (~$15).

---

## AI Factory Execution Strategy

### Timing Constraints (mardi 10 fev, 12:00)

| Track | Deadline | Items | Time Available |
|-------|----------|-------|----------------|
| **URGENT** | 14 fev EOD | Email, Script, Slides | 2.5 jours (60h) |
| **Non-urgent** | 16-21 fev | Staging, MOU | 6-11 jours |
| **Post-feedback** | 23 fev | Dry-runs 3x | Apres feedback Khalil |

### Phase 1: Parallel Urgent Track (10-11 fev, ~2h wall time)

**3 instances CLI en parallele** — delivre 3 livrables en ~45 min vs 90 min sequentiel

```bash
# Terminal 1 — tmux session "demo-email"
cd stoa && claude --profile demo-email
Prompt: "Generate EMAIL-KHALIL.md following Binary DoD L1"
Model: sonnet | Duration: ~15 min | Cost: ~$2

# Terminal 2 — tmux session "demo-script"
cd stoa && claude --profile demo-script
Prompt: "Generate DESIGN-PARTNER-SCRIPT.md following Binary DoD L2"
Model: sonnet | Duration: ~45 min | Cost: ~$8

# Terminal 3 — tmux session "demo-slides"
cd stoa && claude --profile demo-slides
Prompt: "Generate DESIGN-PARTNER-SLIDES.md following Binary DoD L3"
Model: sonnet | Duration: ~30 min | Cost: ~$5
```

**Total Phase 1:** 45 min wall time, ~$15 cost, 3 deliverables DONE

**Verification checkpoint:**
```bash
# Verifier les 3 fichiers crees
ls -lh docs/demo/EMAIL-KHALIL.md
ls -lh docs/demo/DESIGN-PARTNER-SCRIPT.md
ls -lh docs/demo/DESIGN-PARTNER-SLIDES.md

# Scanner content compliance (1 instance, haiku)
claude --profile demo-compliance
Prompt: "Run content-reviewer agent on docs/demo/*.md — zero P0/P1 violations"
Model: haiku | Duration: ~10 min | Cost: ~$0.50
```

**Output Phase 1:** Email pret a envoyer + Script verbal + Slides content → deadline 14 fev OK

---

### Phase 2: Sequential Non-Urgent Track (11-13 fev, ~1h total)

**1 instance CLI, 2 livrables sequentiels**

```bash
# Terminal 1 — reuse "demo-email" session
Prompt: "Generate STAGING-PREVIEW.md following Binary DoD L4"
Model: sonnet | Duration: ~20 min | Cost: ~$3

# Same terminal
Prompt: "Generate MOU-DESIGN-PARTNER.md following Binary DoD L5"
Model: sonnet | Duration: ~25 min | Cost: ~$4
```

**Total Phase 2:** 45 min wall time, ~$7 cost, 2 deliverables DONE

**Verification checkpoint:**
```bash
# Verifier staging guide + MOU
ls -lh docs/demo/STAGING-PREVIEW.md
ls -lh docs/demo/MOU-DESIGN-PARTNER.md

# Re-scan content compliance si modifs
claude --profile demo-compliance
Model: haiku | Duration: ~5 min | Cost: ~$0.25
```

**Output Phase 2:** Guide staging + MOU draft → deadlines 16-21 fev OK

---

### Phase 3: Feedback Loop (14-17 fev, humain)

**Christophe actions (hors Claude):**
1. **Vendredi 14 fev EOD:** Envoyer EMAIL-KHALIL.md a Khalil
2. **Samedi-dimanche 15-16 fev:** Attendre feedback Khalil
3. **Lundi 17 fev:** Analyser feedback + identifier ajustements

**Si ajustements necessaires:**
```bash
# 1 instance CLI, micro-edits
claude --profile demo-adjust
Prompt: "Adjust DESIGN-PARTNER-SCRIPT.md based on Khalil feedback: <paste feedback>"
Model: sonnet | Duration: ~15 min | Cost: ~$2

# Same terminal
Prompt: "Adjust DESIGN-PARTNER-SLIDES.md based on Khalil feedback: <paste feedback>"
Model: sonnet | Duration: ~10 min | Cost: ~$1.50
```

**Output Phase 3:** Script + Slides ajustes selon feedback expert

---

### Phase 4: Dry-Run Iterations (18-23 fev, humain + Claude)

**Christophe actions:**
- **Dry-run 1 (lun 18 fev):** Chronometrer, noter problemes
- **Dry-run 2 (mer 20 fev):** Re-chronometrer, noter problemes
- **Dry-run 3 (ven 22 fev):** Final < 5 min confirme

**Claude assistance (si ajustements scripts):**
```bash
# Apres chaque dry-run
claude --profile demo-adjust
Prompt: "Adjust DESIGN-PARTNER-SCRIPT.md: <paste problems from dry-run>"
Model: sonnet | Duration: ~10 min/iteration | Cost: ~$1.50/iteration
```

**Output Phase 4:** Script + Slides finalises, chrono < 5 min valide

---

### Phase 5: Demo Day (24 fev)

**Pre-flight checklist** (23 fev soir):
- [ ] Script verbal imprime (teleprompter backup)
- [ ] Slides finalises (PowerPoint/Keynote crees par Christophe)
- [ ] Video backup enregistree (selon Q3)
- [ ] Staging environment UP (docker-compose local OU EKS)
- [ ] Comptes test valides (Keycloak)
- [ ] Q&A responses memorisees (5 objections)

---

## Cost & Time Summary

| Phase | Duration (wall) | Cost | Deliverables |
|-------|-----------------|------|--------------|
| Phase 1 (parallel) | 45 min | ~$15.50 | Email + Script + Slides + compliance |
| Phase 2 (sequential) | 45 min | ~$7.25 | Staging + MOU + compliance |
| Phase 3 (feedback) | 25 min | ~$3.50 | Ajustements script/slides |
| Phase 4 (dry-runs) | 30 min | ~$4.50 | Finalisations |
| **TOTAL** | **~2h30** | **~$30.75** | **5 docs + 3 iterations** |

**Gain parallelisation Phase 1:** 45 min saved (90 min → 45 min)
**Deadlines:** Toutes respectees (14 fev, 16 fev, 21 fev, 23 fev)

---

## Execution Order — AI Factory Optimized

**Immediate (mardi 10 fev apres-midi, parallele):**
1. Instance 1: EMAIL-KHALIL.md (15 min, sonnet)
2. Instance 2: DESIGN-PARTNER-SCRIPT.md (45 min, sonnet)
3. Instance 3: DESIGN-PARTNER-SLIDES.md (30 min, sonnet)
4. Instance 4: content-reviewer scan (10 min, haiku)

**Mercredi 11 fev (sequentiel):**
5. Instance 1: STAGING-PREVIEW.md (20 min, sonnet)
6. Instance 1: MOU-DESIGN-PARTNER.md (25 min, sonnet)
7. Instance 4: content-reviewer re-scan (5 min, haiku)

**Vendredi 14 fev EOD:**
8. Christophe envoie email a Khalil

**Lundi 17 fev (si feedback):**
9. Instance 1: Ajustements script/slides (25 min, sonnet)

**Lun 18, Mer 20, Ven 22 fev:**
10. Dry-runs + ajustements iteratifs (10 min/iteration, sonnet)

**Lundi 24 fev:**
11. Demo Day — SHIP IT 🚀

---

## Ship/Show/Ask + Confidence

**Mode:** Ship (tous livrables)
**Rationale:** Documents internes (`docs/demo/`), zero risk, zero code change, zero infra

**Confidence:** [High]
**Justification:**
- Contexte extremement detaille fourni (script templates, slides structure, email texte, MOU sections)
- Tache = structuration + mise en forme (pas invention)
- Binary DoD clair pour chaque livrable
- Seul risque: ajustements tone/style post-feedback Khalil (Phase 3, prevu)

---

## Archive: Cycle 7 Scoreboard

> Cycle 7 complete: 225 pts / 22 PRs (9-10 fev 2026)
> Demo Sprint D1-D11 complete + R1 MCP endpoints
> Details: `memory.md` + `completed-tickets.md`
> Remaining: CAB-1035 (2 pts manual), CAB-1066 (34 pts stoa-web, stretch)
