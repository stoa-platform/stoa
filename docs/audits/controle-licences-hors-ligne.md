<!-- Copyright 2026 Christophe Aboulicam -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Brouillon de contrôle CI des licences

Le contrôle est désactivé par `scripts/ci/licences-policy.json` (`enabled: false`).
Aucun workflow n'est ajouté. Aucun gestionnaire de paquets ni réseau n'est utilisé.
Prérequis : Python 3.11 ou supérieur, sans installation de dépendances.

Préparer dans le checkout de CI un inventaire CSV et son `sources.json`, issus
ensemble de la collecte hors ligne et relus. Par défaut, ces deux fichiers sont
attendus dans `audit/licences/`. Le rapport d'audit décrit la collecte et les limites.
Les fichiers de preuve du job restent séparés du patch pour permettre leur revue.

```bash
python3 -B -m unittest discover -s tests/licences -v
python3 -B scripts/ci/check_licences_offline.py
# Activation explicite, dans un job CI existant préalablement approuvé :
python3 -B scripts/ci/check_licences_offline.py --enforce \
  --root . --inventory audit/licences/inventaire-licences.csv \
  --snapshot audit/licences/sources.json
```

L'appel sans `--enforce` affiche son état désactivé. Une activation durable peut
être réalisée par `enabled: true` après revue de la politique et des preuves.
Codes : `0` succès ou désactivé (message explicite), `1` licence interdite ou
à confirmer, `2` données invalides, inventaire altéré ou sources modifiées.
Un ajout ou retrait de manifeste impose une nouvelle collecte et une revue.

Le CSV comporte au moins `ecosystem,name,version,license,source`. Le snapshot
JSON comporte `schema: 1`, `inventory_sha256` et `sources`, dictionnaire de chemins
relatifs vers leurs SHA-256. Les licences sont réévaluées; la colonne `status`
éventuelle du CSV n'est pas utilisée comme décision de confiance.

`AND` impose toutes les licences; `OR` permet une branche permissive. `WITH`
reste à confirmer sauf si l'expression complète a été approuvée explicitement.
BUSL et BSL sont distincts : BSL-1.0 désigne Boost. MPL, CC-BY, Python-2.0 et
BlueOak restent à confirmer dans cette politique initiale conservatrice.
Les conditions d'attribution et de redistribution demeurent applicables même
pour une licence classée conforme.

Les empreintes détectent la péremption, pas une omission commise lors de la
collecte ni une altération simultanée du CSV et de son snapshot. La revue des
preuves, du collecteur et de leur provenance est nécessaire. Le contrôle ne
reconstruit pas les graphes manquants et ne constitue pas un avis juridique.
