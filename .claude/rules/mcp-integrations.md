---
description: MCP server integrations — Linear, Cloudflare, Vercel, Notion, n8n usage patterns and workflows
globs: "stoa-gateway/src/mcp/**,stoa-gateway/src/oauth/**,.claude/skills/**,.claude/agents/**"
---

# MCP Integrations — Claude.ai Native Services

## Available MCP Servers

Connected via Claude.ai account settings (not local `.claude/settings.json`).

| Server | Tools | Use For | Auth |
|--------|-------|---------|------|
| **Linear** | 37 | Ticket management, sprint tracking, issue lifecycle | OAuth (Claude.ai) |
| **Notion** | 12 | Knowledge base, meeting notes, search across workspace | OAuth (Claude.ai) |
| **Cloudflare** | 21 | DNS records, KV, R2, Workers, D1 databases | API token (Claude.ai) |
| **Vercel** | 11 | stoa-web deploys, build logs, runtime logs | OAuth (Claude.ai) |
| **n8n** | 3 | Workflow execution, orchestration | API key (Claude.ai) |

## Linear Integration

### Team & Project IDs (cached)

| Entity | ID | Name |
|--------|----|------|
| Team | `624a9948-a160-4e47-aba5-7f9404d23506` | CAB-ING |
| Project | `227427af-6844-484d-bb4a-dedeffc68825` | STOA Platform |
| Assignee | `0543749d-ecde-4edf-aec1-6f372aafafce` | Christophe ABOULICAM |

### When to Use Linear MCP

| Trigger | Action | Tool |
|---------|--------|------|
| **Session start** (task from plan.md) | Fetch ticket details + DoD | `get_issue(id, includeRelations=true)` |
| **PR merged** | Update issue → Done, add PR link | `update_issue(id, state="Done")` + `create_comment` |
| **Blocked** | Update issue → Blocked, add context | `update_issue(id, state="Blocked")` + `create_comment` |
| **Sub-task discovered** | Create child issue | `create_issue(title, parentId, team)` |
| **Need cycle context** | Get current sprint issues | `list_cycles(teamId, type="current")` + `list_issues` |
| **DoD verification** | Read issue description for acceptance criteria | `get_issue(id)` |
| **Council validation** | Auto-create ticket on score >= 8/10 | `/council` skill → `create_issue` |
| **Plan sync** | Drift detection plan.md ↔ Linear | `/sync-plan` skill → batch `get_issue` |

### When NOT to Use Linear MCP

- Ship-mode docs/config changes (no ticket overhead)
- Typo fixes, formatting (no tracking value)
- Memory/plan file updates (internal state, not Linear)

### Linear Workflow Integration

```
SESSION START:
  1. Read memory.md + plan.md (local state)
  2. IF task has CAB-XXXX ID:
     → linear.get_issue("CAB-XXXX") for DoD + description
     → linear.update_issue(status="In Progress") if status is "Todo"
  3. Log SESSION-START in operations.log

PR MERGED:
  1. linear.update_issue(id, state="Done")
  2. linear.create_comment(issueId, body="Completed in PR #XXX ...")
  3. Update memory.md + plan.md (local state)

SESSION END:
  1. IF paused: linear.update_issue(status="In Progress") — keep as-is
  2. IF blocked: linear.update_issue(status="Blocked") + create_comment(reason)
  3. Log SESSION-END
```

### Linear Issue Commenting Template

When adding PR completion comment:
```markdown
Completed in PR #XXX (merged to main)

**Changes**: <1-2 line summary>
**Files**: <count> files, ~<LOC> LOC
**Tests**: <pass/fail status>
**CI**: [Pipeline #YYYY](link) — ✅ green
**E2E**: @smoke pass | N/A (docs-only)
**Pod**: `<image:tag>` running in stoa-system | N/A (no deploy)
**Mode**: Ship | Show | Ask
```

## Cloudflare Integration

### When to Use Cloudflare MCP

| Trigger | Action | Tool |
|---------|--------|------|
| **DNS verification** | Check record exists | `search_cloudflare_documentation` or manual curl |
| **New subdomain needed** | Verify availability | Check via API |
| **Troubleshoot DNS** | List records | Use `accounts_list` + zone tools |

### STOA DNS Zone

- Zone: `gostoa.dev` (`748bf095e4882ca8e46f21837067ced8`)
- Proxy: OFF (DNS-only, TLS terminated at OVH/Hetzner)
- Management: Cloudflare API token in Infisical

**Note**: DNS record CRUD requires the Cloudflare API directly (no MCP tool for DNS records yet). Use Cloudflare MCP for docs, Workers, KV, R2, D1 operations.

## Vercel Integration

### When to Use Vercel MCP

| Trigger | Action | Tool |
|---------|--------|------|
| **stoa-web deploy check** | Verify deployment status | `get_deployment` or `list_deployments` |
| **stoa-docs deploy check** | Verify Vercel preview | `get_deployment` |
| **Build failure triage** | Read build logs | `get_deployment_build_logs` |
| **Runtime error** | Read runtime logs | `get_runtime_logs` |
| **Docs question** | Search Vercel docs | `search_vercel_documentation` |

### STOA Vercel Projects

| Project | Repo | URL |
|---------|------|-----|
| stoa-docs | stoa-platform/stoa-docs | docs.gostoa.dev |
| stoa-web | stoa-platform/stoa-web | gostoa.dev |

## Notion Integration

### When to Use Notion MCP

| Trigger | Action | Tool |
|---------|--------|------|
| **Search workspace** | Find related docs | `notion-search(query)` |
| **Read page content** | Fetch full page | `notion-fetch(id)` |
| **Create meeting notes** | Document decisions | `notion-create-pages` |
| **Query database** | Find entries | `notion-query-database-view` |

**Note**: Only use if workspace is actively used. Prefer stoa-docs (Docusaurus) for public documentation.

## n8n Integration

### When to Use n8n MCP

| Trigger | Action | Tool |
|---------|--------|------|
| **List workflows** | Discover available automations | `search_workflows` |
| **Trigger automation** | Execute a workflow | `execute_workflow(workflowId, inputs)` |
| **Check workflow config** | Read workflow details | `get_workflow_details(workflowId)` |

**Note**: n8n acts as MCP proxy for services without native MCP (Jira, Salesforce, SMTP, etc.).

## Cost & Performance Rules

| Rule | Rationale |
|------|-----------|
| **Cache IDs** in this file | Avoid repeated list/search calls for known entities |
| **Batch reads, not writes** | Read multiple issues in one session, write only on state changes |
| **Don't poll** | No periodic "check Linear status" loops — trigger-based only |
| **Log MCP calls** in operations.log | Audit trail: `MCP-CALL \| service=linear action=update_issue id=CAB-XXXX` |
| **Prefer `get_issue` over `list_issues`** | Direct lookup by ID is faster + cheaper |
| **Never store tokens** | MCP auth is managed by Claude.ai — never log or cache tokens |

## Security Rules

- **Never write secrets** via MCP (Cloudflare KV, Notion pages)
- **Never delete** production resources via MCP without explicit user confirmation
- **Cloudflare Workers/D1**: read-only unless user explicitly requests changes
- **Linear**: don't create issues in other people's names (always use current assignee)
- **Notion**: don't create pages in workspaces you don't own
- **Vercel**: don't trigger deploys without explicit request
