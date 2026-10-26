# Primitives d’accessibilité — patch brouillon

`Modal` utilise un élément `dialog` ouvert par `showModal()`, rendu dans un portail
sur `document.body`. Le navigateur isole ainsi l’arrière-plan. `ModalTitle` donne
un nom unique au dialogue et reçoit le focus initial. La primitive gère Tab,
Maj+Tab, Échap, les ouvertures imbriquées, le retour au déclencheur et le verrouillage
du défilement. `closeDisabled` suspend Échap et l’événement natif `cancel` pendant
un traitement. Les fonds et boutons conservent leurs gestionnaires métier.

Cette implémentation nécessite un navigateur prenant en charge `HTMLDialogElement`
et `showModal`. Les tests jsdom simulent seulement l’état ouvert : le véritable
isolement natif, les lecteurs d’écran et le rendu restent à vérifier au navigateur.

`Field`, `FieldLabel`, `FieldInput`, `FieldSelect` et `FieldTextarea` partagent un
identifiant généré par instance. Chaque contrôle répété doit avoir son propre
`Field`. Les erreurs de contrainte native et les erreurs explicites d’un champ
ajoutent `aria-invalid` et relient le message par `aria-describedby`. Une erreur de
soumission générale décrit le `Form` via `FormError`, sans déclarer tous les champs
invalides. Les groupes de choix utilisent `fieldset` et `legend`.

`RowAction` fournit un bouton natif dans une cellule, avec un indicateur de focus.
Son clic ne se propage pas au gestionnaire de la ligne. Les actions secondaires
restent indépendantes. Le composant `Button` utilise `type="button"` par défaut ;
la soumission demande un `type="submit"` explicite.

## Contraste des couleurs opaques

Pour chaque canal sRGB normalisé `c`, la valeur linéaire vaut `c / 12,92` si
`c ≤ 0,04045`, sinon `((c + 0,055) / 1,055)^2,4`.
La luminance relative vaut `L = 0,2126 R + 0,7152 G + 0,0722 B`.
Le rapport vaut `(Lmax + 0,05) / (Lmin + 0,05)` ; les assertions utilisent les
valeurs non arrondies et le seuil demandé de `4,5:1`.

| Usage                                                  |               Avant |               Après |
| ------------------------------------------------------ | ------------------: | ------------------: |
| Texte blanc sur bouton normal                          | `#059669` : 3,768:1 | `#047857` : 5,484:1 |
| Texte blanc sur bouton sombre                          | `#10b981` : 2,537:1 | `#047857` : 5,484:1 |
| Texte blanc sur bouton au survol                       |                   — | `#065f46` : 7,684:1 |
| Texte atténué sur blanc                                | `#a3a3a3` : 2,523:1 | `#525252` : 7,814:1 |
| Texte atténué sur `neutral-50` / `neutral-100`         |                   — |   7,486:1 / 7,167:1 |
| Texte atténué sombre sur `neutral-800` / `neutral-900` |                   — |   5,999:1 / 7,107:1 |

Le jeton `muted` dépend de `--stoa-text-muted`, défini dans les deux applications :
`#525252` en clair et `#a3a3a3` sous `.dark`. Les anciens usages directs de
`text-neutral-400` deviennent `text-muted`. Les couleurs de statut, les autres
nuances de gris, les transparences, les superpositions et les états désactivés ne
sont pas couverts par ces calculs et demandent une revue du rendu.

Les tests de régression se trouvent dans les suites Vitest des deux applications,
notamment `components/shared/{Modal,Button,Field,RowAction,Contrast}.test.*` côté
console, et `CreateAppModal.accessibility.test.tsx` côté portail. Les titres sont
définis par route dans `RouteMetadata`, et `DocumentMetadata` synchronise `title`
et `html[lang]` avec la langue active. Les textes des écrans ne sont pas traduits
par ce patch.

Ce document ne constitue aucune déclaration de conformité.
