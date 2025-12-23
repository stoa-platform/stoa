# Système de Ticketing - Demandes de Production

## 📋 Vue d'ensemble

**Objectif** : Implémenter un workflow de validation manuelle pour les promotions vers PROD avec traçabilité complète.

**Durée estimée** : 1 semaine

**Intégration** : Ajout à la Console APIM existante (pas d'outil externe)

---

## 🎯 Fonctionnalités

| Fonctionnalité | Description |
|----------------|-------------|
| Créer une demande | DevOps soumet une demande de promotion STAGING → PROD |
| Validation RBAC | Seuls les CPI/Admins peuvent approuver |
| Règle anti-self-approval | Le demandeur ne peut pas approuver sa propre demande |
| Workflow automatisé | Approbation → AWX Job → Déploiement PROD |
| Notifications | Email + Slack à chaque étape |
| Historique complet | Audit trail dans Git |

---

## 📁 Structure dans Git

```
apim-gitops/
├── requests/
│   └── prod/
│       ├── 2024/
│       │   ├── 12/
│       │   │   ├── PR-2024-0001.yaml
│       │   │   ├── PR-2024-0002.yaml
│       │   │   └── PR-2024-0003.yaml
│       │   └── ...
│       └── ...
│
├── tenants/
│   └── ...
│
└── apis/
    └── ...
```

---

## 📄 Format du Ticket YAML

```yaml
# requests/prod/2024/12/PR-2024-0003.yaml
apiVersion: apim.cab-i.com/v1
kind: PromotionRequest
metadata:
  id: PR-2024-0003
  createdAt: "2024-12-23T10:30:00Z"
  createdBy: pierre.durand@cab-i.com
  tenant: tenant-finance

spec:
  # Cible de la promotion
  target:
    type: api                      # api | application | policy
    name: payment-api
    version: "2.1.0"
    sourceEnvironment: staging
    targetEnvironment: prod
  
  # Justification
  request:
    justification: "New PCI-DSS compliant payment flow"
    releaseNotes: |
      - Added 3DS2 authentication
      - Fixed timeout issues
      - Performance improvements
    impactAssessment: low          # low | medium | high | critical
    rollbackPlan: "Revert to v2.0.0 via emergency deploy"
    scheduledDate: null            # null = ASAP, ou date ISO
    
  # Validation pré-déploiement
  preChecks:
    stagingTestsPassed: true
    securityScanPassed: true
    performanceTestsPassed: true
    testEvidenceUrl: "https://gitlab.cab-i.com/pipeline/12345"

# Status (géré par le système)
status:
  state: pending                   # pending | approved | rejected | deploying | deployed | failed
  
  # Historique des actions
  history:
    - action: created
      at: "2024-12-23T10:30:00Z"
      by: pierre.durand@cab-i.com
      
    - action: approved
      at: "2024-12-23T14:15:00Z"
      by: jean.dupont@cab-i.com
      comment: "Approved after review"
      
    - action: deployed
      at: "2024-12-23T14:20:00Z"
      by: system
      jobId: "awx-job-5678"
      deploymentId: "deploy-abc123"
      
  # Infos supplémentaires
  approvedBy: jean.dupont@cab-i.com
  approvedAt: "2024-12-23T14:15:00Z"
  deployedAt: "2024-12-23T14:20:00Z"
  
  # En cas de rejet
  rejectedBy: null
  rejectedAt: null
  rejectionReason: null
```

---

## 🔄 Workflow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              WORKFLOW                                            │
│                                                                                  │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│   │  PENDING │───►│ APPROVED │───►│DEPLOYING │───►│ DEPLOYED │                  │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘                  │
│        │                               │                                         │
│        │                               │                                         │
│        ▼                               ▼                                         │
│   ┌──────────┐                   ┌──────────┐                                   │
│   │ REJECTED │                   │  FAILED  │                                   │
│   └──────────┘                   └──────────┘                                   │
│                                                                                  │
│   Transitions:                                                                   │
│   • PENDING → APPROVED : CPI approuve                                           │
│   • PENDING → REJECTED : CPI rejette                                            │
│   • APPROVED → DEPLOYING : AWX job démarre                                      │
│   • DEPLOYING → DEPLOYED : AWX job succès                                       │
│   • DEPLOYING → FAILED : AWX job échec                                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔐 RBAC

| Rôle | Créer demande | Approuver | Rejeter | Voir |
|------|---------------|-----------|---------|------|
| **DevOps** | ✅ Son tenant | ❌ | ❌ | Ses demandes |
| **CPI (Tenant Admin)** | ✅ Son tenant | ✅ Son tenant* | ✅ Son tenant | Son tenant |
| **CPI Admin** | ✅ Tous | ✅ Tous* | ✅ Tous | Tous |
| **Viewer** | ❌ | ❌ | ❌ | Son tenant |

*\* Sauf ses propres demandes (anti-self-approval)*

---

## 📅 Planning Jour par Jour

### Jour 1 : Modèle de Données + API CRUD

| Tâche | Fichiers |
|-------|----------|
| Définir le modèle Pydantic | `src/models/promotion_request.py` |
| Service Git pour les requests | `src/services/promotion_request_service.py` |
| Endpoints CRUD | `src/routers/promotion_requests.py` |
| Tests unitaires | `tests/test_promotion_requests.py` |

**Endpoints à créer :**

```python
GET    /v1/requests/prod                    # Liste (filtres: state, tenant, createdBy)
POST   /v1/requests/prod                    # Créer demande
GET    /v1/requests/prod/{id}               # Détail
GET    /v1/requests/prod/pending            # Demandes en attente pour moi
GET    /v1/requests/prod/my                 # Mes demandes
```

---

### Jour 2 : Workflow Approbation

| Tâche | Fichiers |
|-------|----------|
| Endpoint approve | `src/routers/promotion_requests.py` |
| Endpoint reject | `src/routers/promotion_requests.py` |
| Validation RBAC | `src/auth/permissions.py` |
| Anti-self-approval check | `src/services/promotion_request_service.py` |
| Trigger AWX sur approval | `src/services/awx_service.py` |

**Endpoints à créer :**

```python
POST   /v1/requests/prod/{id}/approve       # Approuver (+ comment optionnel)
POST   /v1/requests/prod/{id}/reject        # Rejeter (+ reason obligatoire)
```

**Logique approve :**

```python
async def approve_request(request_id: str, approver: User, comment: str = None):
    request = await get_request(request_id)
    
    # Validations
    if request.status.state != "pending":
        raise HTTPException(400, "Request not pending")
    
    if request.metadata.createdBy == approver.email:
        raise HTTPException(403, "Cannot approve your own request")
    
    if not has_permission(approver, request.metadata.tenant, "approve"):
        raise HTTPException(403, "Not authorized")
    
    # Update status
    request.status.state = "approved"
    request.status.approvedBy = approver.email
    request.status.approvedAt = datetime.utcnow()
    request.status.history.append({
        "action": "approved",
        "at": datetime.utcnow().isoformat(),
        "by": approver.email,
        "comment": comment
    })
    
    # Commit to Git
    await git_service.commit_request(request)
    
    # Trigger AWX
    job_id = await awx_service.deploy_to_prod(request)
    
    # Update status to deploying
    request.status.state = "deploying"
    await git_service.commit_request(request)
    
    # Notify
    await notify_deployment_started(request, job_id)
    
    return request
```

---

### Jour 3 : Intégration AWX + Callbacks

| Tâche | Fichiers |
|-------|----------|
| Créer job template AWX pour PROD | AWX config |
| Callback webhook AWX → API | `src/webhooks/awx_callback.py` |
| Update status sur succès/échec | `src/services/promotion_request_service.py` |
| Retry logic si échec | `src/services/promotion_request_service.py` |

**Webhook callback :**

```python
@router.post("/webhooks/awx/job-complete")
async def awx_job_complete(payload: AWXJobCallback):
    request_id = payload.extra_vars.get("request_id")
    request = await get_request(request_id)
    
    if payload.status == "successful":
        request.status.state = "deployed"
        request.status.deployedAt = datetime.utcnow()
        request.status.history.append({
            "action": "deployed",
            "at": datetime.utcnow().isoformat(),
            "by": "system",
            "jobId": payload.job_id
        })
        await notify_deployment_success(request)
    else:
        request.status.state = "failed"
        request.status.history.append({
            "action": "failed",
            "at": datetime.utcnow().isoformat(),
            "by": "system",
            "jobId": payload.job_id,
            "error": payload.result_stdout
        })
        await notify_deployment_failed(request)
    
    await git_service.commit_request(request)
```

---

### Jour 4 : UI - Liste et Filtres

| Tâche | Fichiers |
|-------|----------|
| Page ProductionRequests | `src/pages/ProductionRequests.tsx` |
| Composant RequestCard | `src/components/requests/RequestCard.tsx` |
| Filtres (state, tenant) | `src/components/requests/RequestFilters.tsx` |
| Badge status avec couleurs | `src/components/requests/StatusBadge.tsx` |
| Hook useRequests | `src/hooks/useRequests.ts` |

**Structure UI :**

```
src/
├── pages/
│   └── ProductionRequests.tsx
│
└── components/
    └── requests/
        ├── RequestCard.tsx
        ├── RequestFilters.tsx
        ├── StatusBadge.tsx
        └── RequestTimeline.tsx
```

---

### Jour 5 : UI - Formulaire de Demande

| Tâche | Fichiers |
|-------|----------|
| Page NewRequest | `src/pages/NewProductionRequest.tsx` |
| Formulaire avec validation | `src/pages/NewProductionRequest.tsx` |
| Sélecteur API/Version | `src/components/requests/ApiVersionSelector.tsx` |
| Champs pre-checks | `src/components/requests/PreChecksForm.tsx` |
| Submit + redirection | `src/pages/NewProductionRequest.tsx` |

**Champs du formulaire :**

```typescript
interface NewRequestForm {
  // Target
  targetType: 'api' | 'application' | 'policy';
  targetName: string;
  targetVersion: string;
  
  // Request details
  justification: string;        // Required, min 20 chars
  releaseNotes: string;         // Required, markdown
  impactAssessment: 'low' | 'medium' | 'high' | 'critical';
  rollbackPlan: string;         // Required
  scheduledDate?: string;       // Optional, ISO date
  
  // Pre-checks
  stagingTestsPassed: boolean;  // Must be true
  securityScanPassed: boolean;  // Must be true
  performanceTestsPassed: boolean;
  testEvidenceUrl: string;      // Required, URL
}
```

---

### Jour 6 : UI - Détail et Actions

| Tâche | Fichiers |
|-------|----------|
| Page RequestDetail | `src/pages/RequestDetail.tsx` |
| Timeline des actions | `src/components/requests/RequestTimeline.tsx` |
| Boutons Approve/Reject | `src/components/requests/ApprovalActions.tsx` |
| Modal de confirmation | `src/components/requests/ConfirmModal.tsx` |
| Modal de rejet (reason) | `src/components/requests/RejectModal.tsx` |

**Page détail :**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ← Back                                           PR-2024-0003                  │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  payment-api v2.1.0                                      🟡 PENDING     │    │
│  │  tenant-finance                                                         │    │
│  │  Requested by: Pierre Durand • 23 Dec 2024 10:30                        │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Justification                                                          │    │
│  │  ─────────────                                                          │    │
│  │  New PCI-DSS compliant payment flow                                     │    │
│  │                                                                         │    │
│  │  Release Notes                                                          │    │
│  │  ─────────────                                                          │    │
│  │  • Added 3DS2 authentication                                            │    │
│  │  • Fixed timeout issues                                                 │    │
│  │  • Performance improvements                                             │    │
│  │                                                                         │    │
│  │  Impact: Low          Rollback: Revert to v2.0.0                        │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  Pre-checks                                                                      │
│  ──────────                                                                      │
│  ✅ Staging tests passed                                                        │
│  ✅ Security scan passed                                                        │
│  ✅ Performance tests passed                                                    │
│  📎 Evidence: https://gitlab.../pipeline/12345                                  │
│                                                                                  │
│  Timeline                                                                        │
│  ────────                                                                        │
│  ● Created • 23 Dec 10:30 • Pierre Durand                                       │
│  │                                                                               │
│  ○ Awaiting approval...                                                         │
│                                                                                  │
│                                              [Reject]  [✓ Approve]              │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### Jour 7 : Notifications + Polish

| Tâche | Fichiers |
|-------|----------|
| Notifications Kafka | `src/services/notification_service.py` |
| Email templates | `src/templates/emails/` |
| Slack notifications | `src/services/slack_service.py` |
| Loading states UI | Global |
| Error handling UI | Global |
| Tests E2E | `tests/e2e/` |

**Events Kafka :**

```python
# Topics
TOPIC_PROMOTION_REQUESTS = "promotion-requests"

# Events
"request-created"      # Nouvelle demande
"request-approved"     # Demande approuvée
"request-rejected"     # Demande rejetée
"deployment-started"   # Déploiement lancé
"deployment-succeeded" # Déploiement réussi
"deployment-failed"    # Déploiement échoué
```

**Templates Email :**

```
src/templates/emails/
├── request_created.html       # Pour les approbateurs
├── request_approved.html      # Pour le demandeur
├── request_rejected.html      # Pour le demandeur
├── deployment_started.html    # Pour le demandeur + approbateur
├── deployment_succeeded.html  # Pour tous
└── deployment_failed.html     # Pour tous + ops
```

---

## 🔌 Endpoints API Complets

```python
# src/routers/promotion_requests.py

# Liste et recherche
GET    /v1/requests/prod
       Query: ?state=pending&tenant=tenant-finance&createdBy=user@email
       Response: List[PromotionRequest]

# Mes demandes
GET    /v1/requests/prod/my
       Response: List[PromotionRequest]

# Demandes en attente pour moi (approbateur)
GET    /v1/requests/prod/pending
       Response: List[PromotionRequest]

# Créer une demande
POST   /v1/requests/prod
       Body: CreatePromotionRequest
       Response: PromotionRequest

# Détail d'une demande
GET    /v1/requests/prod/{id}
       Response: PromotionRequest

# Approuver
POST   /v1/requests/prod/{id}/approve
       Body: { comment?: string }
       Response: PromotionRequest

# Rejeter
POST   /v1/requests/prod/{id}/reject
       Body: { reason: string }  # Required
       Response: PromotionRequest

# Stats (pour dashboard)
GET    /v1/requests/prod/stats
       Response: {
         pending: number,
         approvedToday: number,
         rejectedToday: number,
         deployedThisWeek: number
       }
```

---

## 📦 Modèles Pydantic

```python
# src/models/promotion_request.py
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime

class TargetSpec(BaseModel):
    type: Literal["api", "application", "policy"]
    name: str
    version: str
    sourceEnvironment: str = "staging"
    targetEnvironment: str = "prod"

class RequestDetails(BaseModel):
    justification: str = Field(..., min_length=20)
    releaseNotes: str
    impactAssessment: Literal["low", "medium", "high", "critical"]
    rollbackPlan: str
    scheduledDate: Optional[datetime] = None

class PreChecks(BaseModel):
    stagingTestsPassed: bool
    securityScanPassed: bool
    performanceTestsPassed: bool
    testEvidenceUrl: str

class HistoryEntry(BaseModel):
    action: str
    at: datetime
    by: str
    comment: Optional[str] = None
    jobId: Optional[str] = None
    error: Optional[str] = None

class RequestStatus(BaseModel):
    state: Literal["pending", "approved", "rejected", "deploying", "deployed", "failed"]
    history: List[HistoryEntry] = []
    approvedBy: Optional[str] = None
    approvedAt: Optional[datetime] = None
    deployedAt: Optional[datetime] = None
    rejectedBy: Optional[str] = None
    rejectedAt: Optional[datetime] = None
    rejectionReason: Optional[str] = None

class RequestMetadata(BaseModel):
    id: str
    createdAt: datetime
    createdBy: str
    tenant: str

class PromotionRequest(BaseModel):
    apiVersion: str = "apim.cab-i.com/v1"
    kind: str = "PromotionRequest"
    metadata: RequestMetadata
    spec: dict  # Contains target, request, preChecks
    status: RequestStatus

# Request DTOs
class CreatePromotionRequest(BaseModel):
    target: TargetSpec
    request: RequestDetails
    preChecks: PreChecks

class ApproveRequest(BaseModel):
    comment: Optional[str] = None

class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=10)
```

---

## 🖥️ Composants React

### RequestCard.tsx

```typescript
interface RequestCardProps {
  request: PromotionRequest;
  onView: () => void;
  onApprove?: () => void;
  canApprove: boolean;
}

export const RequestCard: React.FC<RequestCardProps> = ({
  request,
  onView,
  onApprove,
  canApprove
}) => {
  return (
    <div className="border rounded-lg p-4 hover:shadow-md transition">
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center gap-2">
            <StatusBadge state={request.status.state} />
            <span className="font-mono text-sm text-gray-500">
              {request.metadata.id}
            </span>
          </div>
          <h3 className="font-semibold mt-1">
            {request.spec.target.name} v{request.spec.target.version}
          </h3>
          <p className="text-sm text-gray-600">
            {request.metadata.tenant} • {formatDate(request.metadata.createdAt)}
          </p>
          <p className="text-sm text-gray-500">
            By {request.metadata.createdBy}
          </p>
        </div>
        
        <div className="flex gap-2">
          <button onClick={onView} className="btn-secondary">
            View
          </button>
          {canApprove && request.status.state === 'pending' && (
            <button onClick={onApprove} className="btn-primary">
              Approve
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
```

### StatusBadge.tsx

```typescript
const statusConfig = {
  pending: { color: 'yellow', icon: '🟡', label: 'Pending' },
  approved: { color: 'blue', icon: '🔵', label: 'Approved' },
  deploying: { color: 'blue', icon: '🔄', label: 'Deploying' },
  deployed: { color: 'green', icon: '🟢', label: 'Deployed' },
  rejected: { color: 'red', icon: '🔴', label: 'Rejected' },
  failed: { color: 'red', icon: '❌', label: 'Failed' },
};

export const StatusBadge: React.FC<{ state: string }> = ({ state }) => {
  const config = statusConfig[state] || statusConfig.pending;
  
  return (
    <span className={`badge badge-${config.color}`}>
      {config.icon} {config.label}
    </span>
  );
};
```

### RequestTimeline.tsx

```typescript
export const RequestTimeline: React.FC<{ history: HistoryEntry[] }> = ({ history }) => {
  return (
    <div className="space-y-4">
      {history.map((entry, index) => (
        <div key={index} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className={`w-3 h-3 rounded-full ${getActionColor(entry.action)}`} />
            {index < history.length - 1 && (
              <div className="w-0.5 h-full bg-gray-200" />
            )}
          </div>
          <div>
            <p className="font-medium capitalize">{entry.action}</p>
            <p className="text-sm text-gray-500">
              {formatDateTime(entry.at)} • {entry.by}
            </p>
            {entry.comment && (
              <p className="text-sm text-gray-600 mt-1">{entry.comment}</p>
            )}
            {entry.error && (
              <p className="text-sm text-red-600 mt-1">{entry.error}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
```

---

## ✅ Checklist Finale

### Backend

- [ ] Modèle PromotionRequest
- [ ] Service Git (CRUD requests)
- [ ] Endpoint GET /requests/prod (liste + filtres)
- [ ] Endpoint POST /requests/prod (créer)
- [ ] Endpoint GET /requests/prod/{id} (détail)
- [ ] Endpoint POST /requests/prod/{id}/approve
- [ ] Endpoint POST /requests/prod/{id}/reject
- [ ] Validation RBAC
- [ ] Check anti-self-approval
- [ ] Trigger AWX sur approval
- [ ] Webhook callback AWX
- [ ] Update status deployed/failed

### Frontend

- [ ] Page ProductionRequests (liste)
- [ ] Filtres (state, tenant, search)
- [ ] RequestCard component
- [ ] StatusBadge component
- [ ] Page NewProductionRequest (formulaire)
- [ ] Validation formulaire
- [ ] Page RequestDetail
- [ ] RequestTimeline component
- [ ] Bouton Approve + confirmation
- [ ] Bouton Reject + modal reason
- [ ] Loading states
- [ ] Error handling
- [ ] Toast notifications

### Notifications

- [ ] Event Kafka request-created
- [ ] Event Kafka request-approved
- [ ] Event Kafka request-rejected
- [ ] Event Kafka deployment-succeeded
- [ ] Event Kafka deployment-failed
- [ ] Email aux approbateurs (nouvelle demande)
- [ ] Email au demandeur (approved/rejected)
- [ ] Slack notifications

### Tests

- [ ] Tests unitaires service
- [ ] Tests unitaires endpoints
- [ ] Test workflow complet
- [ ] Test RBAC
- [ ] Test anti-self-approval

---

## 🚀 Commandes de Démarrage

```bash
# Backend - Ajouter les fichiers
touch src/models/promotion_request.py
touch src/services/promotion_request_service.py
touch src/routers/promotion_requests.py
touch src/webhooks/awx_callback.py

# Frontend - Ajouter les fichiers
mkdir -p src/pages
mkdir -p src/components/requests
touch src/pages/ProductionRequests.tsx
touch src/pages/NewProductionRequest.tsx
touch src/pages/RequestDetail.tsx
touch src/components/requests/RequestCard.tsx
touch src/components/requests/StatusBadge.tsx
touch src/components/requests/RequestTimeline.tsx
touch src/components/requests/ApprovalActions.tsx
touch src/components/requests/RejectModal.tsx
touch src/hooks/useRequests.ts
```

---

## 📝 Notes

- Les tickets sont stockés dans Git → audit trail natif
- Le demandeur ne peut JAMAIS approuver sa propre demande
- L'approbation déclenche automatiquement AWX
- Le callback AWX met à jour le status dans Git
- Notifications à chaque étape du workflow
- Historique complet conservé dans le ticket YAML

---

Bon développement ! 🎯
