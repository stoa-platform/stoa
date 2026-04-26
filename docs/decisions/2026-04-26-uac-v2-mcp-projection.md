---
id: decision-2026-04-26-uac-v2-mcp-projection
plan_ref: docs/plans/2026-04-26-uac-v2-mcp-projection.md
challenger: "GPT-5.5 Thinking (ChatGPT review, synthesised by Christophe)"
verdict: REFRAME
decision_gate_log: "#9"
---

# Decision — UAC V2, projection MCP de la metadata `endpoint.llm`

## Challenger output (verbatim)

> GO sur l'idée. NO-GO sur PR 2 Rust obligatoire tout de suite.
> Tu dois d'abord prouver la valeur côté chemin réellement utilisé.
>
> **Ajustement recommandé :**
>
> - **PR 1 — Python generator uniquement.**
>   Si `endpoint.llm` existe : description MCP enrichie. Sinon : fallback legacy inchangé. Tests `avec/sans llm`.
> - **PR 2 — Smoke + canary.**
>   `demo-httpbin.uac.json` + `endpoint.llm`. `tools/list` contient `Intent:` + `Side effects:`. Là tu prouves la chaîne utile.
> - **PR 3 — Rust parity seulement si nécessaire.**
>   Avant de modifier Rust, répondre à l'assumption 4 : *"le Rust generator est-il réellement utilisé dans le chemin démo/prod ?"* Si oui → PR Rust. Si non → ticket backlog, pas maintenant.
>
> **Point important :** la spec MCP n'est pas vérifiée pour `examples` au niveau tool. En V1, ne pas pousser `examples` comme champ structuré. Faire simple : `description = summary + intent + side_effects`. Éventuellement `Examples: ...` en texte, mais pas comme contrat MCP normatif.
>
> **Go criteria recadré :** "tools/list expose Intent + Side effects sur le canary, sans casser les tools legacy." Pas "3 PRs en 7 jours".
>
> **Logique à garder :** preuve d'abord, parité ensuite, gouvernance plus tard.

## Arbitrage

- **Verdict :** REFRAME
- **Reframe applied :**
  - Découplage du Rust generator (PR 3 conditionnelle, non bloquante).
  - Ordre des PRs : Python → Smoke+canary → Rust. La preuve de valeur passe avant la parité.
  - Suppression du push structuré d'`examples` au niveau tool MCP (spec non vérifiée). Repli sur description texte.
  - Go criteria axé sur le résultat observable (`Intent:` + `Side effects:` dans `tools/list` du canary) plutôt que sur le calendrier.

## Conditions de réouverture pour PR 3 (Rust parity)

PR 3 (Rust generator) revient à l'agenda **uniquement si l'un des trois signaux est observé** :

1. Le chemin gateway → `tools/list` en prod consomme effectivement la projection Rust (à vérifier par lecture du code d'appel + un test runtime).
2. Le canary cp-api est mergé et un client agent (Claude/Codex) confirme la lisibilité ; on veut alors la même expérience côté gateway autonome.
3. Une régression de parité est détectée par un test cross-langage existant ou une revue.

Sinon, ticket backlog (pas de pression cycle).

## Meta-signal

Le Decision Gate #9 valide une fois de plus le pattern "preuve d'abord, parité ensuite". Cohérent avec le Gate #6 (per-op CRDs annulé après bench RED) et le Gate #7 (3 tools dev gateway NO-GO car alternative sans gateway plus simple).

## External index

Le log cross-repo `stoa-docs/HEGEMON/DECISION_GATE.md` s'arrête à #7 ; #8 n'y a pas été enregistré. Conformément à la décision opérationnelle (2026-04-26) de ne pas rétablir une mécanique cross-repo abandonnée, **#9 reste self-contained ici**. Si la pratique cross-repo est reprise un jour, #8 et #9 seront enregistrés à ce moment-là dans le même mouvement.

## Audit du signal #1 (2026-04-26, post PR 2)

Audit lecture du chemin runtime `tools/list` côté `stoa-gateway`, exécuté juste après le merge de PR 2 (`d368ae4a4`).

**Verdict : NOGO confirmé sur PR 3 (Rust parity).** Le gateway Rust est un *consumer* de la projection cp-api, pas un *generator*. Aucun équivalent Rust de `_build_description` (cp-api Python) ne s'exécute sur le chemin chaud `/mcp/tools/list`.

### Chaîne runtime confirmée

```
client MCP → GET /mcp/tools/list
  → stoa-gateway/src/mcp/handlers.rs:314      state.tool_registry.list(...)
  → registry rempli au boot par stoa_tools.rs:298  refresh_tools_for_tenant()
  → tool_proxy.rs:340                         GET /v1/internal/gateways/tools/generated
  → cp-api lit la table mcp_generated_tools
  → tools projetés par UacToolGenerator._build_description (modifié en PR 1, #2585)
```

Le gateway réutilise tel quel le champ `description` reçu de cp-api (`stoa_tools.rs:48,93-96`). Pas de re-projection Rust en chemin chaud.

### Code Rust qui ressemble à une projection mais ne l'est pas

- `stoa-gateway/src/uac/binders/mcp.rs:46-93` — `McpBinder::generate_tool_definitions()` construit bien des descriptions, mais appelé uniquement depuis `handlers/admin/contracts.rs:72-76` (POST `/admin/contracts`), jamais sur `tools/list`.
- `stoa-gateway/src/mcp/tools/stoa_tools.rs:114-130` — `infer_action()` est une inférence d'action, pas un équivalent de `_build_description`.

### Implications

- **Signal #1 : NON.** Le chemin gateway → `tools/list` ne consomme pas de projection Rust.
- **Signal #2** (canary mergé + retour client agent) : partiellement satisfait (canary mergé via PR 2). Pas encore de retour agent en prod, mais sans projection Rust, la question ne se pose plus.
- **Signal #3** : aucune régression de parité possible (pas de double projection à comparer).

**Décision : PR 3 fermée, aucun ticket backlog ouvert.** Le gateway Rust restera consumer de cp-api pour la metadata projetée. Le seul lieu de maintenance des descriptions reste `control-plane-api/src/services/uac_tool_generator.py`.

### Plan UAC V2 = exécuté

| PR | État | Merge |
|---|---|---|
| PR 1 — cp-api generator enrichi | ✅ Merged | `82c5ebb49` (#2585) |
| PR 2 — smoke + canary | ✅ Merged | `d368ae4a4` (#2588) |
| PR 3 — Rust parity | ✅ Closed (audit signal #1 NOGO) | n/a |

Go criteria du plan ("`tools/list` expose `Intent` + `Side effects` sur le canary, sans casser les tools legacy") atteint à 100%.
