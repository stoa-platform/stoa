# Skill: Implement Feature

## Quand utiliser

Quand on implemente une nouvelle fonctionnalite (ticket CAB-XXXX). Toujours planifier avant de coder.

## Workflow

### Step 1: Explorer
- Comprendre le contexte: lire les fichiers concernes
- Identifier les composants impactes
- Verifier les patterns existants dans le codebase

### Step 2: Planifier (ne pas coder)
- Proposer 2-3 approches si la feature est complexe
- Choisir l'approche la plus simple qui repond au besoin
- Decrire le plan en 5 etapes max
- Attendre validation ("Go") avant de coder

### Step 3: Implementer
Pour chaque etape du plan:
1. Coder l'etape
2. Ecrire les tests
3. Verifier que tout passe
4. Commiter: `feat({scope}): {description} ({ticket-id})`

### Step 4: Validation finale
- Tous les tests passent (composant + tests impactes)
- Linting OK
- Types OK (mypy/tsc)
- Pas de regression

### Step 5: Mettre a jour le contexte
- memory.md: marquer la feature comme DONE
- Si decision architecturale importante: noter dans docs/decisions/DECISIONS.md

## Regles
- 1 feature par session — pas de scope creep
- Commiter toutes les 30 min minimum
- Si bloque > 10 min → noter le blocage et passer au suivant
- Respecter les patterns existants du composant (voir CLAUDE.md du composant)
