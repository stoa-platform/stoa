# Plan: MCP Server Subscriptions avec Workflow d'Approbation

## Contexte

### Problème Actuel
1. **Stockage en mémoire** : Les subscriptions sont stockées dans un `dict` Python → perdues au redémarrage
2. **Pas de persistence** : Les subscriptions doivent être stockées dans la base de données PostgreSQL (partagée)
3. **Workflow d'approbation inexistant** : Les tools marqués `requires_approval=true` passent en `PENDING_APPROVAL` mais aucun admin ne peut approuver
4. **Validation API Key incomplète** : Seul le préfixe est vérifié, pas le hash SHA-256
5. **Contrat OpenAPI** : Doit être mis à jour dans WebMethods à chaque modification

### Architecture Cible

```
┌─────────────────────────────────────────────────────────────────┐
│                         PORTAL (React)                          │
├─────────────────────────────────────────────────────────────────┤
│  Auth: Keycloak JWT Token (stoa-portal client)                  │
│  Usage: Voir/gérer ses subscriptions, demander accès            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Bearer Token
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│           WEBMETHODS API GATEWAY (apis.stoa.cab-i.com)          │
├─────────────────────────────────────────────────────────────────┤
│  Route: /gateway/Control-Plane-API/2.0/*                        │
│  Auth: OIDC Token Forwarding                                    │
│  Contrat: OpenAPI auto-généré par FastAPI                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONTROL-PLANE API (Python)                   │
├─────────────────────────────────────────────────────────────────┤
│  Endpoints Subscription Management:                              │
│  - GET  /v1/mcp/subscriptions             (mes subscriptions)   │
│  - POST /v1/mcp/subscriptions             (créer subscription)  │
│  - GET  /v1/mcp/subscriptions/{id}        (détail)              │
│  - DELETE /v1/mcp/subscriptions/{id}      (révoquer)            │
│  - POST /v1/mcp/subscriptions/{id}/rotate-key                   │
│                                                                  │
│  Endpoints Admin Approval:                                       │
│  - GET  /v1/admin/mcp/subscriptions/pending                     │
│  - POST /v1/admin/mcp/subscriptions/{id}/approve                │
│  - POST /v1/admin/mcp/subscriptions/{id}/reject                 │
│                                                                  │
│  Storage: PostgreSQL (shared database "stoa")                   │
│  Secrets: HashiCorp Vault (API Keys)                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      MCP GATEWAY (Python)                        │
├─────────────────────────────────────────────────────────────────┤
│  Auth (ordre de priorité):                                       │
│  1. Bearer Token OAuth2/JWT (DEFAUT) - Portal/Claude.ai         │
│  2. Basic Auth Client Credentials - Service Accounts            │
│  3. API Key (stoa_sk_*) - M2M legacy                            │
│                                                                  │
│  Usage: Exécution des tools MCP                                 │
│  Validation API Key: Hash SHA-256 contre PostgreSQL             │
│  Lecture subscriptions: Depuis PostgreSQL (shared DB)           │
└─────────────────────────────────────────────────────────────────┘
```

### Points Importants

1. **Portal → Control-Plane API via WebMethods Gateway**
   - URL: `https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0`
   - Le contrat OpenAPI doit être mis à jour à chaque modification du Control-Plane API

2. **MCP Gateway - Auth par défaut = OAuth2 JWT**
   - Le token Keycloak est le mode principal (pour Portal et Claude.ai)
   - L'API Key est une option secondaire pour M2M
   - Ordre: Bearer Token → Basic Auth → API Key

3. **Base de données partagée**
   - PostgreSQL `stoa` utilisée par Control-Plane API ET MCP Gateway
   - Les subscriptions sont stockées dans cette DB (pas en mémoire)
   - MCP Gateway lit les subscriptions depuis la même DB

4. **Secrets dans Vault**
   - Les API Keys sont stockées chiffrées dans Vault
   - Path: `secret/data/subscriptions/{subscription_id}`
   - Hash SHA-256 stocké en DB pour validation rapide

