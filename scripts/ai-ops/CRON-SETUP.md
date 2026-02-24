# Veille Competitive — Cron Setup

## Architecture

```
watch-collect.sh (2x/jour)          watch-digest.sh (1x/semaine)
  ├── Anthropic blog                   ├── Lit signals-YYYY-WNN.jsonl
  ├── npm Claude Code version          ├── Deduplique (source+title)
  ├── Reddit r/ClaudeAI                ├── Trie par score
  ├── Hacker News                      ├── Formate le digest
  ├── Cursor changelog                 └── (optionnel) Post Slack
  └── Aider changelog
          │
          ▼
  .claude/watch/signals-YYYY-WNN.jsonl (append-only, gitignored)
```

## Option A: crontab (Linux / macOS)

```bash
# Editer crontab
crontab -e

# Collect 2x/jour (08:00 + 18:00 CET = 07:00 + 17:00 UTC)
0 7,17 * * * cd /path/to/stoa && bash scripts/ai-ops/watch-collect.sh >> /tmp/watch-collect.log 2>&1

# Digest chaque lundi 08:00 CET (07:00 UTC)
0 7 * * 1 cd /path/to/stoa && bash scripts/ai-ops/watch-digest.sh >> /tmp/watch-digest.log 2>&1
```

## Option B: launchd (macOS natif)

### Collector (2x/jour)

Creer `~/Library/LaunchAgents/dev.gostoa.watch-collect.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.gostoa.watch-collect</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/path/to/stoa/scripts/ai-ops/watch-collect.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key><integer>8</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>18</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/stoa</string>
    <key>StandardOutPath</key>
    <string>/tmp/watch-collect.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/watch-collect.log</string>
</dict>
</plist>
```

### Digest (lundi 08:00)

Creer `~/Library/LaunchAgents/dev.gostoa.watch-digest.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.gostoa.watch-digest</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/path/to/stoa/scripts/ai-ops/watch-digest.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key><integer>1</integer>
        <key>Hour</key><integer>8</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>/path/to/stoa</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>SLACK_WEBHOOK</key>
        <string>https://hooks.slack.com/services/YOUR/WEBHOOK/URL</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/watch-digest.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/watch-digest.log</string>
</dict>
</plist>
```

### Activer launchd

```bash
# Remplacer /path/to/stoa par le vrai chemin
sed -i '' "s|/path/to/stoa|$(pwd)|g" ~/Library/LaunchAgents/dev.gostoa.watch-*.plist

# Charger les agents
launchctl load ~/Library/LaunchAgents/dev.gostoa.watch-collect.plist
launchctl load ~/Library/LaunchAgents/dev.gostoa.watch-digest.plist

# Verifier
launchctl list | grep gostoa

# Test manuel
launchctl start dev.gostoa.watch-collect
```

## Option C: n8n workflow

Importer `scripts/ai-ops/n8n-workflows/competitive-watch.json` dans n8n.

Le workflow a 2 phases:
1. **Phase Collect** (Schedule: 2x/jour) — HTTP Request nodes + Code node qui ecrit en JSONL
2. **Phase Digest** (Schedule: lundi) — Lit le JSONL, deduplique, formate, poste Slack

## Variables d'environnement

| Variable | Obligatoire | Usage |
|----------|-------------|-------|
| `SLACK_WEBHOOK` | Non | URL webhook Slack pour poster le digest |

## Fichiers de signaux

- Emplacement: `.claude/watch/signals-YYYY-WNN.jsonl`
- Format: une ligne JSON par signal (JSONL)
- Retention: gitignored, local uniquement
- Nettoyage: supprimer les fichiers > 4 semaines manuellement

### Format JSONL

```json
{"ts":"2026-02-24T08:00:00+00:00","source":"reddit","title":"Claude Code hooks","url":"https://...","score":142,"meta":{}}
```

| Champ | Type | Description |
|-------|------|-------------|
| `ts` | ISO 8601 | Timestamp de collecte (UTC) |
| `source` | string | `anthropic`, `npm`, `reddit`, `hn`, `cursor`, `aider` |
| `title` | string | Titre du signal (max 120 chars) |
| `url` | string | Lien vers la source |
| `score` | int | Score communautaire (upvotes, points). 0 si N/A |
| `meta` | object | Metadata additionnelle (ex: `{"version":"1.2.3"}`) |

### Deduplication

Cle: `source + "::" + title.strip().lower()`

Un signal avec la meme source et le meme titre (case-insensitive) n'est jamais ajoute deux fois.
