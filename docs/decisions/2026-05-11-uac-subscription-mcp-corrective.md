---
title: "Decision — UAC Subscription MCP Corrective Plan"
date: 2026-05-13
source_plan: "docs/plans/2026-05-11-uac-subscription-mcp-corrective.md"
source_audit: "docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md"
verdict: "GO_WITH_CONDITIONS"
challenger: "GPT-5.5 Pro — external non-Claude challenger"
validation_status: "accepted"
plan_validation_status_recommendation: "challenged"
code_execution_authorized_by_this_record: false
phase0_authorization: "conditional_after_conditions_are_written_and_signed"
---

# Decision — UAC Subscription MCP Corrective Plan

> **2026-05-18 — ADR numbers renumbered +2.** The ADR references in this record were originally written as ADR-067…071. They were renumbered into free `stoa-docs` slots **ADR-069…073** (gateway fail-closed = ADR-072) after a duplicate-`adr-060` dedup on `stoa-docs` `main` took `adr-067`/`adr-068`. Verdict and conditions are unchanged. See `docs/plans/2026-05-11-uac-subscription-mcp-corrective.md` §8.

## 1. Verdict

**Verdict challenger : `GO_WITH_CONDITIONS`.**

Le plan correctif est directionnellement juste : il attaque les bons systèmes de contrôle — fail-closed gateway, enforcement runtime des approvals, immutabilité audit, chaîne audit Gateway↔CP, révocation/deprovision, state machine et doctrine ADR. Il ne doit toutefois pas être marqué `validated` tel quel, car plusieurs décisions de design restent encore implicites ou insuffisamment prouvables.

**Effet du verdict :**

- le plan peut passer de `draft` à `challenged` ;
- les ADRs et tickets Linear peuvent être préparés ;
- aucune PR P0 de code, migration DB ou changement gateway ne doit être mergée sur la seule base de ce document ;
- les PRs P0 ne deviennent autorisables qu’après incorporation des conditions ci-dessous dans le plan/les ADRs et sign-off des owners concernés.

Le verdict n’est pas `GO` parce que le plan mélange encore deux niveaux :

1. fermeture locale de certains P0 ;
2. levée du NOGO régulateur bout-en-bout.

Ces deux niveaux doivent être séparés explicitement avant exécution.

---

## 2. Conditions bloquantes

### C0 — Statut du plan

Mettre le plan à `validation_status: challenged`, pas `validated`.

`validated` ne doit être utilisé qu’après :

- acceptation écrite des conditions C1 à C7 ;
- ADR-069, ADR-070, ADR-071 et ADR-072 au minimum en draft reviewable ;
- owners business, security, compliance, gateway et CP-API nommés.

### C1 — Clarifier le split Phase 0 / levée du NOGO régulateur

Le plan liste `P0-AUD-2` comme blocker P0, mais place la vraie chaîne audit Gateway↔CP en Phase 1. Cette tension doit être rendue explicite.

Condition : choisir une des deux options avant démarrage :

- **Option A — Promote minimal audit chain to Phase 0** : créer dès Phase 0 un endpoint CP minimal `/v1/internal/audit/emit` et un client gateway minimal pour les décisions deny/approval-gate ;
- **Option B — Garder en Phase 1** : accepter que la Phase 0 ferme des P0 locaux mais ne lève pas encore le NOGO DORA/NIS2, puisque le Gate G2 reste FAIL jusqu’à Phase 1.

Recommandation challenger : **Option A** pour les deny critiques, même si le buffer/retry complet reste en Phase 1.

### C2 — Fail-closed business acceptance

Le fail-closed est acceptable et nécessaire pour le périmètre régulé, mais il doit être assumé comme un comportement business, pas seulement technique.

Condition : ajouter un sign-off business/security sur les règles suivantes :

