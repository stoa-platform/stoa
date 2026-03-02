# Runbook: Chat Agent — Admin Setup & Configuration

> **Severity**: Medium
> **Last updated**: 2026-03-02
> **Owner**: Platform Team
> **Linear Issue**: CAB-286

---

## Overview

The STOA Console includes an integrated AI chat assistant powered by Anthropic Claude.
This runbook covers how to enable, configure, and troubleshoot the chat feature.

### Architecture

```
Console UI (FloatingChat widget)
    │
    │  POST /v1/tenants/{id}/chat/conversations           → Create conversation
    │  POST /v1/tenants/{id}/chat/conversations/{id}/messages → Send + SSE stream
    │
    ▼
Control Plane API (FastAPI)
    │
    │  ChatService → reads tenant API key from DB (encrypted)
    │  ChatService → calls Anthropic Messages API (SSE streaming)
    │
    ▼
Anthropic API (api.anthropic.com)
```

---

## 1. Prerequisites

### Environment Variable

The chat feature is **disabled by default**. Enable it by setting:

```bash
CHAT_ENABLED=True
```

This env var must be set on the `stoa-control-plane-api` deployment. Without it, the chat
router is not registered and all `/chat/*` endpoints return 404.

**Verify in K8s:**
```bash
KUBECONFIG=~/.kube/config-stoa-ovh kubectl exec -n stoa-system \
  deploy/stoa-control-plane-api -- env | grep CHAT_ENABLED
# Expected: CHAT_ENABLED=True
```

### Database Migrations

Chat requires 3 tables created by alembic migrations:

| Table | Migration | Purpose |
|-------|-----------|---------|
| `chat_conversations` | 038 | Conversation metadata (tenant, user, model, provider) |
| `chat_messages` | 038 | Messages with role (user/assistant/system), content, tokens |
| `chat_token_usage` | 040 | Per-user daily token consumption tracking |

**Verify tables exist:**
```bash
KUBECONFIG=~/.kube/config-stoa-ovh kubectl exec -n stoa-system \
  deploy/stoa-control-plane-api -- python3 -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
async def check():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async with engine.connect() as c:
        for t in ['chat_conversations','chat_messages','chat_token_usage']:
            r = await c.execute(text(f\"SELECT EXISTS(SELECT FROM information_schema.tables WHERE table_name='{t}')\"))
            print(f'  {t}: {\"OK\" if r.scalar() else \"MISSING\"} ')
    await engine.dispose()
asyncio.run(check())
"
```

If tables are missing, run migrations:
```bash
KUBECONFIG=~/.kube/config-stoa-ovh kubectl exec -n stoa-system \
  deploy/stoa-control-plane-api -- alembic upgrade head
```

### Anthropic API Key

Each tenant needs an Anthropic API key configured. The key is stored **encrypted** (Fernet AES-128-CBC)
in the tenant's `settings` JSON column.

---

## 2. Configure API Key for a Tenant

### Option A: Via API (recommended)

Use the admin endpoint to set the tenant-level API key:

```bash
# 1. Get an admin auth token from Keycloak
TOKEN=$(curl -s -X POST "${STOA_AUTH_URL}/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=control-plane-api" \
  -d "client_secret=${KC_CLIENT_SECRET}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Or use a user token (must have cpi-admin or tenant-admin role):
TOKEN=$(curl -s -X POST "${STOA_AUTH_URL}/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=control-plane-ui" \
  -d "username=parzival@oasis.gg" \
  -d "password=${USER_PASSWORD}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Set the API key
curl -s -X PUT "${STOA_API_URL}/v1/tenants/${TENANT_ID}/chat/provider-key" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-ant-api03-YOUR-ANTHROPIC-KEY-HERE"}'
# Expected: HTTP 204 (no content)
```

**Required role**: `cpi-admin` or `tenant-admin`

### Option B: Via Pod (direct DB update)

For initial setup or debugging, set the key directly from inside the pod:

```bash
KUBECONFIG=~/.kube/config-stoa-ovh kubectl exec -n stoa-system \
  deploy/stoa-control-plane-api -- python3 -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

TENANT_ID = 'free-torpedo'        # <-- change to your tenant ID
API_KEY = 'sk-ant-api03-...'      # <-- your Anthropic API key

async def set_key():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    # Import encryption service within the pod's Python path
    import sys; sys.path.insert(0, '/app')
    from src.services.encryption_service import encrypt_auth_config
    import json

    encrypted = encrypt_auth_config({'api_key': API_KEY})

    async with engine.begin() as conn:
        # Read current settings
        r = await conn.execute(text('SELECT settings FROM tenants WHERE id = :id'), {'id': TENANT_ID})
        row = r.first()
        if not row:
            print(f'ERROR: tenant {TENANT_ID} not found')
            return
        settings = row[0] or {}
        if isinstance(settings, str):
            settings = json.loads(settings)

        # Update with encrypted key
        settings['chat_provider_api_key'] = encrypted
        await conn.execute(
            text('UPDATE tenants SET settings = :s WHERE id = :id'),
            {'s': json.dumps(settings), 'id': TENANT_ID}
        )
        print(f'API key set for tenant {TENANT_ID}')
    await engine.dispose()

asyncio.run(set_key())
"
```

### Option C: Via Console UI

Users can also send their API key per-request via the `X-Provider-Api-Key` HTTP header.
The backend checks in this order:

