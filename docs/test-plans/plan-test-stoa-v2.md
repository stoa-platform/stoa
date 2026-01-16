# Plan de Test - Session Debug STOA Platform v2

> **Version** : 2.0  
> **Date** : 16 janvier 2026  
> **Améliorations** : Tests RBAC négatifs, Error Snapshot, E2E complet, Cleanup

---

## Objectif

Valider le fonctionnement de toutes les fonctionnalités UI et backend, incluant la connexion MCP avec Claude.ai, avec vérification complète des logs et traces.

---

## Contexte Kubernetes Actuel

| Composant | Pod | Status |
|-----------|-----|--------|
| Control-Plane-API | control-plane-api-b6d9466f4-* (x2) | Running |
| Control-Plane-UI | control-plane-ui-5f57f944b-l47pq | Running |
| MCP Gateway | mcp-gateway-54cbc9b4b4-48g6x | Running |
| Developer Portal | devportal-55455d7c56-nf88s | Running |
| Keycloak | keycloak-6d5b5d94fd-4f6kx | Running |
| PostgreSQL | control-plane-db-0 | Running |
| MinIO | minio-6d5d4cd8fd-mpw9h | Running |

### URLs de Production

| Service | URL |
|---------|-----|
| Console UI | https://console.stoa.cab-i.com |
| Developer Portal | https://portal.stoa.cab-i.com |
| API Gateway | https://apis.stoa.cab-i.com |
| MCP Gateway | https://mcp.stoa.cab-i.com |
| Keycloak | https://auth.stoa.cab-i.com |

---

## Phase 1: Vérification Infrastructure (Read-Only)

### 1.1 Health Checks des Services

```bash
# MCP Gateway
curl -s https://mcp.stoa.cab-i.com/health | jq

# Control Plane API (direct)
curl -s https://api.stoa.cab-i.com/health | jq

# Control Plane API (via Gateway)
curl -s https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/health | jq

# Keycloak
curl -s https://auth.stoa.cab-i.com/realms/stoa/.well-known/openid-configuration | jq .issuer
```

### 1.2 Logs Kubernetes (Verbose)

```bash
# Logs MCP Gateway avec traces complètes
kubectl logs -n stoa-system deployment/mcp-gateway -f --tail=100

# Logs Control Plane API
kubectl logs -n stoa-system deployment/control-plane-api -f --tail=100

# Logs Control Plane UI (nginx)
kubectl logs -n stoa-system deployment/control-plane-ui --tail=50

# Logs Developer Portal
kubectl logs -n stoa-system deployment/devportal --tail=50
```

### 1.3 Vérification Base de Données

```bash
# Connexion à la DB
kubectl exec -it -n stoa-system control-plane-db-0 -- psql -U postgres -d stoa

# Vérifier les tables
\dt

# Vérifier les migrations Alembic
SELECT * FROM alembic_version;

# Sortir
\q
```

---

## Phase 2: Création Utilisateurs de Test (Ready Player One Style)

### 2.1 Utilisateurs à créer dans Keycloak

Créer les utilisateurs suivants dans Keycloak (realm `stoa`), liés au tenant `demo`:

| Username | Email | Prénom | Nom | Rôle | Description |
|----------|-------|--------|-----|------|-------------|
| parzival | parzival@oasis.test | Wade | Watts | cpi-admin | Admin plateforme (The One) |
| art3mis | art3mis@oasis.test | Samantha | Cook | tenant-admin | Admin tenant demo |
| aech | aech@oasis.test | Helen | Harris | devops | DevOps/CI-CD |
| shoto | shoto@oasis.test | Toshiro | Yoshiaki | viewer | Lecture seule |
| daito | daito@oasis.test | Akihide | Karatsu | viewer | Lecture seule |
| irok | irok@sixers.test | Nolan | Sorrento | viewer | Test accès limité (Sixer) |

**Attributs communs:**
- `tenant_id`: demo
- `organization`: OASIS
- `test-user`: true
- **Password**: `Gunter2045!`

### 2.2 Script création Keycloak