---

## Phase 1: Persistence des Subscriptions (Control-Plane API)

### 1.1 Modèle SQLAlchemy pour les Subscriptions

**Fichier**: `control-plane-api/src/models/mcp_subscription.py`

```python
class MCPServerSubscription(Base):
    __tablename__ = "mcp_server_subscriptions"

    id = Column(String, primary_key=True)  # sub-xxxxxxxxxxxx
    server_id = Column(String, nullable=False)  # stoa-platform, crm-apis, etc.
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(String, nullable=False)  # Keycloak sub
    status = Column(Enum("pending", "active", "suspended", "revoked"), default="pending")
    plan = Column(String, default="free")

    # API Key (hash stocké, jamais en clair)
    api_key_prefix = Column(String(16))  # stoa_sk_XXXXXXX
    api_key_hash = Column(String(64))    # SHA-256 hash

    # Workflow d'approbation
    requires_approval = Column(Boolean, default=False)
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    last_used_at = Column(DateTime, nullable=True)
    last_rotated_at = Column(DateTime, nullable=True)

    # Relations
    tool_access = relationship("MCPToolAccess", back_populates="subscription", cascade="all, delete-orphan")


class MCPToolAccess(Base):
    __tablename__ = "mcp_tool_access"

    id = Column(String, primary_key=True)
    subscription_id = Column(String, ForeignKey("mcp_server_subscriptions.id"), nullable=False)
    tool_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    status = Column(Enum("enabled", "disabled", "pending_approval"), default="enabled")
    granted_at = Column(DateTime, nullable=True)

    subscription = relationship("MCPServerSubscription", back_populates="tool_access")
```

### 1.2 Router pour les Subscriptions MCP

**Fichier**: `control-plane-api/src/routers/mcp_subscriptions.py`

```python
router = APIRouter(prefix="/v1/mcp", tags=["MCP Subscriptions"])

@router.get("/servers")
async def list_mcp_servers(user: User = Depends(get_current_user)):
    """Liste les serveurs MCP disponibles (filtrés par rôles)"""

@router.get("/subscriptions")
async def list_my_subscriptions(user: User = Depends(get_current_user)):
    """Liste mes subscriptions MCP"""

@router.post("/subscriptions")
async def create_subscription(request: SubscriptionCreate, user: User = Depends(get_current_user)):
    """Créer une subscription (retourne API Key une seule fois)"""

@router.get("/subscriptions/{subscription_id}")
async def get_subscription(subscription_id: str, user: User = Depends(get_current_user)):
    """Détail d'une subscription"""

@router.delete("/subscriptions/{subscription_id}")
async def revoke_subscription(subscription_id: str, user: User = Depends(get_current_user)):
    """Révoquer une subscription"""

@router.post("/subscriptions/{subscription_id}/rotate-key")
async def rotate_key(subscription_id: str, user: User = Depends(get_current_user)):
    """Régénérer l'API Key (2FA requis)"""
```

---

## Phase 2: Workflow d'Approbation Admin

### 2.1 Configuration Tenant

**Option activable par tenant** (dans la table `tenant_settings` ou `tenants`):
```python
mcp_subscription_requires_approval: bool = False  # Par défaut: auto-approve
mcp_approval_roles: List[str] = ["cpi-admin", "tenant-admin"]
```

### 2.2 Endpoints Admin

**Fichier**: `control-plane-api/src/routers/mcp_admin.py`

```python
router = APIRouter(prefix="/v1/admin/mcp", tags=["MCP Admin"])

@router.get("/subscriptions/pending")
async def list_pending_subscriptions(user: User = Depends(require_role("cpi-admin"))):
    """Liste les subscriptions en attente d'approbation"""

@router.post("/subscriptions/{subscription_id}/approve")
async def approve_subscription(subscription_id: str, user: User = Depends(require_role("cpi-admin"))):
    """Approuver une subscription (génère l'API Key)"""

@router.post("/subscriptions/{subscription_id}/reject")
async def reject_subscription(subscription_id: str, reason: str, user: User = Depends(require_role("cpi-admin"))):
    """Rejeter une subscription avec raison"""
```