- cache absent = deny ;
- cache expiré = deny ;
- CP unreachable + cache expiré = deny ;
- aucune extension de TTL pendant outage CP ;
- aucun mode dégradé “read-only” implicite tant que le gateway ne peut pas prouver la séparation read-only / mutating par contrat UAC typé ;
- readiness doit exposer l’état réel d’enforcement.

Un mode “read-only” ne pourra être ajouté qu’ultérieurement, sous ADR-072, avec preuves typées et tests séparés.

### C3 — Cache permissions gateway : artefact signé et non extensible

Un cache frais peut être accepté pendant une indisponibilité CP, mais seulement comme artefact de politique explicite.

Condition : formaliser dans ADR-072 :

- `policy_version` ;
- `issued_at` ;
- `expires_at` ;
- signature ou MAC CP ;
- tenant scope ;
- allow-set explicite ;
- deny par défaut pour permission absente ;
- expiration non prolongeable localement ;
- invalidation de révocation prioritaire sur tout cache ;
- audit local/queued pour tout deny lié au cache.

### C4 — Approval token : suffisant seulement avec intent binding et preuve 4-eyes

Le JWT single-use proposé est une bonne base, mais il ne suffit pas à lui seul à prouver le 4-eyes.

Condition : enrichir le modèle d’approval token avec :

- `arguments_hash` ou `request_hash` pour lier l’approbation à l’intention exacte de l’appel ;
- `contract_version` ou `policy_version` obligatoire ;
- contrôle `approver_actor_id != requester_actor_id` quand l’opération exige 4-eyes ;
- vérification côté CP que l’approver possède le rôle requis ;
- stockage atomique du `jti` consommé, ou store gateway/CP garantissant le single-use ;
- audit `APPROVAL_TOKEN_ISSUED`, `APPROVAL_TOKEN_USED`, `APPROVAL_TOKEN_REJECTED` ;
- rejet si tenant, tool, call id, hash arguments, TTL ou policy version divergent.

Sans `arguments_hash`, un token pourrait autoriser un appel différent de celui approuvé.

### C5 — Audit immutability : trigger strict, procédure migration séparée

Le trigger PostgreSQL doit bloquer `UPDATE` et `DELETE` sur `audit_events` en production.

Condition : ADR-071 doit trancher avant migration :

- aucune mutation applicative de `audit_events` ;
- `erase_user_pii()` doit produire des événements append-only et/ou une table auxiliaire, sans altérer la ligne audit source ;
- toute correction future passe par événement compensatoire ou table auxiliaire ;
- les migrations correctives futures ne peuvent contourner le trigger que via procédure break-glass formalisée, datée, approuvée et auditée ;
- le rollback de la migration trigger doit être un forward-fix, sauf incident critique documenté.

### C6 — State machine : ajouter partial provisioning et failure states opérables

La state machine proposée couvre la direction générale, mais doit être renforcée pour les déploiements multi-gateway ou multi-region.

Condition : ajouter avant Phase 2 :

- ack par gateway ou par policy target ;
- état `PARTIALLY_PROVISIONED` ou équivalent si certains targets ack et d’autres non ;
- état `REVOCATION_FAILED` ou `DEPROVISIONING_FAILED` visible et alertable ;
- règle claire : `ACTIVE` seulement si tous les targets requis sont prêts ;
- règle claire : `REVOKED` seulement si tous les targets requis ont ack la révocation, ou si un mécanisme de deny supérieur prouve l’arrêt d’usage.

Pour Phase 0, le minimum acceptable est : `REVOKING` / `DEPROVISIONING` / `DEPROVISIONING_FAILED` + retry + alerte.

### C7 — Planning 9 semaines conditionnel au staffing parallèle

Le plan 9 semaines est réaliste seulement avec des workstreams parallèles et un environnement de test prêt.

Condition : préciser les hypothèses de capacité :

- au moins 1 owner gateway Rust ;
- au moins 1 owner CP-API Python/DB ;
- support security/compliance pour ADR-071/ADR-072 ;
- staging avec PostgreSQL, gateway, CP, Kafka/webhook ou équivalent ;
- capacité QA/e2e dédiée pour smoke DORA/NIS2.

