# 🏭 STOA AI Factory

> Claude Code H24 + Orchestration Humaine

## 🎯 Concept

**Tu n'es plus un Project Manager. Tu es un Architect qui supervise un AI Agent.**

```
┌─────────────────────────────────────────────────────────┐
│              CHRISTOPHE = ARCHITECT                     │
│  • Définit PHASEs (objectif + contraintes)              │
│  • Valide PLANs avant GO                                │
│  • Review checkpoints Slack                             │
│  • Décision GO/NOGO sur PRs                             │
└─────────────────────────────────────────────────────────┘
                         │
               Plan + Context + Rules
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              CLAUDE CODE = AI WORKER H24                │
│                                                         │
│   Code → Test → Verify → Commit → Loop                  │
│                    │                                    │
│          Si bloqué/checkpoint → SLACK                   │
└─────────────────────────────────────────────────────────┘
```

## 📁 Structure

```
.stoa-ai/
├── CLAUDE.md              # Contexte global (lire au début)
├── memory.md              # État session courante
├── templates/
│   ├── MEGA-TICKET.md     # Template ticket Linear
│   ├── PHASE-PLAN.md      # Template plan.md
│   └── PROMPT-ENTRY.md    # Prompt d'entrée Claude Code
├── phases/
│   └── CAB-XXXX/          # Un dossier par phase
│       ├── plan.md        # Plan détaillé de la phase
│       ├── context.md     # Contexte spécifique (optionnel)
│       └── logs/          # Logs des sessions
├── scripts/
│   ├── run-phase.sh       # Lancer une phase
│   ├── slack-notify.sh    # Envoyer notification
│   └── daily-digest.sh    # Résumé quotidien
└── n8n/
    └── ai-phase-runner.json  # Workflow n8n à importer
```

## 🚀 Quick Start

### 1. Configuration

```bash
# Copier dans ton repo STOA
cp -r .stoa-ai/ /path/to/stoa/

# Rendre les scripts exécutables
chmod +x .stoa-ai/scripts/*.sh

# Configurer Slack webhook
export SLACK_WEBHOOK="https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

### 2. Créer une Phase

```bash
# Créer le dossier de phase
mkdir -p .stoa-ai/phases/CAB-XXXX

# Copier le template
cp .stoa-ai/templates/PHASE-PLAN.md .stoa-ai/phases/CAB-XXXX/plan.md

# Éditer le plan avec tes steps spécifiques
vim .stoa-ai/phases/CAB-XXXX/plan.md
```

### 3. Lancer Claude Code

```bash
# Option A: Script automatique (tmux)
./stoa-ai/scripts/run-phase.sh CAB-XXXX

# Option B: Manuel avec prompt
claude "Lis .stoa-ai/CLAUDE.md, memory.md, et phases/CAB-XXXX/plan.md. Exécute le plan."
```

### 4. Surveiller via Slack

Les notifications arrivent automatiquement:
- 🟢 Phase terminée
- 🟡 Décision nécessaire
- 🔴 Tests échoués

## 🔄 Workflow Complet

### Toi (5-10 min par phase)

1. **Créer MEGA-ticket** dans Linear avec objectif clair
2. **Rédiger plan.md** avec steps détaillés
3. **Valider via Council** (score 8/10 minimum)
4. **Lancer** `./run-phase.sh CAB-XXXX`
5. **Attendre** notifications Slack
6. **Review** et Approve/Request Changes

### Claude Code (autonome)

```
loop:
  1. Lire plan.md → identifier next step
  2. Coder le step
  3. Lancer tests
  4. Si pass → commit + update plan.md + continue
  5. Si fail → retry 2x → Slack alert
  6. Si question → Slack alert + wait
  7. Si phase done → Slack "Review needed" + stop
```

## 📱 Intégration Slack

### Créer le Webhook

1. Aller sur https://api.slack.com/apps
2. Create New App → From scratch
3. Incoming Webhooks → Activate
4. Add New Webhook to Workspace
5. Choisir le channel `#stoa-ai-worker`
6. Copier l'URL du webhook

### Test Manuel

```bash
export SLACK_WEBHOOK="https://hooks.slack.com/services/..."
./.stoa-ai/scripts/slack-notify.sh done CAB-1068 "Test notification"
```

## ⚙️ Intégration n8n

### Importer le Workflow

1. Ouvrir n8n
2. Workflows → Import from File
3. Sélectionner `.stoa-ai/n8n/ai-phase-runner.json`
4. Configurer les credentials:
   - `SLACK_WEBHOOK` dans les variables d'environnement n8n
   - Chemin vers le repo STOA

### Configurer Linear Webhook

1. Linear → Settings → Integrations → Webhooks
2. Add Webhook
3. URL: `https://your-n8n-instance/webhook/stoa-phase-trigger`
4. Events: Issue updated

## 📊 Daily Digest

Configurer un cron pour le résumé quotidien:

```bash
# Éditer crontab
crontab -e

# Ajouter (tous les jours à 9h)
0 9 * * * cd /path/to/stoa && ./.stoa-ai/scripts/daily-digest.sh
```

## 🏷️ Références

- [Anthropic Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [AWS AI-DLC](https://aws.amazon.com/blogs/devops/open-sourcing-adaptive-workflows-for-ai-driven-development-life-cycle-ai-dlc/)
- CAB-1068 — Ticket de setup
- CAB-1051 — Mode Phase concept

---

*"Claude Code ne dort jamais. Christophe orchestre et valide."*