### 2.3 Notifications (via Kafka)

Topics Kafka:
- `mcp.subscription.requested` - Nouvelle demande
- `mcp.subscription.approved` - Demande approuvée
- `mcp.subscription.rejected` - Demande rejetée

---

## Phase 3: Portal - Modification des Appels API

### 3.1 Nouveau Service

**Fichier**: `portal/src/services/mcpSubscriptions.ts`

```typescript
import { apiClient } from './api';  // Passe par WebMethods Gateway

export const mcpSubscriptionsService = {
  // Serveurs disponibles
  listServers: () => apiClient.get('/v1/mcp/servers'),
  getServer: (id: string) => apiClient.get(`/v1/mcp/servers/${id}`),

  // Mes subscriptions
  listSubscriptions: () => apiClient.get('/v1/mcp/subscriptions'),
  getSubscription: (id: string) => apiClient.get(`/v1/mcp/subscriptions/${id}`),
  createSubscription: (data: CreateSubscriptionRequest) =>
    apiClient.post('/v1/mcp/subscriptions', data),
  revokeSubscription: (id: string) =>
    apiClient.delete(`/v1/mcp/subscriptions/${id}`),
  rotateKey: (id: string) =>
    apiClient.post(`/v1/mcp/subscriptions/${id}/rotate-key`),
};
```

### 3.2 Page My Subscriptions (mise à jour)

**Avant** (appelle MCP Gateway directement):
```typescript
const response = await mcpClient.get('/servers/subscriptions');
```

**Après** (appelle Control-Plane API via WebMethods):
```typescript
const response = await mcpSubscriptionsService.listSubscriptions();
```

### 3.3 Mise à jour du contrat OpenAPI

Après modification du Control-Plane API:
1. Récupérer le nouveau OpenAPI: `curl https://api.stoa.cab-i.com/openapi.json`
2. Mettre à jour dans WebMethods API Gateway
3. Republier l'API `Control-Plane-API v2.0`

---

## Phase 4: MCP Gateway - Validation et Lecture DB

### 4.1 Connexion à PostgreSQL (partagée)

**Fichier**: `mcp-gateway/src/database.py`

```python
# Réutilise la même DB que Control-Plane API
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://stoa:stoa@localhost:5432/stoa")

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession)
```

### 4.2 Service de validation API Key

**Fichier**: `mcp-gateway/src/services/api_key.py`

```python
async def validate_api_key(api_key: str) -> Optional[TokenClaims]:
    """Valide l'API Key contre la DB PostgreSQL"""
    if not api_key.startswith("stoa_sk_"):
        return None

    # Calculer le hash
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_prefix = api_key[:16]

    # Vérifier contre la DB
    async with async_session() as session:
        result = await session.execute(
            select(MCPServerSubscription)
            .where(MCPServerSubscription.api_key_prefix == key_prefix)
            .where(MCPServerSubscription.api_key_hash == key_hash)
            .where(MCPServerSubscription.status == "active")
        )
        subscription = result.scalar_one_or_none()

    if not subscription:
        return None

    # Mettre à jour last_used_at (async, best-effort)
    asyncio.create_task(update_last_used(subscription.id))

    return TokenClaims(
        sub=subscription.user_id,
        client_id=f"subscription:{subscription.id}",
        realm_access={"roles": ["mcp-consumer"]},
    )
```

---

## Phase 5: Migration & Déploiement

### 5.1 Migration Alembic

```bash
cd control-plane-api
alembic revision --autogenerate -m "Add MCP subscriptions tables"
alembic upgrade head
```

### 5.2 Variables d'environnement

