# Rewrite vs Patch — Context rot mitigation

> **Règle binaire dans CLAUDE.md.** Ce fichier est le protocole détaillé (lu on-demand).

## Pourquoi cette règle existe

Recherche 2023-2026 sur l'efficacité des approches d'édition LLM :

- **Aider benchmarks** : search/replace échoue sur 20-30% des tentatives sur codebases évoluées. Pattern matching fragile.
- **Unified diff vs search/replace** : unified diff a rendu GPT-4 Turbo 3× moins paresseux (laziness score 20% → 61%). Le format compte autant que le choix patch-vs-rewrite.
- **Liu et al. "Lost in the Middle" (2023)** : la performance dégrade sévèrement dès que le contexte dépasse 50% de remplissage. Les tokens du milieu "se perdent".
- **Databricks Mosaic (2025)** : correctness des agents chute après 32K tokens. Agents favorisent actions répétitives issues de leur historique.
- **Veseli et al. (2025)** : au-delà de 50% de contexte, dégradation par distance depuis la fin (récents > milieu > anciens). Les tokens anciens de CLAUDE.md deviennent moins influents que les dernières erreurs.

Effet combiné : chaque Edit raté laisse des traces (tool calls échoués, corrections, assumptions fausses) qui polluent le contexte et biaisent les décisions suivantes. Après 2-3 Edits ratés sur le même fichier, l'agent tourne en rond — il "voit" le fichier à travers une accumulation de fausses versions.

## Décisions binaires (seuils)

| Signal | Action |
|--------|--------|
| 1 Edit échoué | Re-lire le fichier, corriger le pattern, retry une fois |
| **2 Edits échoués consécutifs sur même fichier** | **STOP. Write (rewrite complet) ou subagent.** |
| 3+ itérations sur même fichier en session | `/clear` ou délégation subagent (contexte pollué) |
| Diff estimé >30% du fichier | Write direct dès le départ (pas de série d'Edit) |
| Fichier >1500 lignes | Ne pas rewrite inline — split ou subagent |
| Contexte session >70% | Subagent même pour rewrite simple (pollution bias) |

## Enforcement

**3 niveaux actifs** :

1. **Documenté** : CLAUDE.md section "Rewrite vs Patch" (auto-chargé) + `feedback_rewrite_after_fail.md` (persiste cross-sessions)
2. **Détecté** : hook `post-edit-failure-tracker.sh` (PostToolUse Edit)
   - Tracke fails par fichier dans `.claude/state/edit-attempts.json`
   - Injecte `systemMessage` à ≥2 fails consécutifs
   - Second warning à ≥5 Edit total même fichier (risque pollution)
   - Reset sur SessionStart + PostCompact
3. **Exécuté** : skill `/rewrite <file> <intent>` force le Write propre

## Signals de failure (ce que le hook détecte)

Le hook lit `tool_response` post-Edit et flag error si :
- `tool_response.is_error == true`
- `tool_response.error` non vide
- String response contient `error|failed|not found|does not match` (case-insensitive)

Faux positifs possibles mais rares (le hook n'est qu'advisory, `exit 0` toujours).

## Bypass

Pas de kill-switch dédié. Si besoin d'un bypass ponctuel :
- Ignorer le systemMessage (il est advisory, pas bloquant)
- Ou reset manuel : `echo '{}' > .claude/state/edit-attempts.json`

Si tu te retrouves à bypasser régulièrement, c'est un signal que le seuil est mal calibré — ajuster dans le hook plutôt que router autour.

## Interaction avec les autres règles

- **Context budget (60/80/90)** : complémentaire. Le budget mesure le volume, cette règle mesure la qualité (échecs répétés). Un contexte à 40% mais avec 3 Edits ratés est aussi pollué qu'un contexte à 80% propre.
- **PR >300 LOC interdit** : un rewrite peut pousser un fichier au-delà. Si le rewrite lui-même fait >300 LOC de diff, c'est le signal qu'il fallait un subagent, pas un rewrite inline.
- **Test-first (fix/feat)** : un rewrite doit passer les tests existants. Si non, c'est du refactor déguisé — séparer.

## Sources

- [Aider — Unified diffs make GPT-4 Turbo 3X less lazy](https://aider.chat/docs/unified-diffs.html)
- [Aider — Edit formats benchmarks](https://aider.chat/docs/benchmarks.html)
- [Liu et al. 2023 — Lost in the Middle](https://arxiv.org/abs/2307.03172)
- [Diff-XYZ benchmark (arXiv 2510.12487)](https://arxiv.org/html/2510.12487v1)
- [Context Rot: Why AI Gets Worse the Longer You Chat](https://www.producttalk.org/context-rot/)
