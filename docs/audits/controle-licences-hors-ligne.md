<!-- Copyright 2026 Christophe Aboulicam -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Contrôle local des licences — brouillon CI

Python 3.11 ou supérieur, bibliothèque standard uniquement. Aucun gestionnaire de
paquets, cache du compte utilisateur, commande Git ou service distant n'est appelé
par les contrôles. La collecte décrit les déclarations locales et leurs lacunes;
elle ne constitue ni une SBOM de livraison complète ni un avis juridique.

## Exécution et activation

```bash
python3 -B -m unittest discover -s tests/licences -v
python3 -B scripts/ci/check_licences_offline.py --root . --report license-report.json
python3 -B scripts/ci/check_licences_offline.py --root . --enforce --report license-report.json
# Autre syntaxe: --mode warn, --mode deny (1er temps) ou --mode enforce
```

Le mode par défaut est `warn` dans `scripts/ci/licences-policy.json`. Le contrôle
collecte réellement les sources dans ce mode. Il ne dispose plus d'un mode
« désactivé ». Le champ historique `enabled: true`, s'il est conservé dans une
configuration externe, active le blocage; `enabled: false` signifie avertissement.
`--mode` prime sur la configuration et `--enforce` impose le blocage.

| Situation | `warn` (défaut) | `deny` (1er temps) | `enforce` (2e temps) |
| --- | --- | --- | --- |
| Déclarations admises ou dérogations ciblées valides | 0 | 0 | 0 |
| Licence de `phase1_denied_prefixes` (AGPL, SSPL, BUSL, Elastic, non commerciale, commerciale ou propriétaire) | 0, annotation et rapport | 1 | 1 |
| Autre licence interdite par politique ou À CONFIRMER | 0, annotation et rapport | 0, annotation et rapport | 1 |
| Entrées illisibles, invalides, périmées; périmètre vide | 0, annotation « non concluant » | 2 | 2 |

Le mode `warn` ne fait jamais échouer la CI : le script rend 0 et le job
déclare ses deux étapes en `continue-on-error`. Le blocage se fait en deux temps :
`deny` bloque d'abord les seules licences de `phase1_denied_prefixes`, puis
`enforce` bloque tout ce qui n'est pas conforme, une fois les références
À CONFIRMER résolues et les dérogations validées. `BSL-1.0` (Boost) est admise;
la Business Source License est `BUSL-*`.

Le job existant **License Compliance** dans `required-checks.yml` conserve son nom.
Il exécute les tests puis le contrôle local et conserve le rapport avec
`if: always()`. La variable de dépôt `LICENSES_MODE` (`warn`, `deny` ou `enforce`)
choisit le mode; absente, c'est `warn`. La modifier est une action
d'administration distincte de ce changement. Aucune variable n'est modifiée ici.
Le job impose son mode CLI: changer seulement le JSON ne change pas le mode de ce
workflow. Un appel local sans option utilise le JSON.

Après checkout, les commandes de tests et de contrôle fonctionnent sans réseau.
Le checkout, le téléversement du rapport et les autres jobs existants restent des
opérations GitHub Actions: le workflow entier n'est pas un environnement isolé du
réseau. L'ancien scan Trivy du job licences est remplacé; les jobs de vulnérabilités
et de SBOM demeurent indépendants. La protection effective de branche et la
configuration des variables doivent être vérifiées par un administrateur.

## Périmètre et garanties

Le rapport JSON `schema: 2` conserve les références, leur `original_status`, leur
`status`, les preuves locales, les compteurs, les SHA-256 des sources et celui de
la politique. Le résultat `findings` ne signifie jamais une conformité, même si
le code de sortie du mode avertissement est zéro. Une dérogation est comptée
séparément de la conformité. Une erreur remplace le rapport demandé par un état
`invalid-input`, pour éviter de relire un ancien rapport favorable.