```bash
# Variables
KC_URL="https://auth.stoa.cab-i.com"
KC_REALM="stoa"
KC_ADMIN_USER="admin"
KC_ADMIN_PASS="<admin_password>"

# Obtenir token admin
ADMIN_TOKEN=$(curl -s -X POST "$KC_URL/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=$KC_ADMIN_USER" \
  -d "password=$KC_ADMIN_PASS" | jq -r '.access_token')

echo "Admin token obtenu: ${ADMIN_TOKEN:0:20}..."

# Fonction de création utilisateur
create_user() {
  local username=$1
  local email=$2
  local firstname=$3
  local lastname=$4
  local role=$5
  local org=${6:-OASIS}
  
  echo "Creating user: $username ($role)..."
  
  # Créer l'utilisateur
  curl -s -X POST "$KC_URL/admin/realms/$KC_REALM/users" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"username\": \"$username\",
      \"email\": \"$email\",
      \"firstName\": \"$firstname\",
      \"lastName\": \"$lastname\",
      \"enabled\": true,
      \"emailVerified\": true,
      \"attributes\": {
        \"tenant_id\": [\"demo\"],
        \"organization\": [\"$org\"],
        \"test-user\": [\"true\"]
      },
      \"credentials\": [{\"type\": \"password\", \"value\": \"Gunter2045!\", \"temporary\": false}]
    }"
  
  # Récupérer l'ID de l'utilisateur
  USER_ID=$(curl -s "$KC_URL/admin/realms/$KC_REALM/users?username=$username" \
    -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[0].id')
  
  if [ "$USER_ID" != "null" ] && [ -n "$USER_ID" ]; then
    # Assigner le rôle
    curl -s -X POST "$KC_URL/admin/realms/$KC_REALM/users/$USER_ID/role-mappings/realm" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d "[{\"name\": \"$role\"}]"
    echo "  ✅ User $username created with role $role"
  else
    echo "  ❌ Failed to create user $username"
  fi
}

# Créer tous les utilisateurs
create_user "parzival" "parzival@oasis.test" "Wade" "Watts" "cpi-admin"
create_user "art3mis" "art3mis@oasis.test" "Samantha" "Cook" "tenant-admin"
create_user "aech" "aech@oasis.test" "Helen" "Harris" "devops"
create_user "shoto" "shoto@oasis.test" "Toshiro" "Yoshiaki" "viewer"
create_user "daito" "daito@oasis.test" "Akihide" "Karatsu" "viewer"
create_user "irok" "irok@sixers.test" "Nolan" "Sorrento" "viewer" "IOI"

echo ""
echo "✅ All test users created!"
```

---

## Phase 3: Authentification & Tokens

### 3.1 Obtention des Tokens

```bash
# Variables
export KC_URL="https://auth.stoa.cab-i.com"
export KC_REALM="stoa"
export KC_CLIENT="control-plane-api"

# Login avec parzival (cpi-admin)
export TOKEN=$(curl -s -X POST "$KC_URL/realms/$KC_REALM/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=$KC_CLIENT" \
  -d "username=parzival" \
  -d "password=Gunter2045!" | jq -r '.access_token')

echo "parzival token: ${TOKEN:0:20}..."

# Login avec art3mis (tenant-admin)
export TOKEN_TENANT=$(curl -s -X POST "$KC_URL/realms/$KC_REALM/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=$KC_CLIENT" \
  -d "username=art3mis" \
  -d "password=Gunter2045!" | jq -r '.access_token')

echo "art3mis token: ${TOKEN_TENANT:0:20}..."

# Login avec aech (devops)
export TOKEN_DEVOPS=$(curl -s -X POST "$KC_URL/realms/$KC_REALM/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=$KC_CLIENT" \
  -d "username=aech" \
  -d "password=Gunter2045!" | jq -r '.access_token')

echo "aech token: ${TOKEN_DEVOPS:0:20}..."

# Login avec shoto (viewer)
export TOKEN_VIEWER=$(curl -s -X POST "$KC_URL/realms/$KC_REALM/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=$KC_CLIENT" \
  -d "username=shoto" \
  -d "password=Gunter2045!" | jq -r '.access_token')

echo "shoto token: ${TOKEN_VIEWER:0:20}..."

# Login avec irok (viewer - Sixer)
export TOKEN_IROK=$(curl -s -X POST "$KC_URL/realms/$KC_REALM/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=$KC_CLIENT" \
  -d "username=irok" \
  -d "password=Gunter2045!" | jq -r '.access_token')

echo "irok token: ${TOKEN_IROK:0:20}..."
```

### 3.2 Vérification des Rôles

