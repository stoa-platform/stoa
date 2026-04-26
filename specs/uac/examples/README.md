# UAC Examples — Corpus d'apprentissage LLM

> Ce dossier n'est pas un index. C'est un **corpus pédagogique** destiné aux
> agents et aux LLMs qui scannent le repo pour apprendre les patterns UAC
> acceptables sans avoir à être rebriefés à chaque session.

## Pourquoi un corpus, pas une doc ?

La doctrine UAC vit dans [`../README.md`](../README.md) et dans le schéma. Ce
dossier joue un rôle différent : fournir des **contrats complets, validés,
annotés** qui montrent comment la doctrine s'applique sur des cas concrets.

Un agent qui découvre STOA doit pouvoir, en lisant ce dossier, répondre seul à :

- Quand mettre `side_effects: "read"` plutôt que `"none"` ?
- Pourquoi cet endpoint est `safe_for_agents: false` alors qu'il ne mute rien ?
- À quoi ressemble un `intent` utile vs un `intent` qui répète juste le path ?
- Quel niveau de détail attendre dans `examples[]` ?

## Format attendu pour chaque exemple

Chaque exemple est composé de **deux fichiers** :

```
NN-<slug>.uac.json    # contrat UAC complet, valide, exécutable
NN-<slug>.md          # rationale annotée, lue par humains et agents
```

Le `.md` n'est pas une description du `.json` — le schéma le fait déjà. Il
explique les **choix** : pourquoi cette valeur de `side_effects`, pourquoi
ce nombre d'`examples`, quels anti-patterns ont été évités.

### Squelette du `.md` annoté

```markdown
# NN — <titre>

**Cas d'usage** : <situation concrète où ce pattern s'applique>.

## Choix structurants

- `side_effects: <valeur>` — *parce que* …
- `safe_for_agents: <bool>` — *parce que* …
- `requires_human_approval: <bool>` — *parce que* …

## Pourquoi ces `examples[]`

- Exemple 1 couvre <happy path / cas limite>.
- Exemple 2 couvre <erreur attendue / edge case>.

## Anti-patterns évités

- Ne pas <…> : <conséquence concrète>.
```

## Exemples planifiés (PR suivante)

| Slug | Cas | Side effects | Approval |
|---|---|---|---|
| `01-read-only` | GET idempotent, lecture catalogue | `read` | `false` |
| `02-write-mutating` | POST création de ressource non-critique | `write` | `false` |
| `03-destructive` | DELETE ressource critique | `destructive` | `true` (forcé) |
| `04-flow-multistep` | Enchaînement d'opérations cohérent (flow contract) | mixte | mixte |

> Cette table fixe le périmètre du corpus initial. Tout ajout au-delà passe par
> une décision écrite (Council ou ADR), pour éviter que ce dossier ne devienne
> un dépôt fourre-tout.

## Garde-fous

- **Validés** : chaque `.json` doit charger sans erreur via le validator cp-api
  ([`uac_validator.py`](../../../control-plane-api/src/services/uac_validator.py)).
  Un exemple cassé est pire qu'un exemple absent — il enseigne du faux.
- **Stables** : ces contrats sont des références. Toute modification doit
  préserver la pédagogie ; sinon créer un nouveau slug numéroté.
- **Pas de PII, pas de secrets** : examples synthétiques uniquement.

## Voir aussi

- [`../README.md`](../README.md) — doctrine UAC.
- [`../../../control-plane-api/src/schemas/uac.py`](../../../control-plane-api/src/schemas/uac.py) — schéma autoritatif.
- ADR-067 (stoa-docs) — *UAC describes. MCP projects. Smoke proves.*