| Sources | Lecture locale | Limites conservées explicitement |
| --- | --- | --- |
| npm | package.json et package-lock v2/v3; `license` par occurrence; rapprochement sur nom/version/integrity identiques | Absence/divergence du lock, liens locaux, licence manquante |
| Rust | Cargo.toml, dépendances normales/build/dev/cibles/workspace; paquets de Cargo.lock; licence du projet; rapprochement exact des crates locales sans source registry | Résolution features/cibles/patch/workspace non exécutée; aucun transfert de licence du projet aux crates registry |
| Go | require de go.mod; coordonnées de go.sum distinctes | replace/exclude, sélection effective et licence non déterminées par les sommes |
| Python | dépendances PEP 621, extras, groupes PEP 735 simples, build-system, Poetry, requirements | Contraintes et marqueurs non résolus, transitifs et includes non reconstruits; setup/Pipfile et locks non pris en charge marqués incomplets |
| Images | FROM de tous les stages Dockerfile; références image/repository YAML; installations explicites apt/apk/pip/cargo | Lecture YAML lexicale, sans rendu ni rapprochement automatique repository/tag; variables, couches et paquets système à confirmer |
| Helm | Chart.yaml/Chart.lock; Chart.yaml imbriqués; textes de licence et références image/repository dans les archives tgz | Lecture lexicale sans rendu Helm; identifiant SPDX nécessaire dans les textes locaux; aucune licence d'image déduite d'une licence de chart |

Un marqueur `[graphe incomplet]` reste bloquant. Les occurrences d'un manifeste,
d'un lock, d'une somme et d'un graphe incomplet peuvent se recouper: les totaux
ne comptent pas des bibliothèques distinctes ou effectivement embarquées. Les
verrous non interprétés et les wheels ne sont pas considérés comme vérifiés.
Les scripts Python à dépendances inline, les syntaxes d'installation complexes,
les paquets de base et les dépendances générées demandent des collecteurs
complémentaires. Les installations RUN reconnues sont recensées, sans garantie
d'exhaustivité ni résolution de leurs transitifs. Ils sont notamment couverts par les lacunes de composition des
images, sans prétendre les énumérer.

Les répertoires Git, identifiants, outils d'agents, environnements virtuels,
node_modules, vendor, target, build et dist sont élagués avant le parcours. Les
fichiers d'environnement et d'identifiants sont exclus. Les liens de fichiers
sélectionnés sont refusés avant lecture; les répertoires liés ne sont pas suivis.
Les noms/références collectés sont filtrés pour masquer identifiants d'URL,
adresses et certains noms d'hôtes locaux. Le rapport contient encore des
coordonnées de composants et ne doit pas être publié sans revue du contenu.

## Preuves de licences présentes localement

`audit/licences/local-evidence.json` est une liste de rapprochements **relus**.
Elle est vide à la livraison. Elle permet de lire des métadonnées ou textes locaux
sans parcourir les caches du compte utilisateur. Une entrée lie exactement:

```json
{
  "schema": 1,
  "entries": [
    {
      "ecosystem": "cargo",
      "name": "exemple",
      "version": "1.2.3",
      "source": "composant/Cargo.lock",
      "source_sha256": "EMPREINTE_SHA256_DU_LOCK",
      "path": "audit/licences/evidence/exemple/Cargo.toml",
      "sha256": "EMPREINTE_SHA256_DU_FICHIER",
      "kind": "cargo",
      "reason": "Rapprochement revu avec la source et l'artefact exacts."
    }
  ]
}
```

Cet exemple est un gabarit, à compléter après revue. Les deux empreintes sont
obligatoires et vérifiées. Le chemin doit rester dans le dépôt sans lien
symbolique ni accès à des identifiants. La version et le manifeste source doivent
correspondre exactement à une référence collectée; doublons, preuves inutilisées
ou altérées provoquent un code 2. Si plusieurs origines/occurrences partagent
la même identité, préciser `locator` avec la valeur exacte du rapport. Une preuve
ambiguë est refusée. Une déclaration locale contradictoire conserve les deux
expressions et le statut À CONFIRMER.

Formats disponibles:

- `cargo`: lit `package.name`, `version` et `license` d'un Cargo.toml local.
- `python`: lit Name/Version et License-Expression, puis License, d'un METADATA
  local. Un texte libre non reconnu reste À CONFIRMER.
- `spdx-text`: lit un identifiant SPDX unique dans un texte local; utilisable
  notamment pour Go et les images. Des identifiants différents restent inconnus.
  Pour OCI, la référence doit être immuable, avec `@sha256:` et 64 chiffres
  hexadécimaux. Une preuve sur un tag mutable est refusée.

Un texte sans identifiant SPDX exploitable reste À CONFIRMER. Il faut alors
faire relire le texte et compléter le collecteur, avec un test, plutôt qu'inventer
une licence. Les fichiers license-file, les textes d'attribution multiples, les
licences par sous-répertoire et les images multi-licences demandent cette revue.
La licence du chart, du projet ou de l'image de base n'est pas celle de toutes
ses dépendances. Le contenu et la provenance de la preuve doivent être relus:
une empreinte détecte une modification, elle n'authentifie pas le fournisseur.

