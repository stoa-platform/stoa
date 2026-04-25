# CI-1 — Phase 1 Architectural Plan: `claude-issue-to-pr.yml` Rewrite

**Objet** : design détaillé du rewrite, sans code d'implémentation. Livrable Phase 1.

**Décisions Phase 0 confirmées** (Discovery `CI-1-DISCOVERY.md` + retour utilisateur) :
- Topologie 3 jobs conservée
- Langage scripts : Python pour parsing/GraphQL/PR-detection, Bash pour wrappers `gh`
- Composite actions (pas reusable workflows)
- Pinning commit SHA des actions tierces uniquement dans les nouveaux composites (pas d'audit global, hors scope CI-1)
- Tests via pytest principalement, bats minimal, path-filter CI
- Polling `wait_for_label` conservé mais extrait
- Sortie Council structurée (JSON) + fallback regex legacy
- `continue-on-error: true` sur Claude steps préservé et documenté
- Branches séparées : `refactor/ci-1-phase-0-discovery` (discovery commité `368902dcd`) + `refactor/ci-1-ai-factory-rewrite` (ce plan et toutes les sous-phases 2a-2d)

**Pas d'exécution Phase 2a avant validation explicite de ce plan.**

---

## A. Arborescence cible finale

```
.github/
├── CI-1-DISCOVERY.md                         # Phase 0 (déjà commité sur branche phase-0)
├── CI-1-REWRITE-PLAN.md                      # Ce document (Phase 1)
├── README.md                                 # Nouveau (Phase 2d) — index composites + scripts
├── workflows/
│   ├── claude-issue-to-pr.yml                # Final (~100-140 LOC) — remplace l'original en Phase 2d
│   ├── claude-issue-to-pr-v2.yml             # Temporaire (Phase 2b → supprimé Phase 2d)
│   └── ai-factory-scripts-tests.yml          # Nouveau (Phase 2c) — runner pytest + bats
├── actions/
│   ├── label-guard/                          # Nouveau (Phase 2b)
│   │   ├── action.yml
│   │   └── README.md
│   ├── wait-for-label/                       # Nouveau (Phase 2b)
│   │   ├── action.yml
│   │   └── README.md
│   ├── council-run/                          # Nouveau (Phase 2b)
│   │   ├── action.yml
│   │   └── README.md
│   ├── council-sync-linear/                  # Nouveau (Phase 2b)
│   │   ├── action.yml
│   │   └── README.md
│   ├── council-notify-slack/                 # Nouveau (Phase 2b)
│   │   ├── action.yml
│   │   └── README.md
│   ├── detect-partial-pr/                    # Nouveau (Phase 2b)
│   │   ├── action.yml
│   │   └── README.md
│   ├── hegemon-state-push/                   # Nouveau (Phase 2b)
│   │   ├── action.yml
│   │   └── README.md
│   └── write-summary/                        # Nouveau (Phase 2b)
│       ├── action.yml
│       └── README.md
scripts/
├── ai-ops/                                   # Existant, intouché
│   ├── ai-factory-notify.sh
│   └── model-router.sh
└── ci/                                       # Nouveau (Phase 2a)
    ├── parse_council_report.py
    ├── linear_apply_label.py
    ├── detect_pr_for_issue.py
    ├── map_score_to_label.py
    ├── gh_helpers.sh                         # Bash helpers source-able (ticket id, guards)
    ├── wait_for_label.sh                     # Polling loop extractible
    └── tests/
        ├── conftest.py
        ├── test_parse_council_report.py
        ├── test_linear_apply_label.py
        ├── test_detect_pr_for_issue.py
        ├── test_map_score_to_label.py
        ├── test_gh_helpers.bats              # Bats minimal
        └── fixtures/
            ├── council_s1_report.json        # Sample execution output
            ├── council_s2_report.json
            └── legacy_council_comment.md     # Fallback regex input
```

**Ligne de fond** : `.github/actions/` grossit de 4 à 12 composites, `scripts/ci/` est nouveau. Le workflow final passe de 797 LOC à ~140 LOC estimés (réduction ~82%).

---

## B. Scripts — contrats détaillés (inputs / outputs / exit codes)

### B.1 `scripts/ci/parse_council_report.py` (Python)

**But** : extraire score + verdict + mode + estimate depuis la sortie d'un step `anthropics/claude-code-action@v1`, avec fallback regex sur comment markdown legacy.

**Inputs**
- `--execution-file <path>` (requis) : chemin `claude-execution-output.json` (écrit par l'action dans `/home/runner/work/_temp/`)
- `--stage <s1|s2>` (requis) : détermine le pattern de score attendu (`Council Score:` pour S1, `Plan Score:` pour S2)
- `--fallback-comment <path>` (optionnel) : fichier markdown (comment GitHub/Linear) si `execution-file` absent
- `--strict` (flag) : exit 1 si aucune donnée extractible (default: emit empty fields, exit 0)

**Output**
- stdout : JSON unique sur une ligne :
  ```json
  {"score":8.2,"verdict":"go","mode":"ship","estimate_points":3,"source":"structured_json|regex|fallback"}
  ```
- `score` : float [0.0-10.0] ou `null`
- `verdict` : `"go"` | `"fix"` | `"redo"` | `null` (dérivé de score : ≥8→go, ≥6→fix, sinon redo)
- `mode` : `"ship"` | `"show"` | `"ask"` (default `"ask"`)
- `estimate_points` : int ≥0 (default 0)
- `source` : `"structured_json"` si bloc JSON trouvé dans la sortie, `"regex"` si parsing legacy, `"fallback"` si fichier fallback utilisé

**Exit codes**
- `0` : succès (même si champs null, sauf `--strict`)
- `1` : fichier inexistant, JSON invalide, ou `--strict` + rien extrait
- `2` : arguments invalides

**Fallback strategy**
1. Lit `execution-file`, concatène tous les `assistant.content[].text`
2. Cherche un bloc ```json ... ``` contenant `"score"` (nouveau contrat structuré)
3. Si absent, cherche regex legacy : `(?:Council Score|Plan Score|Score):\s*([0-9]+\.?[0-9]*)/10` selon `--stage`
4. Cherche `Ship/Show/Ask:\s*(ship|show|ask)` (case-insensitive)
5. Cherche `Estimate:\s*([0-9]+)\s*pts?` ou `~([0-9]+) pts`
6. Si `--fallback-comment` fourni, re-lance 2-5 sur son contenu

### B.2 `scripts/ci/linear_apply_label.py` (Python)

**But** : remplace les 2 blocs inline de 80 LOC (`Sync Council to Linear`, `Sync Plan Council to Linear`) par 1 script paramétré.

**Inputs** (CLI args + env pour secret)
- `--ticket-id <CAB-XXXX>` (requis)
- `--namespace <ticket|plan>` (requis) : préfixe label Linear (`council:ticket-` ou `council:plan-`)
- `--score <float>` (requis) : score Council
- `--comment-body <str>` (requis) : corps du commentaire Linear à poster
- `env LINEAR_API_KEY` (requis) : token

**Output**
- stdout (JSON) :
  ```json
  {"applied_label":"council:ticket-go","issue_id":"abc-123","comment_posted":true}
  ```
- Si `LINEAR_API_KEY` absent ou `issue_id` introuvable → JSON avec champs null + exit 0 (pas d'erreur bloquante, comportement actuel préservé)

**Exit codes**
- `0` : succès ou skip volontaire (secret absent, ticket non trouvé)
- `1` : erreur réseau / GraphQL 5xx répétée
- `2` : arguments invalides

**Comportement GraphQL** (préservé du bash existant) :
1. `issueSearch(filter: { identifier: { eq: $TICKET_ID } })` → récupère `issue_id`
2. `issueLabels(filter: { name: { eq: $LABEL_NAME } })` → récupère `label_id`
3. Lit labels existants, filtre ceux commençant par `council:${namespace}-` (dédupe)
4. `issueUpdate(input: { labelIds: [...existing_filtered, new] })`
5. `commentCreate(input: { issueId, body })` avec escape JSON correct (évite les bugs `\n` du bash actuel)

### B.3 `scripts/ci/detect_pr_for_issue.py` (Python)

**But** : remplace le bloc inline 42 LOC `Detect Partial Success` avec false-positive guard.

**Inputs**
- `--issue-number <N>` (requis)
- `--ticket-id <CAB-XXXX>` (optionnel)
- `env GH_TOKEN` (requis) : pour `gh` (passé à subprocess ou à `PyGithub` si plus simple — **décision** : subprocess `gh` pour rester cohérent avec le reste du stack)

**Output** (stdout JSON)
```json
{"pr_found":true,"pr_num":1234,"pr_url":"https://github.com/stoa-platform/stoa/pull/1234","pr_state":"OPEN"}
```
ou `{"pr_found":false}` si aucune PR valide.

**False-positive guard** : préserve la logique actuelle — PR doit matcher sur `headRefName` OU `title` contenant soit `CAB-XXXX` soit `issue-${N}`.

**Exit codes**
- `0` : toujours (pas de différence pr_found true/false au niveau exit)
- `1` : erreur `gh` (auth, network)
- `2` : args invalides

### B.4 `scripts/ci/map_score_to_label.py` (Python)

**But** : simple mapping score → label name (factorise logique dupliquée 2× dans le workflow).

**Inputs**
- `--score <float>` (requis)
- `--namespace <ticket|plan>` (requis)

**Output** (stdout, une ligne)
- `council:ticket-go` / `council:ticket-fix` / `council:ticket-redo` (ou `plan-*`)

**Rules** : score ≥ 8.0 → `-go`, score ≥ 6.0 → `-fix`, sinon `-redo`. Score invalide → exit 1.

**Exit codes** : `0` succès, `1` score invalide, `2` args invalides.

> Alternative rejetée : faire ce mapping inline en Python dans `linear_apply_label.py`. Décision : script séparé pour permettre aux autres composites (Slack verdict, labels GitHub futurs) de l'utiliser sans dépendre de l'appel Linear.

### B.5 `scripts/ci/gh_helpers.sh` (Bash source-able)

**But** : regroupe les petites fonctions bash répétées. Source-é par les composites.

**Fonctions exposées**
```bash
extract_ticket_id "<text>"       # stdout: CAB-XXXX ou ""
has_label <issue-num> <label>    # exit 0 si présent, 1 sinon
ensure_label <name> <color> <desc>  # idempotent gh label create --force
add_label <issue-num> <label>    # gh issue edit --add-label
```

**Tests** : via bats, petit fichier.

### B.6 `scripts/ci/wait_for_label.sh` (Bash)

**But** : extrait le polling loop du job `implement.Verify Plan validation`.

**Inputs**
- `$1` issue number
- `$2` label name
- `$3` max-attempts (default 10)
- `$4` interval-seconds (default 30)
- env `GH_TOKEN`

**Output**
- stdout final : `validated=true` ou `validated=false`
- `::notice::` logs GH Actions entre chaque tentative
- `::error::` si timeout

**Exit codes**
- `0` : label trouvé
- `1` : timeout

**Préserve fallback** : check aussi "Plan Score" dans comments (comportement actuel).

---

## C. Composite actions — contrats détaillés

### C.1 `.github/actions/label-guard/action.yml`

**But** : guard idempotence — vérifie si un label est déjà présent sur une issue, émet output bool.

**Inputs**
| Name | Required | Description |
|------|----------|-------------|
| `issue-number` | yes | Issue number |
| `label-name` | yes | Label to check |
| `github-token` | yes | `gh` auth |

**Outputs**
| Name | Description |
|------|-------------|
| `already-set` | `"true"` si label présent, `"false"` sinon |

**Steps internes** : 1 shell step appelant `gh_helpers.sh::has_label`.

**README** : documente pattern guard-idempotence + exemple d'usage.

### C.2 `.github/actions/wait-for-label/action.yml`

**But** : bloque jusqu'à apparition du label (max-attempts × interval) ou échoue.

**Inputs**
| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `issue-number` | yes | — | Issue number |
| `label-name` | yes | — | Label attendu |
| `max-attempts` | no | `10` | Tentatives max |
| `interval-seconds` | no | `30` | Sleep entre tentatives |
| `fallback-comment-pattern` | no | `""` | Regex sur comments (ex: `Plan Score`) |
| `github-token` | yes | — | `gh` auth |

**Outputs**
| Name | Description |
|------|-------------|
| `validated` | `"true"` ou `"false"` |

**Steps internes** : 1 shell step → `scripts/ci/wait_for_label.sh`.

**README** : justifie polling (race condition GitHub label vs comment propagation), référence au § Discovery E.F. Propose solution root-cause comme amélioration futurs (non-scope CI-1).

### C.3 `.github/actions/council-run/action.yml`

**But** : wrapper de `anthropics/claude-code-action@v1` + parsing JSON structuré.

**Inputs**
| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `stage` | yes | — | `s1` (pertinence) ou `s2` (plan) |
| `prompt` | yes | — | Prompt complet (le caller inject title/body) |
| `anthropic-api-key` | yes | — | Secret |
| `model` | no | `claude-sonnet-4-6` | Modèle Claude |
| `max-turns` | no | `5` | Turn budget |
| `allowed-tools` | no | `Bash,Read,Glob,Grep` | Tools autorisés |

**Outputs**
| Name | Description |
|------|-------------|
| `outcome` | `success` / `failure` |
| `score` | Score float extrait (`""` si absent) |
| `verdict` | `go` / `fix` / `redo` / `""` |
| `mode` | `ship` / `show` / `ask` |
| `estimate-points` | int |
| `execution-file` | Path vers `claude-execution-output.json` |

**Steps internes** :
1. `anthropics/claude-code-action@<SHA>` avec `continue-on-error: true` (préservé, documenté dans README)
2. Run `scripts/ci/parse_council_report.py --execution-file $EXEC --stage $STAGE`
3. Parse JSON stdout → émet les outputs via `$GITHUB_OUTPUT`

**README** : justifie `continue-on-error: true` (détection partial success, max_turns). Documente le contrat prompt attendu (bloc JSON structuré optionnel + fallback comment regex).

### C.4 `.github/actions/council-sync-linear/action.yml`

**But** : remplace les 2 blocs inline dupliqués de sync Linear.

**Inputs**
| Name | Required | Description |
|------|----------|-------------|
| `ticket-id` | no | Auto-extract depuis `issue-title` + `issue-body` si absent |
| `issue-title` | no | Pour extraction ticket-id |
| `issue-body` | no | Idem |
| `namespace` | yes | `ticket` ou `plan` |
| `score` | yes | Score Council |
| `run-url` | yes | GitHub Actions run URL (inséré dans comment Linear) |
| `linear-api-key` | yes | Secret |

**Outputs**
| Name | Description |
|------|-------------|
| `applied-label` | Label appliqué (ou `""` si skip) |
| `skipped` | `"true"` si pas de `LINEAR_API_KEY` ou ticket non trouvé |

**Steps internes** :
1. Si `ticket-id` vide → `gh_helpers.sh::extract_ticket_id`
2. Run `scripts/ci/linear_apply_label.py ...`
3. Parse JSON → outputs

### C.5 `.github/actions/council-notify-slack/action.yml`

**But** : wrap appels à `ai-factory-notify.sh::notify_council` + `_react_slack` + `push_metrics_council`.

**Inputs**
| Name | Required | Description |
|------|----------|-------------|
| `ticket` | yes | TICKET ID |
| `issue-title` | yes | — |
| `issue-url` | yes | — |
| `issue-number` | yes | — |
| `score` | yes | Score ("?" si absent) |
| `verdict` | yes | go/fix/redo |
| `slack-webhook` | yes | Secret |
| `slack-bot-token` | yes | Secret |
| `slack-channel-id` | yes | Secret |
| `pushgateway-url` | yes | — |
| `pushgateway-auth` | yes | Secret |
| `n8n-webhook-url` | no | — |
| `hmac-secret` | no | Secret |

**Outputs**
| Name | Description |
|------|-------------|
| `slack-ts` | Timestamp du message Slack (pour threading) |

**Steps internes** : 1 shell step qui source `ai-factory-notify.sh` puis appelle `notify_council`, `_react_slack`, `push_metrics_council`.

**Note** : ces fonctions existent déjà dans `ai-ops/ai-factory-notify.sh`. Le composite ne réécrit pas, il orchestre.

### C.6 `.github/actions/detect-partial-pr/action.yml`

**Inputs**
| Name | Required | Description |
|------|----------|-------------|
| `issue-number` | yes | — |
| `ticket-id` | no | Auto-extract si absent |
| `issue-title` | no | Pour extraction |
| `issue-body` | no | Idem |
| `github-token` | yes | — |

**Outputs**
| Name | Description |
|------|-------------|
| `pr-found` | `"true"` / `"false"` |
| `pr-num` | Numéro PR (`""` si non-found) |
| `pr-url` | — |
| `pr-state` | `OPEN` / `MERGED` / `CLOSED` / `""` |

**Steps internes** : `scripts/ci/detect_pr_for_issue.py`.

### C.7 `.github/actions/hegemon-state-push/action.yml`

**But** : wrap `push_state_session` + `push_state_milestone` + `push_state_cleanup`.

**Inputs**
| Name | Required | Description |
|------|----------|-------------|
| `instance` | yes | `$HEGEMON_INSTANCE` (ex: `l1-impl-${RUN_ID}`) |
| `ticket` | yes | TICKET ID |
| `action` | yes | `session-start` / `milestone` / `cleanup` |
| `milestone-name` | no | Requis si `action=milestone` (ex: `impl-started`, `impl-success`) |
| `pr-num` | no | Pour milestone final |
| `duration-seconds` | no | Pour milestone cleanup |
| `hegemon-url` | yes | Secret |
| `hegemon-email` | yes | Secret |
| `hegemon-password` | yes | Secret |

**Outputs** : aucun.

**Pattern** : `continue-on-error: true` préservé au niveau du step interne (préserve comportement legacy : HEGEMON unreachable ne bloque pas le workflow).

### C.8 `.github/actions/write-summary/action.yml`

**But** : wrap `ai-factory-notify.sh::write_job_summary`.

**Inputs**
| Name | Required | Description |
|------|----------|-------------|
| `ticket` | yes | — |
| `outcome` | yes | `success` / `failure` / `skipped` |
| `model` | no | — |
| `stage` | yes | `council-s1` / `council-s2` / `L1-implement` |
| `pr-num` | no | — |
| `duration-seconds` | no | — |

**Outputs** : aucun.

---

## D. Mapping old-step → new-step

### D.1 Job `council-validate` (9 → 8 steps)

| # old | Nom old step | → | Nom new step / composite | Notes |
|-------|--------------|---|--------------------------|-------|
| 1 | `actions/checkout@v6` | = | `actions/checkout@v6` | Inchangé |
| 2 | `Check Council Already Done` | → | `uses: ./.github/actions/label-guard` | Sortie `already-set` gate les steps suivants |
| 3 | `Run Council Validation` | → | `uses: ./.github/actions/council-run` avec `stage: s1` | Emet `score`, `verdict`, `outcome`, `execution-file` |
| 4 | `Log token usage` | = | step inline 3-ligne `echo ::notice::` | Trop trivial pour un composite |
| 5 | `Mark Council complete` | → | step inline appelant `gh_helpers.sh::ensure_label` + `add_label` | Simple, pas besoin composite dédié |
| 6 | `Check Ship Fast Path` | → | step inline utilisant outputs de `council-run` (`mode`, `estimate-points`) + `gh_helpers.sh` | Simplifié (plus besoin de re-parser exec file) |
| 7 | `Sync Council to Linear` | → | `uses: ./.github/actions/council-sync-linear` avec `namespace: ticket` | **Replaces 83 LOC inline** |
| 8 | `Slack Council Report` | → | `uses: ./.github/actions/council-notify-slack` | **Replaces 29 LOC inline** |
| 9 | `Write Job Summary — Council` | → | `uses: ./.github/actions/write-summary` avec `stage: council-s1` | |

**Gain estimé** : ~180 LOC → ~50 LOC (job entier).

### D.2 Job `plan-validate` (10 → 9 steps)

| # old | Nom old step | → | Nom new step / composite | Notes |
|-------|--------------|---|--------------------------|-------|
| 1 | `actions/checkout@v6` | = | Inchangé | |
| 2 | `Verify Stage 1 Council` | → | `uses: ./.github/actions/label-guard` (label=`council-validated`) + guard label=`plan-validated` | Double guard en séquence |
| 3 | `Skip if not L1` | = | step inline `if: ! validated` → `exit 0` | Préservé |
| 4 | `Check Ship Fast Path` | → | step inline utilisant `label-guard` (label=`ship-fast-path`) + `gh_helpers.sh::add_label` + `gh issue comment` | Ordering fix (comment avant label) — voir §F |
| 5 | `Run Plan Validation (Stage 2 Council)` | → | `uses: ./.github/actions/council-run` avec `stage: s2`, `max-turns: 10` | |
| 6 | `Log token usage` | = | Inchangé | |
| 7 | `Mark Plan validated` | → | step inline via `gh_helpers.sh` | |
| 8 | `Sync Plan Council to Linear` | → | `uses: ./.github/actions/council-sync-linear` avec `namespace: plan` | |
| 9 | `Slack Plan Validation` | → | step inline source de `ai-factory-notify.sh::notify_plan` (spécifique plan, pas council) | Pas composite dédié (1 appel, peu de logique) |
| 10 | `Write Job Summary — Plan` | → | `uses: ./.github/actions/write-summary` avec `stage: council-s2` | |

### D.3 Job `implement` (11 → 10 steps)

| # old | Nom old step | → | Nom new step / composite | Notes |
|-------|--------------|---|--------------------------|-------|
| 1 | `actions/checkout@v6` | = | Inchangé | |
| 2 | `Verify Plan validation` | → | `uses: ./.github/actions/wait-for-label` avec `label-name: plan-validated`, `fallback-comment-pattern: Plan Score` | **Remplace polling inline 31 LOC** |
| 3 | `Abort if no Plan validation` | = | step inline préservé (conditionnel sur output `validated`) | |
| 4 | `Route Model` | = | step inline préservé (source `model-router.sh`) | Non-extrait (déjà versionné) |
| 5 | `Record Start Time` | = | step inline préservé (2 lignes) | Trivial |
| 6 | `Push State — Implementation Started` | → | `uses: ./.github/actions/hegemon-state-push` avec `action: session-start` + `action: milestone` | |
| 7 | `Run Implementation` | = | **Préservé tel quel** (pas wrapé par council-run car prompt différent, pas de parsing score attendu) | `continue-on-error: true` préservé |
| 8 | `Log token usage` | = | Inchangé | |
| 9 | `Detect Partial Success` | → | `uses: ./.github/actions/detect-partial-pr` | **Remplace 42 LOC inline** |
| 10 | `Slack Implementation Result` | → | step inline (dispatcher trop spécifique pour composite) + `linear_comment` + `push_metrics_implement` | Conserve source `ai-factory-notify.sh`, mais variables bien triées |
| 11 | `Write Job Summary — Implement` | → | `uses: ./.github/actions/write-summary` avec `stage: L1-implement` | |

**Note** : `implement.Run Implementation` n'est pas wrapé dans `council-run` car il n'écrit pas un rapport Council (il implémente). Le parsing structuré ne s'applique pas.

---

## E. Stratégie tests

### E.1 Tests Python (pytest)

Framework : `pytest` + `pytest-mock` (déjà dans le repo via `control-plane-api`).

**Coverage target** : 100% des branches des scripts Python extraits (c'est le moment, les scripts sont neufs).

**Scripts testés** (4 suites) :

| Suite | Scénarios principaux |
|-------|---------------------|
| `test_parse_council_report.py` | JSON structuré OK / JSON malformé / regex legacy S1 / regex legacy S2 / fichier absent / `--strict` mode / Ship/Show/Ask extraction / estimate patterns variés |
| `test_linear_apply_label.py` | Ticket trouvé + label applied / ticket non trouvé (skip gracefull) / LINEAR_API_KEY absent (skip) / réseau KO (retry + exit 1) / label-dedup (existing `council:ticket-*` retirés) / escape JSON comment body |
| `test_detect_pr_for_issue.py` | PR trouvée matching ticket / PR trouvée matching issue-N / PR trouvée mais branch/title ne match pas (false-positive rejected) / aucune PR / `gh` error |
| `test_map_score_to_label.py` | 8.0 → go, 7.99 → fix, 6.0 → fix, 5.99 → redo, 0 → redo, invalid → exit 1, namespace plan/ticket |

**Mocks** :
- `linear_apply_label` : mock `httpx` ou `requests` (décision : `httpx` parce que plus moderne et déjà dans cp-api stack)
- `detect_pr_for_issue` : mock `subprocess.run` de `gh`
- Fixtures JSON dans `scripts/ci/tests/fixtures/`

### E.2 Tests Bash (bats-core)

Scope réduit : uniquement `test_gh_helpers.bats` (4-5 tests simples) et éventuellement `test_wait_for_label.bats` (polling avec mock `gh`).

Décision : si bats-core coûte > 30 min d'install/config → on teste `gh_helpers.sh` via `pytest` + `subprocess`. Pas de dogme.

### E.3 Validation YAML

- `action-validator` (Node, un-time install via `npx`) : validation syntaxique de tous les `action.yml`
- `yamllint` : existant dans repo, ajouter les fichiers composites à la config

### E.4 Workflow de test CI

`.github/workflows/ai-factory-scripts-tests.yml` :

```yaml
name: AI Factory Scripts — Tests

on:
  pull_request:
    paths:
      - '.github/actions/**'
      - '.github/workflows/claude-issue-to-pr*.yml'
      - '.github/workflows/ai-factory-scripts-tests.yml'
      - 'scripts/ai-ops/**'
      - 'scripts/ci/**'
  push:
    branches: [main]
    paths:
      - 'scripts/ci/**'
      - '.github/actions/**'

jobs:
  python-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@<SHA> # v5
      - run: pip install pytest pytest-mock httpx
      - run: pytest scripts/ci/tests/ -v --tb=short

  yaml-validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: npx action-validator .github/actions/**/action.yml

  bats-tests:
    if: false  # activé si bats helpers créés
    runs-on: ubuntu-latest
    steps:
      - run: sudo apt-get install -y bats
      - run: bats scripts/ci/tests/*.bats
```

**Non-required initialement** : 2 semaines de soak puis ajout à `required-checks` via `stoa-docs` config (norme repo).

---

## F. Plan rollout fractionné

### F.1 Phase 2a — Extract scripts (zero-impact sur workflow legacy)

**Livrables** :
- `scripts/ci/parse_council_report.py` + tests
- `scripts/ci/linear_apply_label.py` + tests
- `scripts/ci/detect_pr_for_issue.py` + tests
- `scripts/ci/map_score_to_label.py` + tests
- `scripts/ci/gh_helpers.sh` + tests bats
- `scripts/ci/wait_for_label.sh` + tests bats
- `scripts/ci/tests/conftest.py`
- `scripts/ci/tests/fixtures/` (3 fichiers sample)

**Validation Phase 2a** :
1. `pytest scripts/ci/tests/` vert local
2. Le workflow `.github/workflows/claude-issue-to-pr.yml` reste **100% inchangé** — `git diff` ne doit toucher aucun fichier `.github/workflows/*`
3. Commit atomique + push
4. **STOP, user review avant 2b**

**Risques Phase 2a** :
- Aucun en prod (workflow intact)
- Qualité tests — à auditer par user

### F.2 Phase 2b — Composite actions + workflow clone v2

**Livrables** :
- 8 composite actions dans `.github/actions/*/` avec `action.yml` + `README.md`
- `.github/workflows/claude-issue-to-pr-v2.yml` — **clone** du workflow original, refactorisé pour utiliser les composites
- **Stub PR sur `main`** (`chore(ci): register claude-issue-to-pr-v2.yml stub for workflow_dispatch`) qui ajoute une version minimale de `claude-issue-to-pr-v2.yml` sur le default branch. Voir « Contrainte GitHub Actions » ci-dessous.

**Contrainte GitHub Actions** : `workflow_dispatch` requires the YAML file to exist on the default branch for `gh workflow run` (and the REST `/actions/workflows/:id/dispatches` endpoint) to find it. Phase 2b uses a stub PR on main to register the id before the real dispatch — dispatching `--ref refactor/ci-1-phase-2b-composites` then executes the full file from the feature branch while reusing the registered id. Phase 2d REPLACES the stub in-place with the real orchestrator so the id remains stable across the transition.

**Validation Phase 2b** :
1. `action-validator` vert sur tous les composites
2. `claude-issue-to-pr-v2.yml` ne peut pas tourner par accident :
   - **Décision** : trigger `on: workflow_dispatch` UNIQUEMENT en Phase 2b (pas `on: issues`, pas `on: issue_comment`). Ça permet de tester manuellement sur une issue de test sans interférer avec le workflow prod.
   - En Phase 2d on remplace les triggers v2 par les mêmes que legacy.
3. Déclencher v2 manuellement sur **issue de test dédiée** (créée pour l'occasion, ex: `[TEST] CI-1 v2 smoke — ignore me`) :
   - `gh workflow run claude-issue-to-pr-v2.yml --ref refactor/ci-1-phase-2b-composites -f issue_number=<N> -f run_implement=false`
   - Vérifier : Council S1 score émis, label `council-validated` posé
   - Stage 2 déclenché automatiquement via `needs:` chain (pas `/go`/`/go-plan` en 2b, restauration 2d) → label `plan-validated` posé
   - `run_implement=true` (optionnel, non-default) → implement → PR ouverte sur issue de test
4. Comparer outputs v1 vs v2 : diff sur Slack/Linear/comments/metrics
5. Commit atomique + push
6. **STOP, user review avant 2c**

**Risques Phase 2b** :
- Secrets mal propagés dans composites → Claude action échoue silencieusement (détection : outcome visible dans logs)
- Comportement différent sur un edge case non couvert (mitigation : smoke test sur issue dédiée avant Phase 2d)

### F.3 Phase 2c — Tests CI en place

**Livrables** :
- `.github/workflows/ai-factory-scripts-tests.yml`
- Éventuel ajustement `.github/workflows/` pour exclure ce workflow des autres gates

**Validation Phase 2c** :
1. Le nouveau workflow tourne sur la PR qui l'introduit
2. `pytest` vert sur tous les scripts Phase 2a
3. `action-validator` vert
4. Commit atomique + push
5. **STOP, user review avant 2d**

### F.4 Phase 2d — Switch final

**Livrables** :
- Renommage `claude-issue-to-pr-v2.yml` → `claude-issue-to-pr.yml` (remplace l'ancien)
- Ancienne version archivée : soit tag git (`ci-1-legacy-snapshot-$(date)`) soit comment au top du nouveau fichier référençant le commit SHA de l'ancien
- Triggers v2 alignés sur les triggers originaux (`on: issues`, `on: issue_comment`)
- `.github/README.md` créé, listant les composites + scripts + leurs contrats
- Mise à jour ticket Linear CI-1 → `In Review` → `Done`

**Validation Phase 2d** :
1. Pause AI-Factory activée **avant** merge (voir §G)
2. Merge PR finale
3. Test end-to-end sur issue de test :
   - Créer une issue réelle
   - Ajouter label `claude-implement`
   - Observer S1 → `/go` → S2 → `/go-plan` → implement → PR ouverte
   - Comparer timing + qualité résultat vs baseline legacy
4. Pause AI-Factory désactivée
5. Soak 48h : observer 2-3 runs réels en prod, vérifier Slack/Linear/metrics
6. **Clôture Linear** après soak vert

**Risques Phase 2d** :
- Incident prod = rollback = revert du commit de switch + re-activation kill-switch temporairement. Coût faible car legacy archivé.

---

## G. Méthode pause AI-Factory (Phase 2d uniquement)

### G.1 Mécanisme

Le repo expose déjà `DISABLE_L1_IMPLEMENT=true` comme **repo variable**. Les 3 jobs testent `if: vars.DISABLE_L1_IMPLEMENT != 'true'`.

**Procédure** :

1. **Avant merge final Phase 2d** :
   - Set repo variable via GitHub UI : `DISABLE_L1_IMPLEMENT=true`
   - Commit marker `docs/ops/ai-factory-pause.md` avec :
     ```markdown
     # AI Factory Pause — CI-1 Switch

     - **Start**: 2026-04-24 HH:MM UTC (à remplir en Phase 2d)
     - **Expected end**: +1h
     - **Reason**: CI-1 Phase 2d switch — `claude-issue-to-pr` workflow rewrite
     - **Escalation**: christophe.ab.cab.i@gmail.com
     ```
   - Annoncer Slack `#ai-factory-ops` (si canal existe, sinon `#engineering-ops`)

2. **Pendant la pause** :
   - Les issues labelées `claude-implement` pendant la fenêtre sont mises en file d'attente par GitHub (pas d'exécution). Au unpause, elles re-déclencheraient normalement un workflow seulement si un NOUVEL événement déclencheur est émis (ex: ajout puis retrait puis ajout du label).
   - **Décision importante** : pour éviter les déclenchements post-unpause parasites, la pause doit être courte (<1h) et hors heures ouvrées européennes (démo juin en cours).

3. **Post-merge, avant unpause** :
   - Smoke test sur issue de test dédiée via `workflow_dispatch` (v2 encore en mode dispatch).
   - Si smoke KO → revert commit de switch, unpause.

4. **Unpause** :
   - Set `DISABLE_L1_IMPLEMENT=false`
   - Update marker file : `- **End**: YYYY-MM-DD HH:MM UTC`
   - Observe prochain run réel.

### G.2 Marker file : Phase 1 ou Phase 2d ?

**Décision** : template du marker livré en Phase 2d (dans le même commit que le switch). Phase 1 = design doc, pas d'opérations prod. En Phase 2d, Claude rédige le marker avec les données réelles (timestamps) au moment du merge.

**Alternative rejetée** : livrer le marker vide en Phase 1 — risque de pollution `docs/ops/` avec marker vide non-utilisé si Phase 2d retardée.

---

## H. Checklist non-régression (Phase 2d validation)

### H.1 Labels GitHub produits

| Label | Job qui le pose | Préservé ? |
|-------|-----------------|-----------|
| `council-validated` (#0e8a16) | `council-validate` step `Mark Council complete` | À vérifier : couleur + description + timing (doit être posé UNIQUEMENT si Council OK) |
| `plan-validated` (#006b75) | `plan-validate` step `Mark Plan validated` OU `Check Ship Fast Path` | À vérifier : idem, posé dans Ship fast-path trajectory |
| `ship-fast-path` (#d4c5f9) | `council-validate` step `Check Ship Fast Path` | À vérifier : posé uniquement si Mode=Ship + estimate≤5 |

### H.2 Comments GitHub issue

| Commentaire | Format attendu | Préservé ? |
|-------------|----------------|-----------|
| Council S1 report | Contient `Council Score: X.XX/10 — [Go|Fix|Redo]` | Prompt inchangé |
| Plan S2 report | Contient `Plan Score: X.XX/10 — [Go|Fix|Redo]` | Prompt inchangé |
| Ship fast-path auto-comment | `Ship fast-path: Stage 2 skipped ... /go-plan` | Préservé |
| Abort comment | `Implementation requires plan validation ...` | Préservé |

### H.3 Comments Linear

| Commentaire | Condition | Format |
|-------------|-----------|--------|
| S1 sync | `LINEAR_API_KEY` + ticket-id extractable | `Council validation (Stage 1): **X.XX/10** — council:ticket-* [GitHub Actions run](URL)` |
| S2 sync | idem | `Plan validation (Stage 2): **X.XX/10** — council:plan-* ...` |

**Escape char correction** : le bash actuel génère `\\n` littéral dans le body Linear. Le Python le remplacera par de vrais newlines (amélioration, non breaking).

### H.4 Labels Linear

| Namespace | Labels |
|-----------|--------|
| `council:ticket-*` | `go` / `fix` / `redo` |
| `council:plan-*` | `go` / `fix` / `redo` |

Dedup : labels existants du même namespace sont retirés avant ajout du nouveau (préservé).

### H.5 Slack messages

| Job | Message | Fonction source |
|-----|---------|-----------------|
| S1 | Council report avec score/verdict | `notify_council` |
| S2 | Plan validation | `notify_plan` |
| Implement success | Tada emoji + PR URL | `notify_implement success` |
| Implement max_turns | Rocket emoji + PR URL | `notify_implement ask` |
| Implement failure | X emoji | `notify_error` |

Réactions Slack : `:mag:` post-S1, `:white_check_mark:` post-S2, `:tada:`/`:rocket:`/`:x:` post-implement.

### H.6 Metrics Prometheus

| Metric call | Job | Data |
|-------------|-----|------|
| `push_metrics_council` | S1 | workflow, ticket, score, verdict |
| `push_metrics_implement` | implement | workflow, ticket, status, duration, model, max_turns |
| `push_metrics_error` | implement failure path | workflow, stage, ticket |

### H.7 HEGEMON state

| Call | Moment |
|------|--------|
| `push_state_session implementing` | Implement start |
| `push_state_milestone impl-started` | Implement start |
| `push_state_milestone impl-{outcome}` | Implement end (success/failure/max_turns) |
| `push_state_cleanup` | Implement end |

### H.8 Fork safety

- [ ] `author_association` gate toujours présent sur `plan-validate` et `implement`
- [ ] Liste fermée `[OWNER, MEMBER, COLLABORATOR]` préservée
- [ ] Gate testé via commit d'un fork test (simulé localement par `gh act` si disponible)

### H.9 Kill-switch

- [ ] `DISABLE_L1_IMPLEMENT=true` court-circuite les 3 jobs
- [ ] Nouveau workflow teste la var de la même manière
- [ ] Aucun nouveau composite ne bypass la var

### H.10 Concurrency

- [ ] Groupe `claude-issue-${{ github.event.issue.number }}` préservé
- [ ] `cancel-in-progress: false` préservé

### H.11 Timeouts

| Job | Timeout legacy | Timeout v2 |
|-----|----------------|------------|
| council-validate | 15 min | 15 min |
| plan-validate | 20 min | 20 min |
| implement | 60 min | 60 min |

Pas de changement de timeout en CI-1.

---

## I. Risques consolidés (héritage Phase 0 + nouveaux)

| # | Risque | Probabilité | Impact | Mitigation |
|---|--------|-------------|--------|------------|
| R1 | Composite action lit mal un secret → Claude action échoue auth silencieux | Moyenne | Fort | Dry-run Phase 2b sur issue de test ; logs `::notice::` avant/après chaque action critique |
| R2 | Parsing JSON structuré non émis par Claude → fallback regex échoue sur un nouveau format | Faible | Moyen | Tests unitaires avec fixtures réelles ; fallback triple (structured JSON → S1/S2 regex → autres regex) |
| R3 | `linear_apply_label.py` — escape JSON body casse sur comment avec guillemets | Moyenne | Faible | Fixtures test avec body contenant `"`, `\`, newlines |
| R4 | Branche longue Phase 2 → conflits avec autres PRs CI | Moyenne | Moyen | Rebase quotidien `origin/main` sur branche rewrite |
| R5 | Le fix ordering `ship-fast-path` (label avant comment) casse un consommateur downstream | Faible | Moyen | **Décision revue** : NE PAS changer l'ordre en Phase 2b. Préserver label-then-comment legacy. Amélioration hors scope. |
| R6 | Tests pytest `import` échouent parce que `scripts/ci/` n'est pas un package Python | Moyenne | Faible | Ajouter `__init__.py` ou configurer `pytest.ini` avec `pythonpath = scripts/ci` |
| R7 | `gh_helpers.sh` sourcé par des composites exécutant sur runner fresh — PATH peut différer | Faible | Faible | Utiliser chemins absolus `$GITHUB_WORKSPACE/scripts/ci/gh_helpers.sh` |
| R8 | `anthropics/claude-code-action@v1` change son format `execution_file` entre versions | Moyenne | Moyen | Pin au commit SHA lors de la migration en composite (norme nouveaux composites) |
| R9 | Soak 48h Phase 2d insuffisant pour détecter un bug saisonnier (ex: ticket sans CAB-ID) | Moyenne | Faible | Pendant soak, observer runs en rotation AI-Factory ; rollback ready |
| R10 | Pause AI-Factory dépassée → file d'attente se vide avec comportement imprévu | Faible | Moyen | Pause < 1h, hors heures bureau EU ; procédure §G documentée |

---

## J. Estimates

| Phase | LOC additionnelles | Effort Claude | Complexité |
|-------|-------------------|---------------|------------|
| 2a | ~450 (scripts + tests) | 2h | Faible (pure extraction) |
| 2b | ~400 (8 composites + READMEs + v2 workflow) | 3h | Moyenne (composite API design) |
| 2c | ~80 (workflow tests) | 1h | Faible |
| 2d | ~50 (switch + archive + README) | 1h | Moyenne (opérationnel, pause) |
| **Total** | **~980 LOC** | **~7h** | |

Workflow final `claude-issue-to-pr.yml` : **~140 LOC** (vs 797 legacy = **-82%**).

---

## K. Décisions qui restent ouvertes (demande utilisateur avant Phase 2a)

1. **Test framework fallback** : si bats-core install > 30 min en CI, on teste `gh_helpers.sh` via pytest+subprocess. **Confirm ?**
2. **Pin commit SHA des nouvelles actions tierces** : `actions/setup-python@<SHA>` dans `ai-factory-scripts-tests.yml` et `anthropics/claude-code-action@<SHA>` dans `council-run/action.yml`. J'utiliserai les SHAs actuels résolus depuis `@v5` et `@v1`. **OK ?**
3. **R5 ordering fix** : le plan actuel PRÉSERVE l'ordre legacy (label puis comment). Je supprime la proposition d'amélioration pour ne pas élargir le scope. **Confirme ?**
4. **Pause Phase 2d horaire** : je propose une fenêtre ~~samedi matin UTC~~ à définir le moment du switch, pas maintenant. Phase 2d ouvre un court thread de synchronisation. **OK ?**
5. **Nommage workflow tests** : `ai-factory-scripts-tests.yml` vs `ci-scripts-tests.yml`. Je pars sur le premier (scope clair). **OK ?**
6. **Issue de test en Phase 2b** : créer une issue dédiée dans le repo ou utiliser une existante ? Je propose d'en créer une labelée `[TEST] CI-1` avec auto-fermeture après validation. **OK ?**

---

## L. Livrable Phase 1 — récapitulatif

- ✅ Arborescence cible détaillée (A)
- ✅ 6 scripts Python/Bash contractualisés inputs/outputs/exit codes (B)
- ✅ 8 composite actions avec inputs/outputs/steps (C)
- ✅ Mapping old-step → new-step pour les 3 jobs (D)
- ✅ Stratégie tests pytest + bats + action-validator + workflow CI (E)
- ✅ Plan rollout 2a/2b/2c/2d avec validation gates (F)
- ✅ Méthode pause AI-Factory (G)
- ✅ Checklist non-régression 11 axes (H)
- ✅ Risques consolidés + mitigations (I)
- ✅ Estimates (J)
- ✅ 6 décisions ouvertes pour validation utilisateur (K)

**STOP — Phase 2a (extract scripts) lancée uniquement après validation explicite de ce plan + arbitrage des 6 questions (K).**