```bash
# Décoder le token parzival (devrait avoir cpi-admin)
echo "=== parzival roles ==="
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq '.realm_access.roles'

# Vérifier le tenant_id
echo "=== parzival tenant_id ==="
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq '.tenant_id'

# Vérifier art3mis
echo "=== art3mis roles ==="
echo $TOKEN_TENANT | cut -d. -f2 | base64 -d 2>/dev/null | jq '.realm_access.roles'

# Vérifier shoto (viewer)
echo "=== shoto roles ==="
echo $TOKEN_VIEWER | cut -d. -f2 | base64 -d 2>/dev/null | jq '.realm_access.roles'
```

**Rôles attendus:**

| Utilisateur | Rôle | Accès |
|-------------|------|-------|
| parzival | cpi-admin | Accès total |
| art3mis | tenant-admin | Admin tenant demo uniquement |
| aech | devops | Déploiements |
| shoto/daito | viewer | Lecture seule |
| irok | viewer | Accès limité (Sixer) |

---

## Phase 4: Tests MCP Gateway

### 4.1 Endpoints MCP REST

```bash
# Server Info
curl -s https://mcp.stoa.cab-i.com/mcp/v1/ \
  -H "Authorization: Bearer $TOKEN" | jq

# Liste des Tools
curl -s "https://mcp.stoa.cab-i.com/mcp/v1/tools?limit=50" \
  -H "Authorization: Bearer $TOKEN" | jq

# Catégories de Tools
curl -s https://mcp.stoa.cab-i.com/mcp/v1/tools/categories \
  -H "Authorization: Bearer $TOKEN" | jq

# Tags disponibles
curl -s https://mcp.stoa.cab-i.com/mcp/v1/tools/tags \
  -H "Authorization: Bearer $TOKEN" | jq

# Détail d'un Tool spécifique
curl -s https://mcp.stoa.cab-i.com/mcp/v1/tools/stoa_platform_info \
  -H "Authorization: Bearer $TOKEN" | jq

# Invocation d'un Tool
curl -s -X POST https://mcp.stoa.cab-i.com/mcp/v1/tools/stoa_health_check/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "stoa_health_check", "arguments": {}}' | jq
```

### 4.2 Test SSE Transport (Claude Desktop)

```bash
# Test connexion SSE (Ctrl+C pour arrêter)
curl -N -s https://mcp.stoa.cab-i.com/mcp/sse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream"
```

### 4.3 Logs MCP avec Traces

```bash
# Activer le mode debug dans les logs
kubectl logs -n stoa-system deployment/mcp-gateway -f 2>&1 | grep -E "(ERROR|WARNING|tool|invoke|policy)"
```

---

## Phase 5: Tests Control Plane API

### 5.1 Endpoints CRUD

```bash
# Liste des Tenants
curl -s https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/tenants \
  -H "Authorization: Bearer $TOKEN" | jq

# Liste des APIs d'un Tenant (remplacer {tenantId})
curl -s "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/tenants/demo/apis" \
  -H "Authorization: Bearer $TOKEN" | jq

# MCP Subscriptions
curl -s https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/mcp/subscriptions \
  -H "Authorization: Bearer $TOKEN" | jq

# MCP Servers
curl -s https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/mcp/servers \
  -H "Authorization: Bearer $TOKEN" | jq

# Pipeline Traces
curl -s https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/traces \
  -H "Authorization: Bearer $TOKEN" | jq

# Error Snapshots
curl -s https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/mcp/errors \
  -H "Authorization: Bearer $TOKEN" | jq

# Usage Stats
curl -s https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/usage/me \
  -H "Authorization: Bearer $TOKEN" | jq
```

### 5.2 Logs API avec Traces

```bash
kubectl logs -n stoa-system deployment/control-plane-api -f 2>&1 | grep -E "(ERROR|WARNING|POST|PUT|DELETE)"
```

---

## Phase 6: Tests Error Snapshot

### 6.1 Génération d'erreurs pour test

```bash
echo "=== Test 1: Tool inexistant ==="
curl -s -X POST https://mcp.stoa.cab-i.com/mcp/v1/tools/inexistant_tool_xyz/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "inexistant_tool_xyz", "arguments": {}}' | jq

echo ""
echo "=== Test 2: Arguments invalides ==="
curl -s -X POST https://mcp.stoa.cab-i.com/mcp/v1/tools/stoa_health_check/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "stoa_health_check", "arguments": {"invalid_param": "should_fail"}}' | jq

echo ""
echo "=== Test 3: Token invalide ==="
curl -s -X POST https://mcp.stoa.cab-i.com/mcp/v1/tools/stoa_health_check/invoke \
  -H "Authorization: Bearer invalid_token_12345" \
  -H "Content-Type: application/json" \
  -d '{"name": "stoa_health_check", "arguments": {}}' | jq

echo ""
echo "=== Test 4: Payload malformé ==="
curl -s -X POST https://mcp.stoa.cab-i.com/mcp/v1/tools/stoa_health_check/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d 'not_valid_json{{{' 2>&1 | head -20
```

