# AI Factory Autonomous — Setup Guide

## Prerequisites

- GitHub repo admin access (stoa-platform/stoa)
- Anthropic API key with sufficient credits
- Slack workspace with incoming webhook
- n8n instance (for Level 3)

## Step 1: Install Claude GitHub App

```bash
# Option A: Automatic (from Claude Code CLI)
claude /install-github-app

# Option B: Manual
# 1. Install: https://github.com/apps/claude
# 2. Grant permissions: Contents (RW), Issues (RW), Pull Requests (RW)
# 3. Select repository: stoa-platform/stoa
```

## Step 2: Add GitHub Secrets

Go to: `Settings > Secrets and variables > Actions > New repository secret`

| Secret | Value | Required For |
|--------|-------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | All claude-* workflows |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL | Slack notifications |

### Get Slack Webhook URL

1. Go to https://api.slack.com/apps
2. Create a new app (or use existing) > Incoming Webhooks > Activate
3. Add New Webhook to Workspace > Select channel (e.g., `#stoa-ai-factory`)
4. Copy the webhook URL

## Step 3: Create GitHub Labels

Create these labels in your repository (Settings > Labels):

| Label | Color | Description |
|-------|-------|-------------|
| `claude-implement` | `#6f42c1` | Triggers autonomous Council + implementation |
| `council-review` | `#fbca04` | Issue has pending Council review |
| `self-improve` | `#0e8a16` | AI Factory self-improvement proposal |
| `daily-digest` | `#c5def5` | Daily triage digest |
| `weekly-audit` | `#bfd4f2` | Weekly audit report |
| `ci-failure` | `#d73a4a` | CI failure requiring attention |
| `coverage-drop` | `#e4e669` | Test coverage regression |

## Step 4: Test Level 1

```bash
# Test @claude mention
# Go to any issue or PR, comment: @claude what files handle authentication?

# Test auto-review
# Open a new PR — claude-review.yml should trigger automatically

# Test issue-to-PR
# Create an issue, add label "claude-implement"
# Wait for Council report on the issue
# Comment "/go" to start implementation
```

## Step 5: Setup n8n (Level 3)

1. Open your n8n instance
2. Import `scripts/ai-ops/n8n-linear-to-claude.json`
3. Configure credentials:
   - HTTP Header Auth: `Authorization: Bearer <GITHUB_PAT>` (needs `repo` scope)
   - Set environment variable: `SLACK_WEBHOOK=<your-webhook-url>`
4. Configure Linear webhook:
   - Go to Linear > Settings > API > Webhooks
   - URL: `https://<your-n8n>/webhook/stoa-linear-webhook`
   - Events: Issue updates
5. Activate the workflow

## Step 5b: Setup Merge PR Relay (Ask Mode)

1. Import `scripts/ai-ops/n8n-merge-pr.json` into n8n
2. Ensure the workflow uses the same `GitHub PAT` credential and `APPROVE_HMAC_SECRET` variable as the approve-ticket workflow
3. Add repo variable: `Settings > Secrets and variables > Actions > Variables > New repository variable`
   - Name: `N8N_MERGE_WEBHOOK_URL`
   - Value: `https://<your-n8n>/webhook/merge-pr`
4. Activate the workflow in n8n

This adds a one-click "Merge PR" button to Ask-mode Slack notifications. Without this variable, the button falls back to linking directly to the PR.

## Step 6: Verify Scheduled Tasks (Level 2)

Scheduled tasks start automatically after merge to main.
To test immediately:

```bash
# Trigger manually via GitHub CLI
gh workflow run claude-scheduled.yml -f task=daily-triage
gh workflow run claude-scheduled.yml -f task=daily-ci-health
gh workflow run claude-scheduled.yml -f task=weekly-audit
```

## Step 7: Test Multi-Agent (Level 5)

```bash
# Dispatch parallel agents for multiple tickets
gh workflow run claude-multi-agent.yml -f tickets="CAB-1200,CAB-1201"
```

## Cost Estimates

| Level | Frequency | Est. Monthly Cost |
|-------|-----------|------------------|
| L1: Interactive | On-demand | ~$5-20 (depends on usage) |
| L2: Scheduled | 2x daily + 1x weekly | ~$30-50 |
| L3: Linear Pipeline | Per ticket (~10/week) | ~$20-40 |
| L4: Self-Improve | 1x weekly | ~$5-10 |
| L5: Multi-Agent | On-demand | ~$10-30 per batch |
| **Total** | | **~$70-150/month** |

All estimates assume Sonnet model. Opus would be ~10x more.

## Monitoring

- **GitHub Actions**: Check workflow runs at `Actions` tab
- **Slack**: All notifications in your configured channel
- **Costs**: Monitor at https://console.anthropic.com/usage
