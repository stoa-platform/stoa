# Plan: CAB-1068 — AI Factory Setup

> Ce fichier guide Claude Code. Mettre à jour les checkboxes au fur et à mesure.

## 🎯 Objectif de cette Phase

Mettre en place l'infrastructure AI Factory pour permettre à Claude Code de travailler H24 en autonomie supervisée.

## 📋 Contexte

- **MEGA parent**: CAB-1068
- **Branche**: `christopheabcabi/cab-1068-mega-ai-factory-setup-claude-code-h24-orchestration`
- **Fichiers principaux**: 
  - `.stoa-ai/CLAUDE.md`
  - `.stoa-ai/memory.md`
  - `.stoa-ai/scripts/*.sh`

## ✅ Steps

### Step 1: Structure de base
- [x] Créer `.stoa-ai/` directory
- [x] Créer `CLAUDE.md` avec contexte projet
- [x] Créer `memory.md` template
- [ ] Valider structure dans le repo STOA

### Step 2: Templates
- [x] Créer `templates/MEGA-TICKET.md`
- [x] Créer `templates/PHASE-PLAN.md`
- [x] Créer `templates/PROMPT-ENTRY.md`

### Step 3: Scripts d'automatisation
- [x] Créer `scripts/run-phase.sh`
- [x] Créer `scripts/slack-notify.sh`
- [x] Créer `scripts/daily-digest.sh`
- [ ] Rendre les scripts exécutables (`chmod +x`)
- [ ] Tester localement

### Step 4: Slack Integration
- [ ] Créer channel `#stoa-ai-worker`
- [ ] Créer Slack App avec Incoming Webhook
- [ ] Configurer `SLACK_WEBHOOK` env var
- [ ] Tester notification manuelle

### Step 5: n8n Workflow
- [ ] Créer workflow "AI Phase Runner"
- [ ] Trigger: Linear webhook (status change)
- [ ] Action: Clone + Run Claude Code
- [ ] Action: Slack notify on completion
- [ ] Tester E2E

### Step 6: Premier test réel
- [ ] Choisir un petit ticket existant
- [ ] Créer sa phase dans `.stoa-ai/phases/`
- [ ] Lancer `./run-phase.sh CAB-XXXX`
- [ ] Observer le comportement
- [ ] Documenter les learnings

## 🚫 Ne PAS faire

- Ne pas modifier l'architecture STOA existante
- Ne pas créer de dépendances bloquantes
- Ce setup doit être 100% optionnel

## 🔔 Checkpoints Slack

Envoyer notification si:
- [x] Structure créée → `🟢 Structure ready`
- [ ] Scripts testés → `🟢 Scripts ready`
- [ ] Slack configuré → `🟢 Slack ready`
- [ ] Premier test OK → `🟢 AI Factory operational`

## 📊 Progression

| Step | Status | Temps |
|------|--------|-------|
| Step 1: Structure | ✅ DONE | 10min |
| Step 2: Templates | ✅ DONE | 15min |
| Step 3: Scripts | 🔄 IN PROGRESS | - |
| Step 4: Slack | ⬜ TODO | - |
| Step 5: n8n | ⬜ TODO | - |
| Step 6: Test | ⬜ TODO | - |

---

*Créé: 2026-02-04*
*Dernière update: 2026-02-04 12:20*