### 6.2 Vérification capture Error Snapshots

```bash
# Attendre 2 secondes pour la propagation
sleep 2

# Lister les derniers Error Snapshots
echo "=== Error Snapshots capturés ==="
curl -s "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/mcp/errors?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq

# Détail du dernier Error Snapshot (si ID connu)
# curl -s "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/mcp/errors/{error_id}" \
#   -H "Authorization: Bearer $TOKEN" | jq
```

### 6.3 Vérification dans les logs

```bash
# Logs MCP Gateway - erreurs
kubectl logs -n stoa-system deployment/mcp-gateway --tail=50 2>&1 | grep -E "(ERROR|error_snapshot|capture)"

# Logs Control Plane API - stockage
kubectl logs -n stoa-system deployment/control-plane-api --tail=50 2>&1 | grep -E "(error|snapshot)"
```

---

## Phase 7: Tests RBAC (Positifs et Négatifs)

### 7.1 Tests Positifs (Accès autorisé)

```bash
echo "=== RBAC Positif: parzival (cpi-admin) peut tout faire ==="

# parzival peut lister les tenants
curl -s https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/tenants \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | .name' | head -5

# parzival peut invoquer n'importe quel tool
curl -s -X POST https://mcp.stoa.cab-i.com/mcp/v1/tools/stoa_platform_info/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "stoa_platform_info", "arguments": {}}' | jq '.content[0].text' | head -5

echo ""
echo "=== RBAC Positif: shoto (viewer) peut lire ==="

# shoto peut lister les tools
curl -s "https://mcp.stoa.cab-i.com/mcp/v1/tools?limit=5" \
  -H "Authorization: Bearer $TOKEN_VIEWER" | jq '.tools | length'
```

### 7.2 Tests Négatifs (Accès refusé)

```bash
echo "=== RBAC Négatif: shoto (viewer) ne peut PAS créer ==="

# shoto ne devrait PAS pouvoir créer un tenant
RESULT=$(curl -s -w "\n%{http_code}" -X POST https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/tenants \
  -H "Authorization: Bearer $TOKEN_VIEWER" \
  -H "Content-Type: application/json" \
  -d '{"name": "hacked-tenant-by-shoto", "description": "Should fail"}')

HTTP_CODE=$(echo "$RESULT" | tail -1)
BODY=$(echo "$RESULT" | sed '$d')

if [ "$HTTP_CODE" == "403" ] || [ "$HTTP_CODE" == "401" ]; then
  echo "✅ PASS: shoto bloqué (HTTP $HTTP_CODE)"
else
  echo "❌ FAIL: shoto aurait dû être bloqué (HTTP $HTTP_CODE)"
  echo "$BODY" | jq
fi

echo ""
echo "=== RBAC Négatif: shoto (viewer) ne peut PAS supprimer ==="

# shoto ne devrait PAS pouvoir supprimer
RESULT=$(curl -s -w "\n%{http_code}" -X DELETE https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/tenants/demo \
  -H "Authorization: Bearer $TOKEN_VIEWER")

HTTP_CODE=$(echo "$RESULT" | tail -1)

if [ "$HTTP_CODE" == "403" ] || [ "$HTTP_CODE" == "401" ]; then
  echo "✅ PASS: shoto ne peut pas supprimer (HTTP $HTTP_CODE)"
else
  echo "❌ FAIL: shoto aurait dû être bloqué (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== RBAC Négatif: irok (Sixer) accès limité aux tools admin ==="

# irok ne devrait PAS voir certains tools sensibles
RESULT=$(curl -s "https://mcp.stoa.cab-i.com/mcp/v1/tools?category=admin" \
  -H "Authorization: Bearer $TOKEN_IROK" | jq '.tools | length')

if [ "$RESULT" == "0" ] || [ "$RESULT" == "null" ]; then
  echo "✅ PASS: irok ne voit pas les tools admin (count: $RESULT)"
else
  echo "⚠️  WARNING: irok voit $RESULT tools admin - vérifier la policy OPA"
fi

echo ""
echo "=== RBAC Négatif: art3mis ne peut PAS modifier un autre tenant ==="

# art3mis (tenant-admin de demo) ne devrait pas pouvoir modifier un autre tenant
RESULT=$(curl -s -w "\n%{http_code}" -X PUT https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/tenants/other-tenant \
  -H "Authorization: Bearer $TOKEN_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"description": "Hacked by art3mis"}')

HTTP_CODE=$(echo "$RESULT" | tail -1)

if [ "$HTTP_CODE" == "403" ] || [ "$HTTP_CODE" == "404" ]; then
  echo "✅ PASS: art3mis limitée à son tenant (HTTP $HTTP_CODE)"
else
  echo "❌ FAIL: art3mis aurait dû être bloquée (HTTP $HTTP_CODE)"
fi
```