```yaml
# Control-Plane API
DATABASE_URL: "postgresql+asyncpg://stoa:stoa@control-plane-db:5432/stoa"
VAULT_ADDR: "https://vault.stoa.cab-i.com"
VAULT_MCP_KEYS_PATH: "secret/data/mcp-subscriptions"

# MCP Gateway (même DB)
DATABASE_URL: "postgresql+asyncpg://stoa:stoa@control-plane-db:5432/stoa"
VAULT_ADDR: "https://vault.stoa.cab-i.com"

# Tenant settings
MCP_SUBSCRIPTION_REQUIRES_APPROVAL: "false"  # Activable par tenant
```

### 5.3 Mise à jour WebMethods

1. Exporter le nouveau OpenAPI depuis Control-Plane API
2. Importer dans WebMethods API Gateway
3. Republier `Control-Plane-API v2.0`

---

## Résumé des Tâches

| # | Tâche | Composant | Priorité |
|---|-------|-----------|----------|
| 1 | Créer modèles SQLAlchemy (MCPServerSubscription, MCPToolAccess) | control-plane-api | P0 |
| 2 | Créer migration Alembic | control-plane-api | P0 |
| 3 | Créer router `/v1/mcp/subscriptions` | control-plane-api | P0 |
| 4 | Créer router `/v1/mcp/servers` (liste serveurs) | control-plane-api | P0 |
| 5 | Modifier Portal: nouveau service `mcpSubscriptions.ts` | portal | P0 |
| 6 | Modifier Portal: MySubscriptions.tsx utilise nouveau service | portal | P0 |
| 7 | Mettre à jour contrat OpenAPI dans WebMethods | webmethods | P0 |
| 8 | MCP Gateway: connexion DB partagée | mcp-gateway | P1 |
| 9 | MCP Gateway: validation API Key par hash | mcp-gateway | P1 |
| 10 | Créer router admin `/v1/admin/mcp/subscriptions` | control-plane-api | P1 |
| 11 | Ajouter option `requires_approval` par tenant | control-plane-api | P2 |
| 12 | Notifications Kafka pour workflow | control-plane-api | P2 |
| 13 | Tests E2E du workflow complet | all | P2 |

---

---

## Phase 6 (Optionnel): mTLS + Certificate-Bound Tokens pour M2M

### 6.1 Architecture mTLS

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLIENT M2M (Service Account)                 │
├─────────────────────────────────────────────────────────────────┤
│  1. Certificat client X.509 (mTLS)                              │
│  2. Token OAuth2 lié au certificat (Certificate-Bound)          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ mTLS + Bearer Token
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MCP GATEWAY (Python)                        │
├─────────────────────────────────────────────────────────────────┤
│  Validation:                                                     │
│  1. Vérifier certificat client (CN, validité, CA)               │
│  2. Extraire thumbprint du certificat                           │
│  3. Valider token JWT + vérifier cnf.x5t#S256 == thumbprint     │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Certificate-Bound Access Tokens (RFC 8705)

Le token JWT contient un claim `cnf` (confirmation) avec le thumbprint du certificat:

```json
{
  "sub": "service-account-crm",
  "iss": "https://auth.stoa.cab-i.com/realms/stoa",
  "cnf": {
    "x5t#S256": "sha256-thumbprint-du-certificat-client"
  }
}
```

### 6.3 Configuration Keycloak

1. **Activer mTLS sur le client**:
   - Client Authentication: ON
   - Authentication Flow: X.509 Certificate
   - X509 Certificate User Attribute: CN

2. **Lier le token au certificat**:
   - Token Endpoint Auth: X509_CERTIFICATE
   - Certificate Bound Access Tokens: ON

### 6.4 Implémentation MCP Gateway

**Fichier**: `mcp-gateway/src/middleware/mtls.py`