Sans ces hypothèses, rebaser le planning à **12–14 semaines** plutôt que 9.

---

## 3. Réponses aux questions du gate

### 1. Le passage fail-closed est-il acceptable business sans mode dégradé “read-only” ?

**Réponse : oui, sous condition C2.**

Pour un chemin d’accès régulé, un mode fail-open ou read-only implicite est plus risqué qu’une indisponibilité contrôlée. Le plan doit toutefois assumer l’impact produit : incident CP peut devenir incident d’accès gateway. Cela exige un runbook, des métriques, un canary et un sign-off business.

Le mode read-only ne doit pas être improvisé. Il ne peut être autorisé qu’avec une preuve machine-readable que l’opération est réellement non-mutating, dérivée du contrat UAC et non d’une heuristique.

### 2. Peut-on autoriser un cache de permissions gateway pendant une indisponibilité CP ?

**Réponse : oui uniquement jusqu’à expiration d’un cache frais, signé et explicitement scoped. Après expiration : deny.**

Règles challenger :

- fresh cache + allow explicite = allow ;
- missing permission = deny ;
- stale cache = deny new calls ;
- unavailable CP + no fresh cache = deny ;
- révocation explicite = invalidation prioritaire, même si le cache n’a pas expiré ;
- aucune prolongation locale du cache par le gateway.

### 3. Le modèle d’approval token JWT single-use est-il suffisant pour prouver le 4-eyes ?

**Réponse : pas tel qu’écrit ; oui sous condition C4.**

Un JWT single-use prouve qu’un jeton a été présenté. Il ne prouve pas automatiquement :

- que l’approver était distinct de l’executor/requester ;
- que l’approver avait le bon rôle ;
- que l’approbation porte sur les mêmes arguments que l’appel exécuté ;
- que le token n’est pas réutilisé dans une race condition ;
- que la version de politique/UAC approuvée est celle exécutée.

Avec `arguments_hash`, séparation des acteurs, store `jti` atomique, TTL court, audit complet et policy version binding, le modèle devient acceptable.

### 4. La pseudonymisation hors-table `audit_events` résout-elle correctement le conflit GDPR Art.17 vs DORA Art.11 ?

**Réponse : direction correcte, mais résolution incomplète tant qu’ADR-071 n’est pas accepté.**

La table auxiliaire est préférable à une mutation in-place, car elle préserve la ligne source et crée une preuve d’effacement/pseudonymisation. Mais il faut documenter :

- ce qui est conservé ;
- ce qui est pseudonymisé ;
- qui peut relier le hash à l’identité originale ;
- comment répondre à une demande d’accès/effacement ;
- quelles données sont considérées réglementaires et non purgeables ;
- quelle durée de rétention s’applique à chaque table.

### 5. Le trigger PostgreSQL d’immutabilité doit-il bloquer toutes les mises à jour, y compris les migrations correctives futures ?

**Réponse : oui en production, avec procédure break-glass exceptionnelle.**

Le trigger doit bloquer les mutations ordinaires et applicatives. Pour les migrations futures, le comportement normal doit être : append compensatoire, backfill dans table auxiliaire, ou correction par nouvel événement. Le contournement du trigger ne doit exister que comme procédure break-glass : Decision Record, fenêtre de maintenance, approbation security/compliance, journalisation et vérification post-migration.

### 6. La state machine unifiée proposée couvre-t-elle les états “partial provisioning” et “revocation failed” ?

**Réponse : partiellement.**

Elle couvre bien la direction `APPROVED → PROVISIONING → READY → ACTIVE` et `REVOKING → DEPROVISIONING → REVOKED`, mais elle ne suffit pas encore pour les cas multi-target : un gateway peut ack pendant qu’un autre échoue. Ajouter `PARTIALLY_PROVISIONED` ou une structure d’ack par target, ainsi que `DEPROVISIONING_FAILED` / `REVOCATION_FAILED`, est nécessaire.

