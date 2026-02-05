# Skill: Create ADR

## Quand utiliser

Quand une decision architecturale importante est prise et doit etre documentee. Les ADRs vivent dans le repo **stoa-docs**.

## Workflow

### Step 1: Identifier le prochain numero
- Verifier le dernier ADR dans `stoa-docs/docs/architecture/adr/`
- Le nouveau sera le suivant (ex: si le dernier est ADR-030, le nouveau est ADR-031)

### Step 2: Creer le fichier
Chemin: `stoa-docs/docs/architecture/adr/adr-{NNN}-{kebab-case-title}.md`

### Step 3: Remplir le template

```markdown
# ADR-{NNN}: {Title}

## Metadata
| Field | Value |
|-------|-------|
| **Status** | 📋 Draft |
| **Date** | {YYYY-MM-DD} |
| **Author** | {author} |

## Context
{Pourquoi cette decision est necessaire. Probleme, contraintes, alternatives.}

## Decision
{Ce qui a ete decide. Inclure des diagrammes si utile.}

## Consequences
### Positive
{Benefices}
### Negative
{Inconvenients}
### Mitigations
{Comment reduire les inconvenients}

## References
{Liens vers ADRs lies, standards, documentation externe}
```

### Step 4: Mettre a jour l'index
Ajouter l'entree dans `stoa-docs/docs/architecture/adr/README.md` dans la section appropriee:
- Platform & Infrastructure
- Security & Compliance
- MCP & AI Gateway
- Business & Strategy
- Developer Experience & AI Workflow

### Step 5: Commiter
- Format: `docs(adr): ADR-{NNN} {title}`
- Dans le repo stoa-docs

## Regles
- Les ADRs vivent dans **stoa-docs**, pas dans stoa
- Statut initial: 📋 Draft (passe a ✅ Accepted apres validation)
- Un ADR par decision — pas de megas ADRs fourre-tout