```python
import hashlib
import base64
from cryptography import x509

async def validate_certificate_bound_token(
    request: Request,
    token_claims: TokenClaims
) -> bool:
    """Valide que le token est lié au certificat client mTLS"""

    # 1. Extraire le certificat client (via header Ingress ou TLS)
    client_cert_pem = request.headers.get("X-Client-Cert")
    if not client_cert_pem:
        # Pas de mTLS, ignorer la validation
        return True

    # 2. Parser le certificat
    cert = x509.load_pem_x509_certificate(client_cert_pem.encode())

    # 3. Calculer le thumbprint SHA-256
    cert_thumbprint = base64.urlsafe_b64encode(
        hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).digest()
    ).decode().rstrip("=")

    # 4. Vérifier contre le claim cnf.x5t#S256 du token
    cnf = token_claims.dict().get("cnf", {})
    expected_thumbprint = cnf.get("x5t#S256")

    if expected_thumbprint and expected_thumbprint != cert_thumbprint:
        logger.warning(
            "Certificate-bound token mismatch",
            expected=expected_thumbprint,
            actual=cert_thumbprint,
        )
        return False

    return True
```

### 6.5 Configuration Ingress pour mTLS

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mcp-gateway-mtls
  annotations:
    nginx.ingress.kubernetes.io/auth-tls-verify-client: "optional"
    nginx.ingress.kubernetes.io/auth-tls-secret: "stoa-system/client-ca-cert"
    nginx.ingress.kubernetes.io/auth-tls-pass-certificate-to-upstream: "true"
spec:
  tls:
    - hosts:
        - mcp.stoa.cab-i.com
      secretName: mcp-gateway-tls
  rules:
    - host: mcp.stoa.cab-i.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: mcp-gateway
                port:
                  number: 80
```

### 6.6 Gestion des Certificats Client

**Vault PKI** pour émettre les certificats clients:

```bash
# Créer un rôle PKI pour les clients M2M
vault write pki/roles/mcp-client \
    allowed_domains="stoa.cab-i.com" \
    allow_subdomains=true \
    max_ttl="8760h" \
    key_type="rsa" \
    key_bits=2048

# Émettre un certificat client
vault write pki/issue/mcp-client \
    common_name="service-account-crm.stoa.cab-i.com" \
    ttl="720h"
```

### 6.7 Modèle de Données (Extension)

```python
class MCPServerSubscription(Base):
    # ... champs existants ...

    # mTLS (optionnel)
    mtls_enabled = Column(Boolean, default=False)
    client_cert_cn = Column(String, nullable=True)  # CN du certificat autorisé
    client_cert_thumbprint = Column(String(64), nullable=True)  # SHA-256 du cert
```

---

## Résumé des Modes d'Authentification MCP Gateway

| Mode | Usage | Sécurité | Priorité |
|------|-------|----------|----------|
| **Bearer Token OAuth2** | Portal, Claude.ai, utilisateurs | Forte (JWT signé) | 1 (défaut) |
| **mTLS + Certificate-Bound Token** | M2M haute sécurité | Très forte | 1bis (si activé) |
| **Basic Auth (Client Credentials)** | Service Accounts | Moyenne | 2 |
| **API Key (stoa_sk_*)** | M2M legacy, scripts | Faible | 3 |

---

## Questions Résolues

1. **Stockage des API Keys** : Hash SHA-256 en DB pour validation rapide + clé chiffrée dans Vault
2. **Auth MCP Gateway par défaut** : OAuth2 JWT (Bearer Token) - API Key est secondaire
3. **Base de données** : PostgreSQL partagée entre Control-Plane API et MCP Gateway
4. **Routing Portal** : Via WebMethods API Gateway (`apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0`)
5. **mTLS pour M2M** : Optionnel, avec Certificate-Bound Tokens (RFC 8705)

## Questions Ouvertes

1. **Granularité de l'approbation** : Par serveur ou par tool?
2. **Révocation cascade** : Si un tenant est désactivé, révoquer toutes ses subscriptions?
3. **Quotas/Rate limiting** : Limiter le nombre de subscriptions par user/tenant?
4. **Migration données existantes** : Comment migrer les subscriptions in-memory actuelles?
5. **CA pour mTLS** : Vault PKI ou CA externe (Let's Encrypt client certs non supportés)?