### 7.3 Matrice RBAC de référence

| Action | parzival (cpi-admin) | art3mis (tenant-admin) | aech (devops) | shoto (viewer) |
|--------|---------------------|------------------------|---------------|----------------|
| List tenants | ✅ | ✅ (own only) | ✅ (own only) | ✅ (own only) |
| Create tenant | ✅ | ❌ | ❌ | ❌ |
| Delete tenant | ✅ | ❌ | ❌ | ❌ |
| List tools | ✅ | ✅ | ✅ | ✅ |
| Invoke tool | ✅ | ✅ | ✅ | ✅ (read-only tools) |
| Admin tools | ✅ | ❌ | ❌ | ❌ |
| Deploy API | ✅ | ✅ | ✅ | ❌ |

---

## Phase 8: Tests UI - Console (API Provider)

### 8.1 Pages à Tester

| Page | URL | Test |
|------|-----|------|
| Login | /login | Redirection Keycloak, obtention token |
| Dashboard | / | Affichage stats, quick actions |
| Tenants | /tenants | Liste, création, édition (admin only) |
| APIs | /apis | Liste, création, import OpenAPI |
| AI Tools | /ai-tools | Catalogue tools, filtres, recherche |
| Subscriptions | /ai-tools/subscriptions | Mes abonnements |
| Usage | /ai-tools/usage | Dashboard usage |
| Applications | /applications | Gestion apps |
| Deployments | /deployments | Historique, traces pipeline |
| Monitoring | /monitoring | Transactions API |
| Error Snapshots | /mcp/errors | Erreurs MCP |

### 8.2 Vérification Console Browser

```javascript
// Ouvrir DevTools (F12) > Console
// Vérifier les erreurs JavaScript
console.log("Checking for errors...");

// Vérifier les appels réseau dans Network tab
// Filtrer par XHR/Fetch
```

### 8.3 Logs Nginx (UI)

```bash
kubectl logs -n stoa-system deployment/control-plane-ui -f
```

---

## Phase 9: Tests UI - Developer Portal (API Consumer)

### 9.1 Pages à Tester

| Page | URL | Test |
|------|-----|------|
| Home | / | Dashboard, featured APIs/Tools |
| API Catalog | /apis | Browse, search, filtres |
| API Detail | /apis/{id} | Documentation, endpoints |
| API Test | /apis/{id}/test | Sandbox interactif |
| MCP Servers | /servers | Browse servers avec visibilité rôle |
| Server Detail | /servers/{id} | Tools du serveur |
| Subscriptions | /subscriptions | Gestion abonnements |
| Contracts | /contracts | Universal API Contracts |
| My Apps | /apps | Applications OAuth |
| Service Accounts | /service-accounts | Comptes de service MCP |
| Usage | /usage | Analytics usage |
| Webhooks | /webhooks | Gestion webhooks |

### 9.2 Test Subscription Flow

1. Naviguer vers `/servers`
2. Sélectionner un serveur
3. Cliquer "Subscribe"
4. Vérifier création de clé API
5. Tester rotation de clé
6. Vérifier dans `/subscriptions`

---

## Phase 10: Test Connexion MCP avec Claude.ai (Web)

### 10.1 Prérequis Claude.ai

Pour connecter Claude.ai (web) au MCP Gateway STOA, il faut:
- Un compte Claude Pro/Team avec accès aux MCP integrations
- Une clé API ou token d'authentification STOA
- Configuration du MCP Server dans les settings Claude.ai

