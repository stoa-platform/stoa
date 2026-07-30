---
id: decision-2026-05-23-stoa-kill-total
plan_ref: docs/plans/2026-05-23-stoa-kill-total.md
verdict: go
gate: 12
gate_log: stoa-docs/HEGEMON/DECISION_GATE.md
challenger: operator (solo project mode, no external challenger requested)
date: 2026-05-23
---

# Decision Gate #12 — STOA Platform shutdown (kill total)

## Verdict

**GO** — operator self-validation.

## Triggers matchés

- (a) >5h ops : wind-down complet ≈ 4-6h Claude étalé sur 7j elapsed.
- (b) Business direct : project shutdown, fin du SaaS, impact GTM total.
- (c) Irréversible : destruction infra prod, archive repos publics, dump données client (réversible par restore mais coût ≥ 1 jour).

## Contexte décision

- 6 mois écoulés depuis le lancement actif.
- **0 client signé**.
- **~€12 K cumulés engagés** (infra + temps + outillage).
- Charge mensuelle courante ~€225-400/mo selon scope (réduction prod-only du 2026-05-20 visait €70-110/mo mais reste un saignement sans revenu).
- Opérateur ne peut plus assumer financièrement ni mentalement.
- Nouveau projet déjà défini (scope séparé, pas dans ce gate).

## Pourquoi pas de challenger externe

Le Decision Gate #11 (réduction infra) a été validé sans challenger externe en `solo project mode` car la décision était opérationnelle (économie pure, scope additif négatif). Le présent #12 est plus radical (shutdown) mais **moins ambigu** :

- Pas de trade-off à arbitrer : zéro revenu, charge non soutenable, équation triviale.
- Un challenger externe ne pourrait que recommander soit (a) shutdown (= verdict identique), soit (b) "trouve un client en 30 jours" (= déni de la réalité 6 mois écoulés sans pipeline).
- La doctrine `feedback_doctrine_routes_through_doctrine.md` exige plan-validation + gate. Les deux sont faits. La doctrine n'impose pas un challenger sur chaque gate ; elle impose une contre-analyse quand l'opérateur est dans le doute ou dans le hype.

L'opérateur n'est ni dans le doute ni dans le hype. La décision est sobre et financièrement forcée.

## Alternatives considérées et rejetées

| Option | Pourquoi rejetée |
|---|---|
| Park minimal (€5-20/mo, landing statique) | Coût cognitif > coût financier. Garder "ouvert" = continuer à penser à STOA au lieu du nouveau projet. |
| Open source only (kill infra, repos vivants) | OK techniquement mais l'opérateur préfère trait final pour psychologie. Repos restent publics archivés — `gh repo archive` couvre ce besoin sans entretien actif. |
| Pivot des assets (HEGEMON / UAC / AI Factory) | Hors scope de ce gate. Le code reste accessible (Apache 2.0, repos archivés + tarballs privés locaux). Si le nouveau projet a besoin d'un asset, il est restaurable en 1h. Pas besoin de pré-extraire maintenant. |
| Continuer 3 mois de plus pour validation finale GTM | Décision rejetée 2026-05-23 — opérateur a fait l'arbitrage : pas d'extension. |

## Conditions de validation post-exécution

Considérer le shutdown réussi si à J+10 :
- Facturation OVH/Contabo/Hetzner : invoices J+30 = €0 (ou résiduels de fin de cycle).
- `gh repo list stoa-platform` : tous repos `isArchived: true`.
- Tarballs `~/Backups/stoa-shutdown/*.tar.gz.gpg` présents, vérifiés `gpg --decrypt | tar -t` OK.
- `MEMORY.md` + `infra-status.md` mis à jour : sections "DECOMMISSIONED 2026-05" datées.

## Réversibilité

- **Re-provision infra** : `stoa-infra` tarball + IaC Terraform/Ansible/Helm = re-deploy possible en ~1-2 jours (OVH MKS provisioning + Vault restore + KC realm import + PG restore + ArgoCD bootstrap).
- **Re-open repos** : `gh repo unarchive` instantané, code/historique intact.
- **Domaine** : si conservé renewal, re-pointer vers nouveau cluster trivial.
- **Données client** : PG dump chiffré conservé 1 an minimum (RGPD : si dump contient données nominatives, destruction documentée à J+365 ou plus tôt si pas de base légale).

Coût psychologique de la réversion : modéré. Coût technique : faible. = décision pas définitive irréversible, juste un trait d'arrêt opérationnel.

## Sign-off

Opérateur unique (`feedback_solo_project_mode_signoffs.md`) agissant comme product / security / privacy / business owner. Pas de DPO/Legal/Finance séparés à invoquer.

Date : 2026-05-23.
