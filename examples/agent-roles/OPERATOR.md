# Guide opérateur — contrôle d’accès des rôles agents

## Démonstration locale

```bash
./scripts/run_demo.sh --prepare
./scripts/run_demo.sh
```

## Démo locale d’installation de stoactl

Cette démo s’appuie sur les images préconstruites via le script de préparation et sur le module source du CLI compagnon STOA v2. Le lanceur demande une phrase de passe masquée puis exécute le véritable `stoactl credentials add anthropic` avec saisie masquée de la clé fournisseur. La phrase de passe et le contenu chiffré du coffre transitent uniquement en mémoire locale : le tube anonyme est privé (les octets en transit ne sont pas chiffrés), le fichier du coffre reste chiffré au repos et le déverrouillage s’effectue via un socket Unix privé vers Docker sans jamais injecter la clé fournisseur dans l’environnement Claude. Le coffre opérateur existe uniquement pendant l’exécution puis est nettoyé automatiquement. Par défaut, `--show` affiche au plus 5 commandes.

```bash
./scripts/agent_demo.sh --prepare
STOA_POC_STOACTL_SRC=/chemin/vers/stoa-v2/cli ./scripts/install_demo.sh --show
```

Le parcours distingue deux périmètres bien séparés. Une simulation de remboursement par MCP direct autorise 50 et refuse 80, puis une vérification d’inférence réelle lance le véritable CLI Claude en mode `--bare` avec un grant local borné sur Claude Sonnet 4.6 et un seul prompt `READY` (le CLI pouvant effectuer des tentatives de reprise HTTP) pouvant être facturé par Anthropic. L’empreinte HMAC du journal est ensuite vérifiée face au coffre.

L’option `--show --verify-local` conserve le contrôle synthétique A1 avec quatre valeurs de test fournisseur et sans appel de modèle. La preuve actuelle couvre le chiffrement Go vers Rust, le périmètre Docker et les bouchons sans revendiquer de test réel complet.

```bash
STOA_POC_STOACTL_SRC=/chemin/vers/stoa-v2/cli ./scripts/install_demo.sh --show --verify-local
```

### Story locale

La story locale couvre uniquement les chapitres 1 à 3, sans inférence live ni facturation, et sans utiliser de clés ni de profils natifs dédiés. Elle s'appuie sur quatre exemples synthétiques aux chemins masqués, exécute réellement les commandes `import`, `list` et `probe`, vérifie 6 commandes au total et observe quatre échecs d'authentification HTTPS directs.

Les données de démonstration sont stockées en texte chiffré AES-256-GCM (Go) sans laisser de fixture en clair sur disque. La gestion d'environnement distingue exactement le fichier `.env` de Gemini CLI de l'environnement natif d'Antigravity.

```bash
STOA_POC_STOACTL_SRC=/chemin/vers/stoa-v2/cli ./scripts/install_demo.sh --show --story --verify-local
```

## Démonstration guidée (chapitres 1 à 5)

- **Chapitres 1 à 3 (preuve locale synthétique, 6 commandes, sans inférence réseau)** :
  ```bash
  ./scripts/install_demo.sh --show --story --verify-local
  ```
- **Histoire complète — chapitres 1 à 5 (8 commandes, inférence gouvernée réelle)** :
  ```bash
  ./scripts/install_demo.sh --show --story --anthropic-key-file /chemin/vers/cle-anthropic
  ```

### Périmètre et protection de la clé
- Quatre configurations CLI jetables (`claude`, `vibe`, `antigravity`, `codex`) sont raccordées au relais scopé via `stoactl connect`, mais **seul le vrai CLI Claude** exécute une inférence réelle (modèle `claude-sonnet-4-6`) à travers la passerelle locale.
- Le fichier passé à `--anthropic-key-file` doit être un fichier régulier protégé (`chmod 600`, propriétaire courant, 1 à 4097 octets, sans lien symbolique). Son descripteur est transmis directement à `stoactl credentials add` dans un coffre éphémère dédié : Python ne lit ni ne copie la clé, et ni le chemin ni le secret ne sont affichés.

## Démo filmable : Claude Code via relais MCP enfant

### 1. Compiler le CLI compagnon (`stoactl`)

Depuis la branche publiée correspondante du dépôt compagnon STOA v2, dans son sous-répertoire `cli` :

```bash
go build -o /tmp/stoa-demo-stoactl .
```

### 2. Préparer les images locales

Depuis `examples/agent-roles` :

```bash
./scripts/agent_demo.sh --prepare
```

### 3. Lancer la démo réelle (Claude Code)

```bash
STOA_POC_STOACTL_BIN=/tmp/stoa-demo-stoactl ./scripts/agent_demo.sh --api-key-file /path/to/private-0600-file
```