### 10.2 Configuration MCP Server dans Claude.ai

1. Aller sur https://claude.ai/settings/integrations
2. Ajouter un nouveau MCP Server:
   - **Name**: STOA Platform
   - **URL**: `https://mcp.stoa.cab-i.com/mcp/sse`
   - **Authentication**: Bearer Token (utiliser le token Keycloak ou API Key)

### 10.3 Test dans Claude.ai

1. Ouvrir une nouvelle conversation sur claude.ai
2. Vérifier que les tools STOA apparaissent dans les options
3. Tester: *"Use the stoa_platform_info tool to show me platform details"*
4. Vérifier l'invocation dans les logs MCP Gateway

### 10.4 Logs Pendant Test Claude.ai

```bash
# Terminal 1: MCP Gateway logs (filtrer health checks)
kubectl logs -n stoa-system deployment/mcp-gateway -f 2>&1 | grep -v health

# Terminal 2: Control Plane API logs
kubectl logs -n stoa-system deployment/control-plane-api -f 2>&1 | grep -v health

# Terminal 3: Voir les connexions SSE
kubectl logs -n stoa-system deployment/mcp-gateway -f 2>&1 | grep -E "(SSE|session|initialize)"
```

### 10.5 Troubleshooting Claude.ai Connection

```bash
# Test manuel SSE depuis terminal
curl -N -s "https://mcp.stoa.cab-i.com/mcp/sse" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream"

# Vérifier CORS headers
curl -I "https://mcp.stoa.cab-i.com/mcp/v1/" \
  -H "Origin: https://claude.ai"
```

---

## Phase 11: Smoke Test E2E Complet

### 11.1 Scénario End-to-End

Ce test valide le flow complet de la plateforme.

```bash
echo "=========================================="
echo "  STOA E2E Smoke Test - Ready Player One"
echo "=========================================="

# Step 1: parzival vérifie la plateforme
echo ""
echo "Step 1: parzival (admin) vérifie la plateforme..."
PLATFORM_INFO=$(curl -s -X POST https://mcp.stoa.cab-i.com/mcp/v1/tools/stoa_platform_info/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "stoa_platform_info", "arguments": {}}')

if echo "$PLATFORM_INFO" | jq -e '.content' > /dev/null 2>&1; then
  echo "  ✅ Platform info retrieved"
else
  echo "  ❌ Failed to get platform info"
  echo "$PLATFORM_INFO" | jq
fi

# Step 2: art3mis liste les tools disponibles
echo ""
echo "Step 2: art3mis (tenant-admin) liste les tools..."
TOOLS_COUNT=$(curl -s "https://mcp.stoa.cab-i.com/mcp/v1/tools?limit=100" \
  -H "Authorization: Bearer $TOKEN_TENANT" | jq '.tools | length')

if [ "$TOOLS_COUNT" -gt 0 ]; then
  echo "  ✅ art3mis voit $TOOLS_COUNT tools"
else
  echo "  ❌ art3mis ne voit aucun tool"
fi

# Step 3: aech crée une subscription (si endpoint existe)
echo ""
echo "Step 3: aech (devops) vérifie les subscriptions..."
SUBS=$(curl -s "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/mcp/subscriptions" \
  -H "Authorization: Bearer $TOKEN_DEVOPS" | jq 'if type == "array" then length else 0 end')

echo "  ✅ aech voit $SUBS subscriptions"

# Step 4: shoto invoque un tool (lecture seule)
echo ""
echo "Step 4: shoto (viewer) invoque stoa_health_check..."
HEALTH=$(curl -s -X POST https://mcp.stoa.cab-i.com/mcp/v1/tools/stoa_health_check/invoke \
  -H "Authorization: Bearer $TOKEN_VIEWER" \
  -H "Content-Type: application/json" \
  -d '{"name": "stoa_health_check", "arguments": {}}')

if echo "$HEALTH" | jq -e '.content' > /dev/null 2>&1; then
  echo "  ✅ shoto peut invoquer les tools de lecture"
else
  echo "  ❌ shoto ne peut pas invoquer le health check"
fi

# Step 5: Vérifier metering/traces
echo ""
echo "Step 5: Vérification des traces..."
TRACES=$(curl -s "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/traces?limit=5" \
  -H "Authorization: Bearer $TOKEN" | jq 'if type == "array" then length else 0 end')

echo "  ✅ $TRACES traces récentes trouvées"

# Step 6: Vérifier Error Snapshots (des tests précédents)
echo ""
echo "Step 6: Vérification Error Snapshots..."
ERRORS=$(curl -s "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/mcp/errors?limit=5" \
  -H "Authorization: Bearer $TOKEN" | jq 'if type == "array" then length else 0 end')

echo "  ✅ $ERRORS error snapshots capturés"

# Step 7: Usage stats
echo ""
echo "Step 7: Vérification usage stats..."
USAGE=$(curl -s "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/usage/me" \
  -H "Authorization: Bearer $TOKEN")

if echo "$USAGE" | jq -e '.' > /dev/null 2>&1; then
  echo "  ✅ Usage stats disponibles"
else
  echo "  ⚠️  Usage stats non disponibles"
fi

echo ""
echo "=========================================="
echo "  E2E Smoke Test Complete!"
echo "=========================================="
```

