# Skill: Audit Component

## Quand utiliser

Quand on veut analyser un composant sans le modifier. Audit de code, detection de problemes, recommandations.

## Mode: READ-ONLY — Ne modifier aucun fichier

## Workflow

### Step 1: Identifier le scope
- Quel composant auditer (control-plane-api, mcp-gateway, portal, etc.)
- Quel angle: securite, performance, qualite de code, architecture, dette technique

### Step 2: Lire le contexte
- CLAUDE.md du composant
- Structure des fichiers et dependances
- Tests existants et couverture
- Configuration (pyproject.toml, package.json, Cargo.toml)

### Step 3: Analyser
Selon l'angle choisi:

**Qualite de code:**
- Patterns coherents? Violations des conventions?
- Code duplique? Abstractions manquantes?
- Gestion d'erreurs adequate?
- Tests suffisants? Cas limites couverts?

**Securite:**
- Injection SQL, XSS, CSRF?
- Secrets en dur?
- Validation des inputs aux frontieres?
- Dependances vulnerables?

**Architecture:**
- Couplage excessif entre modules?
- Responsabilites bien separees?
- Interfaces claires?
- Patterns documentes dans les ADRs?

**Performance:**
- Requetes N+1?
- Caching adequat?
- Serialisation efficace?
- Connections poolees?

### Step 4: Rapport
Produire un rapport structure:
```
## Audit: {Composant} — {Angle}
### Etat actuel
### Forces
### Problemes identifies (par severite: P0/P1/P2/P3)
### Recommandations
### Impact ADR (nouvelle decision a documenter?)
```

## Regles
- NE JAMAIS modifier de fichiers
- Toujours citer les chemins de fichiers et numeros de ligne
- Prioriser les problemes par severite
- Proposer des actions concretes, pas des generalites