## Liste des exceptions justifiées

La liste effective est `exceptions` dans `scripts/ci/licences-policy.json`.
**Elle est vide: aucune dérogation réelle n'a été autorisée.** Les inconnues ne
sont pas exemptées collectivement pour rendre le mode bloquant vert.

Une dérogation doit préciser des chaînes non vides pour tous ces champs:

| Champ | Portée |
| --- | --- |
| ecosystem, name, version, source, license | Correspondance exacte avec une référence; l'expression de licence reste visible |
| locator (si ambiguïté) | Origine ou occurrence exacte telle que collectée; aucune dérogation ne se propage silencieusement à une autre origine |
| source_sha256 | Empreinte du manifeste/lock courant |
| reason | Justification concrète et obligations résiduelles |
| approved_by | Responsable ayant réellement approuvé |
| decision | Référence de la décision conservée pour revue |
| expires | Date ISO AAAA-MM-JJ; valide jusqu'à la fin de cette date selon l'horloge du runner |

Les jokers, doublons, dates passées, entrées inutilisées/superflues et exemptions
de graphes incomplets sont refusés. Une modification du manifeste impose une
nouvelle revue de la dérogation. Les anciens `allowed_exceptions` SPDX globaux
ne sont plus acceptés dans la configuration CLI, car dépourvus de justification
et de portée. Le parseur SPDX conserve AND, OR, WITH; aucune exception WITH n'est
supprimée silencieusement. Les familles interdites sont un choix de politique
conservateur, pas une conclusion juridique universelle d'incompatibilité.

## Compatibilité avec l'inventaire d'audit précédent

```bash
python3 -B scripts/ci/check_licences_offline.py --enforce --root . \
  --inventory audit/licences/inventaire-licences.csv \
  --snapshot audit/licences/sources.json --report license-report.json
```

CSV et snapshot restent optionnels, mais obligatoires ensemble. Leurs empreintes
et le périmètre sont revérifiés selon le contrat historique. Les statuts du CSV
ne sont pas crus. Les changements de sources imposent de régénérer et relire
l'inventaire; cette option ne fournit pas de résolution supplémentaire.
Le mode par défaut sans CSV effectue une collecte fraîche à chaque exécution.

## Documents dans les distributions

Les deux listes d'archives Go incluent `LICENSE*` et `NOTICE*`; `extra_files`
les transmet aussi au contexte Docker temporaire de GoReleaser. Les Dockerfile
publiés concernés les copient dans `/usr/share/licenses/stoa/` dans le dernier
stage: API, console, portail, gateway, Keycloak, stoactl et moniteur TLS. La
variante Dockerfile.connect reçoit également les documents.

Les workflows préparent les fichiers dans leurs contextes avant build. Pour un
build local des composants utilisant un contexte de sous-répertoire:

```bash
python3 -B scripts/ci/release_legal.py --dest stoa-gateway
# Puis le build habituel, avec les outils et dépendances disponibles.
```

La préparation copie exactement les deux fichiers racine et refuse d'écraser un
contenu différent. Aucune attribution ni aucun en-tête de titulaire n'est réécrit.
Les copies temporaires ne sont pas des notices de dépendances tierces.
Les images de développement et les Dockerfile auxiliaires sans publication
identifiée n'ont pas tous été modifiés.

Le chart de plateforme reçoit les deux fichiers avant `helm package`, puis le
workflow contrôle leur présence et leurs octets dans le tgz. Les bundles `dist`
téléversés par le workflow Node réutilisable et l'artefact binaire supplémentaire
reçoivent les mêmes documents. Les archives sources GitHub proviennent des
sources racine qui contiennent déjà les deux fichiers. Il n'existe pas ici de
pipeline de publication de wheel/sdist à corriger; tout nouveau packaging devra
appliquer la même obligation et inspecter l'artefact final.

```bash
python3 -B scripts/ci/release_legal.py --archive chemin/vers/artefact.tar.gz
# Accepte aussi zip et tgz, sans extraction sur disque.
```

Les tests créent et inspectent de vraies archives tar/zip et testent les absences,
altérations et conflits. Ils ne remplacent pas l'inspection des images finales ni
un build réel Helm/GoReleaser. Les attributions tierces, leur contenu et leurs
obligations de redistribution restent à traiter avec les artefacts exacts.
