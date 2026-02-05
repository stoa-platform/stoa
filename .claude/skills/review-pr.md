# Skill: Review PR

## Quand utiliser

Quand on doit faire une review de Pull Request. Peut etre invoque avec le numero de PR.

## Workflow

### Step 1: Charger le contexte
```bash
gh pr view {number}
gh pr diff {number}
gh pr checks {number}
```

### Step 2: Checklist de review

#### Fonctionnel
- [ ] Le code fait ce que le titre/description de la PR annonce
- [ ] Pas de scope creep (changements non lies)
- [ ] Les cas limites sont geres

#### Tests
- [ ] Nouveaux tests pour nouveau code
- [ ] Tests existants toujours verts
- [ ] Couverture >= 70% (Python), adequate (TS, Rust)

#### Qualite
- [ ] Respecte les conventions de code (voir .claude/rules/)
- [ ] Pas de code mort, imports inutilises
- [ ] Noms de variables/fonctions clairs
- [ ] Gestion d'erreurs adequate

#### Securite
- [ ] Pas de secrets en dur
- [ ] Validation des inputs aux frontieres
- [ ] Pas de vulnerabilites OWASP Top 10
- [ ] Docker multi-arch si Dockerfile modifie

#### Git
- [ ] Commit messages conventionnels
- [ ] Pas de fichiers sensibles commites (.env, *.pem)
- [ ] Branche correctement nommee

### Step 3: Verdict

**Go** — Approve la PR
**Fix** — Request changes avec commentaires specifiques (fichier + ligne)
**Refaire** — La PR manque l'objectif, fermer et recreer

### Step 4: Commenter
- Commenter sur les lignes specifiques, pas des commentaires generiques
- Distinguer: bloquant (must fix) vs suggestion (nice to have)
- Citer le pattern/convention viole si applicable

## Regles
- Verdict binaire: Go / Fix / Refaire — pas de "peut-etre"
- Toujours verifier les checks CI avant de reviewer le code
- Si la PR touche les zones interdites (terraform, workflows) → attention maximale
