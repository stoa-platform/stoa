---
id: plan-2026-05-23-stoa-kill-total
triggers: [a, b, c]                    # a: >5h ops; b: business (project shutdown); c: irreversible (deletions + repo archives + DNS release)
validation_status: validated           # operator self-validation, solo project mode, project shutdown decision
challenge_ref: docs/decisions/2026-05-23-stoa-kill-total.md
supersedes: docs/plans/2026-05-20-infra-reduction-prod-only.md
---

# Plan — STOA Platform kill total (project shutdown)

## Contexte

6 mois de runway. Pas de client signé. ~€12 K cumulés engagés. Opérateur ne peut plus assumer la charge mensuelle (~€225-390/mo selon mois) ni la charge cognitive. Décision : shutdown complet, cible **€0/mo runtime**. Repos publics archivés read-only (le code reste accessible Apache 2.0). Repos privés archivés + tarball local. Aucun client live → aucun préavis externe nécessaire. Le plan d'infra-reduction du 2026-05-20 (prod-only €70-110/mo) est superseded.

## Objectif

- Stopper toute facturation infra récurrente sous 7 jours.
- Préserver irréversiblement les artefacts qui ont une valeur future (code OSS, IP HEGEMON, méthodologie AI Factory, données prod au cas où un repreneur apparaît).
- Pas de post-mortem public obligatoire (silence radio acceptable). Option blog/LinkedIn ouverte mais non bloquante.

## Scope

**In**
- Kill TOUS les payants : MKS Prod, MKS Dev (déjà couvert par plan mardi), tous VPS OVH (vault-vps inclus cette fois), Contabo HEGEMON + runners, Hetzner staging, OVH managed PG, OVH LB, tooling-vps, infisical-vps.
- Archive repos publics : `stoa-platform/stoa`, `stoa-docs`, `stoa-web`, `stoa-quickstart`, `stoactl` → `gh repo archive` + README "Project archived — Apache 2.0, no longer maintained".
- Archive repos privés : `PotoMitan/stoa-strategy`, `PotoMitan/stoa-infra` → tarball local chiffré + `gh repo archive`.
- DNS Cloudflare : release zone `gostoa.dev` (ou laisser expirer au prochain renewal).
- Tiers SaaS : Linear export + workspace freeze, Vercel projets delete, Cloudflare zone delete, MCP integrations désautorisées.
- L3.5 Autopilot kill-switches activés (`DISABLE_AUTOPILOT_SCAN=true`, `DISABLE_L3_LINEAR=true`).

**Out**
- Migration code/IP vers nouveau projet (opérateur a indiqué nouveau projet défini — scope séparé, post-shutdown).
- Comms publiques (blog, LinkedIn, mailing prospects). Optionnel, l'opérateur décide après.
- Décision sur domaines `gostoa.dev` / `klinnovation` (re-sell, garder en parking, release) — peanut financier, à trancher J+5.

## Phases