### 11.2 Vérification Kafka/Metering

```bash
# Liste des topics
kubectl exec -it -n stoa-system redpanda-0 -- rpk topic list

# Consumer sur le topic metering (derniers 10 messages)
kubectl exec -it -n stoa-system redpanda-0 -- rpk topic consume stoa.metering.events --num 10
```

---

## Phase 12: Cleanup (Optionnel)

### 12.1 Suppression des utilisateurs de test

> ⚠️ **ATTENTION** : Ne pas exécuter en production réelle avec des données importantes !

```bash
echo "=== Cleanup Test Users ==="
echo "⚠️  This will delete all test users. Continue? (y/N)"
read -r CONFIRM

if [ "$CONFIRM" != "y" ]; then
  echo "Cleanup cancelled."
  exit 0
fi

# Obtenir token admin
ADMIN_TOKEN=$(curl -s -X POST "$KC_URL/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=$KC_ADMIN_USER" \
  -d "password=$KC_ADMIN_PASS" | jq -r '.access_token')

# Supprimer chaque utilisateur de test
for user in parzival art3mis aech shoto daito irok; do
  USER_ID=$(curl -s "$KC_URL/admin/realms/$KC_REALM/users?username=$user" \
    -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[0].id')
  
  if [ "$USER_ID" != "null" ] && [ -n "$USER_ID" ]; then
    curl -s -X DELETE "$KC_URL/admin/realms/$KC_REALM/users/$USER_ID" \
      -H "Authorization: Bearer $ADMIN_TOKEN"
    echo "  🗑️  Deleted user: $user"
  else
    echo "  ⚠️  User not found: $user"
  fi
done

echo ""
echo "✅ Cleanup complete!"
```

### 12.2 Nettoyage des données de test

```bash
# Supprimer les Error Snapshots de test (si API le permet)
# curl -X DELETE "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/v1/mcp/errors?test=true" \
#   -H "Authorization: Bearer $TOKEN"

# Nettoyer les traces de test
# (Généralement géré par retention policy automatique)
```

---

## Checklist de Validation Finale

### Infrastructure
- [ ] Tous les pods Running
- [ ] Health checks OK pour tous les services
- [ ] Ingress routes fonctionnels
- [ ] Certificats SSL valides

### Authentification
- [ ] Login Keycloak fonctionne
- [ ] Token JWT valide avec bons rôles
- [ ] Refresh token fonctionne
- [ ] Logout fonctionne

### MCP Gateway
- [ ] `/mcp/v1/` retourne server info
- [ ] `/mcp/v1/tools` liste les tools
- [ ] Tool invocation fonctionne
- [ ] OPA policy enforce les permissions
- [ ] SSE transport fonctionne
- [ ] Metering events émis vers Kafka

### Control Plane API
- [ ] CRUD Tenants fonctionne
- [ ] CRUD APIs fonctionne
- [ ] MCP subscriptions fonctionne
- [ ] Pipeline traces stockées
- [ ] Error snapshots capturées

### Console UI
- [ ] Login/Logout fonctionne
- [ ] Dashboard affiche stats
- [ ] Tool catalog charge
- [ ] Filtres/recherche fonctionnent
- [ ] Deployments timeline affiche
- [ ] Monitoring API fonctionne

### Developer Portal
- [ ] API Catalog browse fonctionne
- [ ] API Test sandbox fonctionne
- [ ] MCP Servers visible (role-based)
- [ ] Subscription flow complet
- [ ] Key rotation fonctionne
- [ ] Usage stats affichent