### 7. Le plan 9 semaines est-il réaliste ?

**Réponse : oui seulement avec staffing parallèle et staging prêt ; sinon non.**

Les volumes annoncés (~6800 LOC, ~67 tests) sont plausibles, mais le chemin critique est moins le LOC que :

- migrations DB + trigger audit ;
- behavior change gateway fail-closed ;
- endpoint audit inter-service ;
- smoke e2e CP↔Gateway ;
- ADR-071/ADR-072 avec sign-off sécurité/compliance ;
- state machine + compatibilité API/UI.

Avec une seule équipe séquentielle, 9 semaines est optimiste. Avec deux workstreams techniques + support compliance/QA, 9 semaines est acceptable.

---

## 4. Scope autorisé / refusé

### Autorisé immédiatement

- Création des ADR drafts : ADR-069, ADR-070, ADR-071, ADR-072, puis ADR-001.
- Création des tickets Linear, sans assigner encore de date de merge P0.
- Mise à jour du plan à `validation_status: challenged`.
- Préparation des tests/smoke specs.
- Revue de staffing et owners.

### Autorisable après conditions écrites et signées

- `P0-SUB-2` TTL commit, avec test transactionnel.
- `P0-GW-1` et `P0-GW-2`, après ADR-072 draft et sign-off fail-closed.
- `P0-MCP-1`, après ajout des exigences `arguments_hash`, jti single-use atomique et preuve 4-eyes.
- `P0-AUD-1`, après ADR-071 draft accepté par security/compliance.
- `P0-SUB-1`, après formalisation des états minimum `REVOKING/DEPROVISIONING/DEPROVISIONING_FAILED`.
- `P0-AUD-2`, soit en Phase 0 minimal, soit explicitement reporté en Phase 1 avec mention que le NOGO régulateur n’est pas levé avant cette Phase.

### Refusé à ce stade

- Marquer le plan `validated`.
- Démarrer une migration `audit_events` sans ADR-071.
- Introduire un mode read-only ou cached-allow implicite pendant outage CP.
- Déclarer la doctrine ADR-069 conforme sans enforcement runtime et smoke test.
- Déclarer la conformité DORA/NIS2 après Phase 0 si Gateway↔CP audit chain reste absente.

---

## 5. Delta recommandé à appliquer au plan

Ajouter une section `1.6 Challenger verdict` au plan ou mettre à jour le frontmatter :

```yaml
validation_status: challenged
decision_record: "docs/decisions/2026-05-11-uac-subscription-mcp-corrective.md"
decision_verdict: "GO_WITH_CONDITIONS"
challenged_at: "2026-05-13"
challenger: "GPT-5.5 Pro — external non-Claude challenger"
```

Ajouter également dans la section Phase 0 :

```text
Important: Phase 0 closes local P0 blockers only if P0-AUD-2 minimal audit chain is included.
If P0-AUD-2 remains in Phase 1, the global NOGO remains in force until Phase 1 acceptance.
```

---

## 6. Sign-off

- Accountable owner: TBD
- Business owner: TBD
- Security: TBD
- Compliance: TBD
- Gateway: TBD
- CP-API: TBD
- External challenger: GPT-5.5 Pro — verdict `GO_WITH_CONDITIONS`

---

## 7. Final challenger statement

Le plan est solide comme base de remédiation, mais il ne doit pas être traité comme un GO d’exécution brut. Le bon état documentaire après ce gate est :

```text
plan.validation_status = challenged
verdict = GO_WITH_CONDITIONS
code execution = blocked until conditions C1-C7 are integrated and signed
```

La ligne rouge principale : **ne pas déclarer la levée du NOGO tant que la chaîne audit Gateway↔CP n’est pas opérationnelle et prouvée par smoke test.**