### Phase 0 — Decision Gate #12 + irreversibility checks
- Decision Gate #12 enregistré dans `stoa-docs/HEGEMON/DECISION_GATE.md` (operator self-validation, solo project mode `feedback_solo_project_mode_signoffs.md`).
- Pas de challenger externe : décision opérateur tranchée, contre-analyse non requise (vs Gate #11 où ratio coût/bénéfice était à challenger).
- Snapshot état facturation actuelle : OVH dashboard, Contabo panel, Hetzner console → capture screenshot dans `docs/archives/2026-05-23-kill-total/billing-baseline/`.

### Phase 1 — Backups irréversibles (BLOQUANTE — J0)
**Aucune destruction Phase 2+ avant que Phase 1 soit committée.**

- **PG prod dump** : `kubectl exec -n stoa-system <cp-api-pod> -- pg_dump $DATABASE_URL > stoa-prod-$(date +%F).sql` → chiffré GPG → `docs/archives/2026-05-23-kill-total/db/` **(gitignored, pointer file in git)** + copie locale `~/Backups/stoa-shutdown/`.
- **Vault export** : `vault kv export secret/` via `vault-vps` (`hcvault.gostoa.dev`) → JSON chiffré GPG → backups locaux.
- **Keycloak realms export** : `kcadm get realms -r stoa --fields *` ou via Helm bootstrap-job artefact → JSON → backups locaux.
- **stoa-strategy** : `git clone --mirror` → tarball local chiffré (refs/research client, GTM, pricing — ne JAMAIS leak publiquement).
- **stoa-infra** : `git clone --mirror` → tarball local chiffré (IaC complète, utile si re-provision plus tard).
- **HEGEMON binary + DB + config** : SCP `worker-1` → backup local (réutilisable autre projet).
- **n8n workflows / Uptime Kuma / Netbox** : déjà couvert par Phase 1 du plan mardi — reprendre exports si non encore faits.
- Manifest : `docs/archives/2026-05-23-kill-total/MANIFEST.md` listant chaque archive + sha256 + emplacement local + clé GPG utilisée.
- **Verify**: tar -tf chaque tarball, gpg --decrypt --output=/dev/null sur 1 fichier, restore-test SQL dump dans PG local sacrificiel (docker run postgres + `psql -f`).

### Phase 2 — Stop la facturation récurrente (J+1)
Ordre = saigner le plus cher d'abord, mais sans toucher au runtime live tant que Phase 3 n'est pas faite.

- **Contabo HEGEMON 5 VPS** (~€45/mo) : cancel via panel. Vérifier période engagement (souvent next billing cycle, pas immédiat).
- **Contabo runners 4 VPS** (~€36/mo) : désenregistrer GH runners (`gh api -X DELETE`), cancel via panel. PR `ci(runners): drop self-hosted contabo` reprise du plan mardi Phase 3.
- **Hetzner staging 5 cx33 + LB** (~€45/mo) : cancel via console.
- **OVH VPS fleet** 11 (dev/bench/tooling/infisical) **+ vault-vps** (€60/mo cumulé) : cancel via OVH manager. **vault-vps tué après Phase 1 export confirmé**.
- **HEGEMON kill-switches** : GitHub repo variables `DISABLE_AUTOPILOT_SCAN=true`, `DISABLE_L3_LINEAR=true`. systemctl stop hegemon worker-1 avant cancel.

### Phase 3 — Kill prod runtime (J+2)
- **OVH MKS Prod** (3x B2-15, ~€120/mo) : delete cluster via OVH manager APRÈS Phase 1 PG dump committé.
- **OVH MKS Dev** (€58/mo) : delete cluster.
- **OVH LB** (€10/mo) : delete.
- **OVH managed PG** (€15/mo) : delete APRÈS dump + restore-test Phase 1.
- ArgoCD : non applicable (meurt avec le cluster).
- Keycloak : meurt avec le cluster (export Phase 1 conservé).

### Phase 4 — DNS + domaines (J+3)
- **Cloudflare zone `gostoa.dev`** : delete tous records DNS. Garder zone vivante 30j (au cas où) puis release.
- **Domaine `gostoa.dev`** : décision opérateur : (a) laisser expirer au renewal, (b) release immédiat, (c) parking pour revente. Coût €10/an = négligeable, pas bloquant pour le kill total.
- MCP integrations OAuth (Linear/Vercel/Cloudflare/Notion) : déconnecter via `claude.ai` settings (cleanup propre, pas obligatoire).

### Phase 5 — Archive repos (J+4)
- **Repos publics** (`stoa-platform/*`, `stoactl`) :
  - Update root README : section "⚠️ Project Archived" + lien post-mortem (si écrit) + Apache 2.0 reminder + "fork freely".
  - `gh repo archive stoa-platform/stoa` (puis stoa-docs, stoa-web, stoa-quickstart, stoactl).
  - Repos restent visibles, clonables, mais read-only.
- **Repos privés** (`PotoMitan/stoa-strategy`, `stoa-infra`) :
  - Backup tarball local Phase 1 déjà fait.
  - `gh repo archive` (reste visible à toi, plus modifiable, pas exposé public).
  - Alternative : `gh repo delete` si tu veux nettoyer ton GH compte (irréversible, ne le faire qu'après tarball Phase 1 vérifié).
- **Branches** : laisser, ça ne coûte rien sur repo archivé.

### Phase 6 — Tiers SaaS (J+5)
- **Linear** : export tickets en CSV (`linear-cli export` ou via UI Settings → Import/Export). Workspace : downgrade Free tier ou freeze. Pas urgent (Linear Free supporte 250 issues).
- **Vercel** : delete projets `stoa-web`, `stoa-docs` (si déployés). Compte reste, Free tier.
- **Cloudflare** : delete zone `gostoa.dev` après Phase 4. Compte reste, Free tier.
- **Notion** : si workspace dédié STOA → archive ou delete. Si dans workspace perso → leave as is.
- **GitHub Actions** : repo archive désactive les workflows automatiquement.
- **Sentry / Datadog / autres APM** : aucun connu à ce stade. Si activés silencieusement → cancel.
- **OAuth apps GitHub** (claude-linear-dispatch etc.) : révoquer dans Settings.

### Phase 7 — Post-mortem (J+7, OPTIONNEL)
- Doc interne `docs/post-mortem/2026-05-stoa-shutdown.md` : 6 mois, ~€12 K, pourquoi pas de client (positioning ? timing ? canaux ? GTM ?). Pour TOI, pas public. Sert au nouveau projet.
- Public (LinkedIn ou blog) : optionnel. Solo project mode = pas de pression community. Décision opérateur après le wind-down.

## Go / No-Go

**Go si**
- Phase 1 backups vérifiés (restore-test PG OK, gpg --decrypt OK sur sample).
- Aucun client live identifié (zéro tenant payant sur `oasis`/`oasis-gunters` — à confirmer J0).
- Nouveau projet validé en parallèle (opérateur a dit oui — pas bloquant pour shutdown mais utile pour identifier ce qui doit migrer Phase 1).

**No-Go si**
- Phase 1 révèle un client réel non documenté sur prod (consulter Linear/emails).
- Tarball stoa-strategy ne décrypte pas (regenerate clé GPG, ne PAS continuer).

## Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Regret 3 mois plus tard, vouloir re-provision | M | M | Tarballs Phase 1 = re-deploy possible en 1-2 jours (stoa-infra IaC complet) |
| Client surprise pendant wind-down | TF | H | Phase 0 inventory tenants prod, contact direct si trouvé |
| Backup PG corrompu non détecté | F | C | Phase 1 restore-test obligatoire |
| Domaine `gostoa.dev` perdu si squatté | F | M | Si valeur sentimentale/branding : renew 1 an supplémentaire (€10) et trancher plus tard |
| Cancel Contabo facturé mois suivant quand même | M | F | Acceptable, ~€80 perdus max |
| Repos archivés cassent un import externe (qui dépendrait du code) | TF | F | Apache 2.0, ils peuvent fork |
| Données prod recall obligation (RGPD) | F | M | PG dump local chiffré 1 an puis destruction documentée |

## Coûts cibles

| Composant | Avant (€/mo) | Après (€/mo) |
|---|---|---|
| OVH MKS Prod 3x B2-15 | €120 | 0 |
| OVH managed PG | €15 | 0 |
| OVH LB | €10 | 0 |
| OVH MKS Dev | €58 | 0 |
| OVH VPS fleet (11 + vault-vps) | €60 | 0 |
| OVH tooling-vps | €6 | 0 |
| OVH infisical-vps | €4.50 | 0 |
| Contabo HEGEMON 5x + runners 4x | €81 | 0 |
| Hetzner staging | €45 | 0 |
| Cloudflare | 0 (Free) | 0 |
| Vercel | 0 (Free) | 0 |
| Linear | ? (vérifier plan) | 0 (Free tier) ou cancel |
| Domaine `gostoa.dev` | ~€1/mo (€10/an) | 0 ou €1 si conservé |
| **Total** | **~€400** | **~€0-1** |

Économie : tout. Reste optionnel : ~€10/an domaine si garde.

## Calendrier

- **J0 (sam 2026-05-23)** : Phase 0 + 1 (backups + restore-test). **Aucun kill aujourd'hui.**
- **J+1 (dim)** : Phase 2 (VPS Contabo/Hetzner/OVH dev-fleet/HEGEMON).
- **J+2 (lun)** : Phase 3 (MKS prod + dev + PG + LB) — APRÈS restore-test Phase 1 confirmé vert.
- **J+3 (mar)** : Phase 4 (DNS).
- **J+4 (mer)** : Phase 5 (repos archive).
- **J+5 (jeu)** : Phase 6 (SaaS tiers).
- **J+7 (sam)** : Phase 7 post-mortem (optionnel).

Total : 1 semaine elapsed, ~4-6h Claude effectif (la Phase 1 backup + verify prend le plus de temps).

## Confirmation requise avant Phase 2

Phase 1 = backups uniquement, non destructive. **Avant chaque Phase 2-6, je m'arrête, je te montre les commandes exactes en clair, tu réponds GO ou NO-GO en prose.** Pas d'AskUserQuestion sur des actions irréversibles (`feedback_gates_plaintext.md`).
