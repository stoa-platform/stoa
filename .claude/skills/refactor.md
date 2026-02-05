# Skill: Refactor

## Quand utiliser

Quand on restructure du code sans changer le comportement visible. Toujours garder les tests verts.

## Workflow

### Step 1: Definir le perimetre
- Quoi refactorer et pourquoi
- Quels fichiers sont concernes
- Quelle est l'interface publique a preserver

### Step 2: Baseline
- Lancer TOUS les tests du composant
- Verifier qu'ils passent AVANT de commencer
- Si des tests echouent deja → fixer d'abord (session separee)

### Step 3: Refactorer incrementalement
Pour chaque changement atomique:
1. Faire le changement
2. Lancer les tests
3. Si les tests passent → commiter
4. Si les tests echouent → revert et reessayer differemment

### Step 4: Verification finale
- Tous les tests passent
- Linting OK
- Types OK
- Pas de code mort ajoute (supprimer les imports inutilises, etc.)

### Step 5: Commiter
- Format: `refactor({scope}): {description}`
- Decrire le "pourquoi" dans le body du commit

## Regles
- **Jamais de changement de comportement** — si le refactor change l'API publique, c'est une feature
- **Tests verts a chaque etape** — pas de "cassons tout puis reparons"
- **Petits commits** — un commit par changement atomique
- **Pas de fix de bug** dans un refactor — sessions separees
- **Pas d'ajout de feature** dans un refactor — sessions separees