En mode interactif par défaut (sans `--verify-relay` ni `--headless`), la démo exécute le véritable TUI natif de Claude Code dans le volet gauche tmux en mode `--verbose`, affichant directement les réponses d'outils et les `decision_id` (`Ctrl+O` reste disponible en option pour inspecter le transcript natif). Le profil Claude temporaire isolé est automatiquement supprimé au nettoyage en fin de session. Les lignes finales `PROOF`, `ELAPSED` et `UPSTREAM` sont affichées dans le volet droit avec le journal vérifié de la passerelle, sans jamais injecter de texte synthétique dans le volet gauche.

### 4. Vérification du relais sans modèle (`--verify-relay`)

```bash
STOA_POC_STOACTL_BIN=/tmp/stoa-demo-stoactl ./scripts/agent_demo.sh --verify-relay --headless
```

### Notes

- Utiliser une clé Anthropic dédiée dans un fichier propriétaire en mode `0600`. Le compteur `caller_auth_headers_seen` mesure les en-têtes de l’appelant vus par le mock.
- **Profils intacts** : aucun profil utilisateur ou CLI n'est lu ni modifié.
- `--verify-relay` vérifie les appels MCP, la révocation et le journal. Le mode avec `--api-key-file` vérifie aussi le passage de Claude Code.
- **Durée affichée** : mesure monotonic du démarrage et du scénario complet, hors maintien d'affichage final et nettoyage.
- **`tmux`** : socket privé, fermeture automatique en fin de scénario (détachement possible via `Ctrl-b d`).

## Rotation et rétention du journal de décisions

Dans `docker-compose.yml`, `stoa-gateway` écrit le journal dans le volume `role-floors` (`/tmp/stoa-poc-floors/decisions`, `STOA_POC_DECISIONS_DIR`), borné par `STOA_POC_DECISIONS_MAX_BYTES` (défaut `16777216`) et `STOA_POC_DECISIONS_MAX_FILES` (défaut `8`, plafond `64`). L’export sous verrou vers un répertoire privé `0700` s’effectue avec `./scripts/export_decisions.sh /chemin/export-0700` (ou `STOA_POC_DECISIONS_EXPORT_DIR`) et publie `decisions.ndjson` et `decisions.health.json` en mode `0600` sans écrasement.

```bash
./scripts/run_observability.sh --rotation-proof
stoactl decisions report --journal /chemin/decisions.ndjson --from 2026-11-20T00:00:00Z --to 2026-11-21T00:00:00Z -o json
stoactl decisions mark-unexpected 11111111-1111-4111-8111-111111111111 --journal /chemin/decisions.ndjson --draft-dir /chemin/brouillons-0700
```

La preuve `--rotation-proof` (ou `STOA_POC_OBSERVABILITY_ROTATION_PROOF=1`) applique `STOA_POC_ROTATION_PROOF_MAX_BYTES` (défaut `4096`) et `STOA_POC_ROTATION_PROOF_MAX_FILES` (défaut `32`), accepte `STOA_POC_OBSERVABILITY_EVIDENCE_DIR` et `STOA_POC_STOACTL_BIN`, et contrôle `status=healthy`, `active_generation>=1`, `retained_segments>=2`, `expired_segments=0`, `retention_pruned=false` et `gap_detected=false` (sortie `Rotation     · PASS`). Le lecteur `stoactl decisions report` expose `journal_availability`, `journal_active_generation`, `journal_retained_segments`, `journal_expired_segments`, `journal_retention_pruned` et `journal_gap_detected`, distinguant l’expiration planifiée par rétention d’une perte réelle.

## Preuves locales synthétiques (macOS et dock Compose Linux)

```bash
./scripts/run_onboarding.sh --prepare
STOA_POC_STOACTL_BIN=/chemin/absolu/stoactl ./scripts/run_onboarding.sh --client cursor
./scripts/run_relay_dock.sh --prepare
STOA_POC_STOACTL_LINUX_BIN=/chemin/absolu/stoactl-linux ./scripts/run_relay_dock.sh
```

`run_onboarding.sh` accepte `--client cursor`, `--client claude`, `--client codex --codex-bin /chemin/absolu/codex` et `--debug` (ou `STOA_POC_ONBOARDING_DEBUG=1`). Il exécute `plan-only`, confirmation d’empreinte, appel MCP via relais, redémarrage Gateway et broker, `stoactl doctor` sur copie séparée et `stoactl restore` dans un répertoire temporaire jetable sans lire ni modifier les profils utilisateurs réels. `run_relay_dock.sh` monte un binaire ELF Linux en lecture seule et vérifie l’isolation des conteneurs Linux Compose (`network_mode: none`, `read_only`, `cap_drop: ALL`, absence de `docker.sock`, volumes de sockets dédiés).