### Claude.ai Web Integration
- [ ] MCP Server configuré dans claude.ai/settings
- [ ] SSE connection établie
- [ ] Tools STOA découverts par Claude
- [ ] Tool invocation fonctionne (stoa_platform_info)
- [ ] Réponses retournées correctement
- [ ] Logs MCP Gateway montrent les requêtes

### Tests RBAC (Ready Player One)
- [ ] parzival (cpi-admin): accès total vérifié
- [ ] art3mis (tenant-admin): CRUD tenant demo uniquement
- [ ] aech (devops): déploiements OK, pas de delete
- [ ] shoto (viewer): lecture seule, pas de modifications
- [ ] irok (viewer): accès limité confirmé

### Error Snapshots
- [ ] Erreurs générées capturées
- [ ] Détails visibles dans Console UI
- [ ] PII masqué correctement

### E2E Smoke Test
- [ ] Flow complet validé
- [ ] Metering events générés
- [ ] Traces visibles

---

## Commandes Debug Utiles

```bash
# Voir tous les logs en temps réel
kubectl logs -n stoa-system -l app=mcp-gateway -f

# Port-forward pour debug local
kubectl port-forward -n stoa-system svc/mcp-gateway 8080:80

# Describe pod pour voir les events
kubectl describe pod -n stoa-system -l app=mcp-gateway

# Voir les configmaps
kubectl get configmap -n stoa-system

# Voir les secrets (sans les valeurs)
kubectl get secrets -n stoa-system

# Exec dans un pod
kubectl exec -it -n stoa-system deployment/mcp-gateway -- sh

# Vérifier les ressources
kubectl top pods -n stoa-system
```

---

## Problèmes Connus à Vérifier

| Problème | Cause | Solution |
|----------|-------|----------|
| 404 sur /tools | Routes incorrectes | Utiliser `/mcp/v1/tools` |
| Token expiration | JWT expire | Refresh token ou re-login |
| CORS errors | Headers manquants | Vérifier config nginx/gateway |
| Rate Limiting | Slowapi limite | Attendre ou augmenter limit |
| SSE disconnect | Timeout | Vérifier keep-alive settings |

---

## Fichiers de Configuration Clés

| Fichier | Description |
|---------|-------------|
| `control-plane-api/src/main.py` | Entry point API |
| `mcp-gateway/src/main.py` | Entry point MCP |
| `mcp-gateway/src/handlers/mcp_sse.py` | SSE transport Claude |
| `mcp-gateway/src/policy/opa_client.py` | OPA policies |
| `control-plane-ui/src/config.ts` | UI configuration |
| `portal/src/config.ts` | Portal configuration |

---

## Résultats d'Exécution (16 janvier 2026)

### Statut Global : 10/11 Phases PASS (91%)

| Phase | Statut | Score |
|-------|--------|-------|
| 1. Infrastructure | ✅ PASS | 100% |
| 2. Utilisateurs Test | ✅ PASS | 100% |
| 3. Authentification | ✅ PASS | 100% |
| 4. MCP Gateway | ✅ PASS | 100% |
| 5. Control Plane API | ✅ PASS | 100% |
| 6. Error Snapshots | ✅ PASS | 100% |
| 7. RBAC | ✅ PASS | 100% |
| 8-9. UI | ✅ PASS | 100% |
| 10. Claude.ai | ⚠️ WARNING | 80% |
| 11. E2E Smoke Test | ✅ PASS | 100% |

### Bugs Identifiés et Corrigés

| Bug | Fichier | Statut |
|-----|---------|--------|
| `'Tool' object has no attribute 'inputSchema'` | mcp-gateway/src/handlers/mcp_sse.py:91 | ✅ FIXED |
| `Logger._log() got an unexpected keyword argument 'path'` | control-plane-api/src/routers/mcp_proxy.py:91-107 | ✅ FIXED |

### Métriques Clés

- **Tools MCP disponibles** : 23
- **MCP Servers configurés** : 9
- **Error Snapshots capturés** : 50
- **Pipeline Traces** : 5 récentes
- **Usage Today** : 127 calls

### Rapport Détaillé

Voir : [2026-01-16-debug-session.md](../test-results/2026-01-16-debug-session.md)

---

*"The OASIS was the only world that made sense to me." - Ready Player One*

**Version** : 2.1 | **Last Updated** : 16 janvier 2026 | **Executed** : ✅
