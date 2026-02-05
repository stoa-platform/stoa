# Skill: Update Memory

## Quand utiliser

En fin de session, ou quand un jalon important est atteint. Met a jour memory.md avec l'etat courant.

## Workflow

### Step 1: Lire l'etat actuel
- Lire `memory.md`
- Verifier `git log --oneline -10` pour les commits recents
- Verifier `git status` pour les changements non commites

### Step 2: Mettre a jour les sections

#### Session State (table)
Deplacer les items:
- Taches terminees → DONE (avec commit hash)
- Taches en cours → IN PROGRESS
- Prochaines taches → NEXT
- Blocages → BLOCKED (avec raison)

#### Decisions This Sprint
Ajouter toute decision technique notable prise durant la session:
- Format: `YYYY-MM-DD: {decision courte}`

#### Known Issues
Ajouter tout probleme decouvert mais non resolu.

#### Notes
Ajouter du contexte utile pour la prochaine session.

### Step 3: Mettre a jour le header
```markdown
> Last updated: {YYYY-MM-DD} (Session N — {description courte})
```

### Step 4: Archiver si necessaire
Si memory.md depasse 100 lignes:
- Deplacer les items DONE de plus de 2 semaines vers `docs/archive/memory-{YYYY-MM}.md`
- Garder uniquement l'etat actif dans memory.md

## Format de reference

```markdown
# STOA Memory

> Last updated: YYYY-MM-DD (Session N — Description)

## Session State
| Status | Ticket | Description | Evidence |
|--------|--------|-------------|----------|
| DONE | CAB-XXXX | Description | commit abc1234 |
| NEXT | CAB-YYYY | Description | — |

## Decisions This Sprint
- YYYY-MM-DD: Decision description

## Known Issues
- Issue description

## Notes
- Context for next session
```
