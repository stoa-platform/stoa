# Skill: Fix Bug

## Quand utiliser

Quand on identifie un bug specifique avec des symptomes connus (ticket CAB-XXXX, erreur HTTP, crash, comportement incorrect).

## Workflow

### Step 1: Comprendre
- Lire la description du bug et les messages d'erreur
- Identifier le composant et les fichiers concernes
- Verifier memory.md pour du contexte lie

### Step 2: Reproduire
- Ecrire ou trouver un test qui reproduit le bug
- Verifier que le test echoue avant de fixer

### Step 3: Fixer
- Faire le changement minimal pour corriger la cause racine
- Ne PAS refactorer le code environnant
- Ne PAS fixer d'autres bugs dans le meme commit

### Step 4: Verifier
- Le test de reproduction doit passer
- Lancer la suite complete du composant concerne:
  - Python: `pytest --cov=src`
  - TypeScript: `npm run test`
  - Rust: `cargo test`
- Lancer le linting:
  - Python: `ruff check .`
  - TypeScript: `npm run lint`
  - Rust: `cargo clippy`

### Step 5: Commiter
- Format: `fix({scope}): {description} ({ticket-id})`
- Inclure la cause racine dans le body du commit
- Mettre a jour memory.md avec les details du fix

## Anti-Patterns
- Ne PAS fixer des problemes non lies dans le meme commit
- Ne PAS refactorer en meme temps
- Ne PAS sauter l'etape de reproduction
- Ne PAS elargir le scope au-dela du bug identifie