## Prérequis et migration autorisée sur profil actif

Un profil actif s’établit localement depuis une configuration explicitement provisionnée, sans IdP local de démo. L’opérateur fournit un fichier `--relay-config` en mode `0600` (relais approuvé et preuve d’enrôlement), un broker `stoactl relay serve --config /chemin/relay-config.json` actif et un coffre Vault HTTPS (`VAULT_ADDR=https://...`, `VAULT_TOKEN_FILE` pointant vers un jeton `0600`, `VAULT_CACERT` uniquement pour une CA privée, et un compte de lecture distinct dédié à la Gateway). L’import d’un serveur pair HTTPS exige son origine dans `STOA_POC_IMPORT_ALLOWED_ORIGINS`, distincte de la liste des origines sortantes `STOA_POC_OUTBOUND_ALLOWED_ORIGINS` utilisée par la Gateway pour ses appels amont. L’exécution d’un outil importé, y compris en cas fixture, exige cette autorisation d’origine et la règle `Action::Create` associée à l’outil importé ; la signature de rôle seule ne suffit pas.

```bash
stoactl doctor --client cursor --project-dir /chemin/projet --user-dir /chemin/profil
stoactl init --client cursor --project-dir /chemin/projet --user-dir /chemin/profil --relay-config /chemin/relay-config.json --plan-only
stoactl init --client cursor --project-dir /chemin/projet --user-dir /chemin/profil --relay-config /chemin/relay-config.json --state-dir /chemin/state-0700 --confirm "$PLAN_SHA256"
stoactl restore --state-dir /chemin/state-0700
stoactl restore --state-dir /chemin/state-0700 --transaction "$TX_UUID" --cleanup-remote --relay-config /chemin/relay-config.json
```

Lorsque plusieurs portées coexistent pour le client ciblé, `stoactl init --plan-only` exige `--target-scope` avec un nom complet et affiche les portées candidates dans son diagnostic. Une fois la portée précisée, `--plan-only` masque les champs sensibles (`[MASKED]`), vérifie l’absence de motif bloquant et calcule l’empreinte `SHA-256`. La commande d’application reprend exactement toutes les options de l’aperçu (dont `--relay-config`, `--target-scope` et `--codex-bin` pour Codex) en ajoutant `--state-dir` et `--confirm "$PLAN_SHA256"` (ou accord TTY interactif). `stoactl doctor` utilise les mêmes options de client, de racines et `--codex-bin`, sans `--relay-config`.

| Client | Options de `init --plan-only` et `init --confirm` |
| --- | --- |
| Cursor | `--client cursor --project-dir /chemin/projet --user-dir /chemin/profil --relay-config /chemin/relay-config.json` |
| Claude Code | `--client claude --project-dir /chemin/projet --user-dir /chemin/profil --relay-config /chemin/relay-config.json` |
| Codex | `--client codex --codex-bin /chemin/absolu/codex --project-dir /chemin/projet --user-dir /chemin/profil --relay-config /chemin/relay-config.json` |

| Client | Valeurs complètes admises pour `--target-scope` |
| --- | --- |
| Cursor | `cursor_project`, `cursor_user` |
| Claude Code | `claude_project`, `claude_user_project`, `claude_user_root` |
| Codex | `codex_project`, `codex_user` |

## Limites connues

- Les deux budgets chaîne et appelant racine résident en mémoire et repartent à zéro au redémarrage du processus Gateway. La démo simule les remboursements.
- Le fichier de plancher stocke la version et l’empreinte de la politique signée dans le volume Compose `role-floors` en mode `0600` et les conserve après redémarrage et recréation tant que le volume existe. La commande `docker compose down -v` retire ce volume.
- Seul le transport Streamable HTTP statique au schéma admis est importé. Aucun import STDIO arbitraire, OAuth tiers ni SSE legacy n’est admis, et les scopes incompatibles ne sont jamais supprimés.
- Les sauvegardes chiffrées et `stoactl restore` local conservent les secrets dans Vault. Le nettoyage distant côté Gateway s’exécute uniquement avec `--cleanup-remote --relay-config`, aucun nettoyage de secret n’intervient sans reçu, et `restore` rétablit localement les secrets historiques en échouant si le profil a été modifié depuis la migration.
- Le broker en mémoire ne transmet aucun secret au processus agent. L’exécution sur un même UID hôte sans dock reste une limite d’isolation OS, le dock Compose Linux isole les instances étroites, et les appels hors MCP ne passent pas par la passerelle.