1. `X-Provider-Api-Key` header (per-request, no storage)
2. Tenant `settings.chat_provider_api_key` (encrypted in DB)
3. If neither exists → HTTP 400: "No API key"

---

## 3. Verify Chat is Working

### API-level test

```bash
# 1. Create a conversation
CONV_ID=$(curl -s -X POST "${STOA_API_URL}/v1/tenants/${TENANT_ID}/chat/conversations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test conversation"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "Conversation: $CONV_ID"

# 2. Send a message and read the SSE stream
curl -s -N -X POST "${STOA_API_URL}/v1/tenants/${TENANT_ID}/chat/conversations/${CONV_ID}/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello, respond with just the word OK"}' 2>&1 | head -20
```

**Expected SSE output:**
```
event: message_start
data: {"conversation_id": "..."}

event: content_delta
data: {"delta": "OK"}

event: message_end
data: {"message_id": "...", "usage": {"input_tokens": ..., "output_tokens": ...}}
```

### Browser test

1. Open `https://console.gostoa.dev`
2. Log in as an admin user
3. Click the chat bubble (bottom-right corner)
4. Type "Hello" and press Enter
5. Verify a response appears (not "(no response)")

---

## 4. Chat API Endpoints Reference

All endpoints are under `POST /v1/tenants/{tenant_id}/chat/`.

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/conversations` | User | Create a new conversation |
| `GET` | `/conversations` | User | List conversations (with pagination, status filter) |
| `GET` | `/conversations/{id}` | User | Get conversation with messages |
| `PATCH` | `/conversations/{id}` | User | Rename a conversation |
| `POST` | `/conversations/{id}/messages` | User | Send message + stream response (SSE) |
| `PATCH` | `/conversations/{id}/archive` | User | Archive or restore a conversation |
| `DELETE` | `/conversations/{id}` | User | Delete a conversation |
| `DELETE` | `/conversations` | Admin | Delete ALL conversations for a tenant |
| `DELETE` | `/conversations/purge` | Admin | GDPR purge (archived > N days) |
| `GET` | `/usage` | User | Token usage for current user |
| `GET` | `/usage/tenant` | Admin | Token usage for entire tenant |
| `GET` | `/usage/budget` | User | Token budget status |
| `GET` | `/usage/metering` | Admin | Aggregated usage statistics |
| `PUT` | `/provider-key` | Admin | Set tenant-level Anthropic API key |

---

## 5. Configuration Reference

### Environment Variables (Control Plane API)

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_ENABLED` | `False` | Enable/disable chat feature (router registration) |
| `CHAT_TOKEN_BUDGET_DAILY` | `0` | Daily token budget per user (0 = unlimited) |
| `BACKEND_ENCRYPTION_KEY` | dev key | Fernet key for encrypting API keys at rest |

### Tenant Settings (JSON column)

| Key | Type | Description |
|-----|------|-------------|
| `chat_provider_api_key` | string (encrypted) | Fernet-encrypted Anthropic API key |

### Default Model

The chat creates conversations with `claude-sonnet-4-20250514` by default. Users can override
the model when creating a conversation via the API.

---

## 6. Troubleshooting

### "(no response)" in the chat widget

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| No API key configured | Check tenant `settings` for `chat_provider_api_key` | Set key via `PUT /provider-key` |
| Chat tables missing | Query `information_schema.tables` | Run `alembic upgrade head` |
| `CHAT_ENABLED=False` | Check pod env | Set `CHAT_ENABLED=True` in deployment |
| Invalid/expired API key | Check pod logs for Anthropic 401 | Update the API key |
| Tenant not found | 404 on conversation create | Verify tenant ID in DB |

### Check pod logs for chat errors

```bash
KUBECONFIG=~/.kube/config-stoa-ovh kubectl logs -n stoa-system \
  deploy/stoa-control-plane-api --tail=100 --since=5m | grep -i chat
```

### Verify encryption key consistency

If the API key was set with a different `BACKEND_ENCRYPTION_KEY` than the one currently in the pod,
decryption will fail silently. Verify:

```bash
KUBECONFIG=~/.kube/config-stoa-ovh kubectl exec -n stoa-system \
  deploy/stoa-control-plane-api -- python3 -c "
import asyncio, os, sys
sys.path.insert(0, '/app')
from src.services.chat_service import ChatService
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

async def test():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    factory = async_sessionmaker(engine, class_=AsyncSession)
    async with factory() as session:
        svc = ChatService(session)
        key = await svc.get_tenant_api_key('TENANT_ID_HERE')
        if key:
            print(f'Key decrypted OK (starts with: {key[:12]}...)')
        else:
            print('No key found or decryption failed')
    await engine.dispose()

asyncio.run(test())
"
```

### Token budget exceeded

If `CHAT_TOKEN_BUDGET_DAILY > 0`, users may hit their daily limit. Check via:

```bash
curl -s "${STOA_API_URL}/v1/tenants/${TENANT_ID}/chat/usage/budget" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 7. Security Notes

- API keys are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256)
- The `BACKEND_ENCRYPTION_KEY` is the master key — if lost, all stored API keys become unreadable
- Per-request keys via `X-Provider-Api-Key` header are **not stored** (transit only)
- Only `cpi-admin` and `tenant-admin` roles can set the tenant-level key
- Chat messages are stored in the database — consider GDPR retention policies (`DELETE /conversations/purge`)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-03-02 | Claude Code | Initial creation (CAB-286) |
