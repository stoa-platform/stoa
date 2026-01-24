# Ticketing System - Production Requests

## 📋 Overview

**Objective**: Implement a manual validation workflow for PROD promotions with complete traceability.

**Estimated Duration**: 1 week

**Integration**: Added to the existing APIM Console (no external tools)

---

## 🎯 Features

| Feature | Description |
|---------|-------------|
| Create a request | DevOps submits a STAGING → PROD promotion request |
| RBAC Validation | Only CPI/Admins can approve |
| Anti-self-approval rule | Requester cannot approve their own request |
| Automated workflow | Approval → AWX Job → PROD Deployment |
| Notifications | Email + Slack at each step |
| Complete history | Audit trail in Git |

---

## 📁 Git Structure

```
stoa-gitops/
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

## 📄 YAML Ticket Format

```yaml
# requests/prod/2024/12/PR-2024-0003.yaml
apiVersion: gostoa.dev/v1
kind: PromotionRequest
metadata:
  id: PR-2024-0003
  createdAt: "2024-12-23T10:30:00Z"
  createdBy: pierre.durand@cab-i.com
  tenant: tenant-finance

spec:
  # Promotion target
  target:
    type: api                      # api | application | policy
    name: payment-api
    version: "2.1.0"
    sourceEnvironment: staging
    targetEnvironment: prod
  
  # Request details
  request:
    justification: "New PCI-DSS compliant payment flow"
    releaseNotes: |
      - Added 3DS2 authentication
      - Fixed timeout issues
      - Performance improvements
    impactAssessment: low          # low | medium | high | critical
    rollbackPlan: "Revert to v2.0.0 via emergency deploy"
    scheduledDate: null            # null = ASAP, or ISO date

  # Pre-deployment validation
  preChecks:
    stagingTestsPassed: true
    securityScanPassed: true
    performanceTestsPassed: true
    testEvidenceUrl: "https://gitlab.cab-i.com/pipeline/12345"

# Status (managed by the system)
status:
  state: pending                   # pending | approved | rejected | deploying | deployed | failed

  # Action history
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

  # Additional info
  approvedBy: jean.dupont@cab-i.com
  approvedAt: "2024-12-23T14:15:00Z"
  deployedAt: "2024-12-23T14:20:00Z"
  
  # In case of rejection
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
│   • PENDING → APPROVED : CPI approves                                           │
│   • PENDING → REJECTED : CPI rejects                                            │
│   • APPROVED → DEPLOYING : AWX job starts                                       │
│   • DEPLOYING → DEPLOYED : AWX job succeeds                                     │
│   • DEPLOYING → FAILED : AWX job fails                                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔐 RBAC

| Role | Create request | Approve | Reject | View |
|------|----------------|---------|--------|------|
| **DevOps** | ✅ Own tenant | ❌ | ❌ | Own requests |
| **CPI (Tenant Admin)** | ✅ Own tenant | ✅ Own tenant* | ✅ Own tenant | Own tenant |
| **CPI Admin** | ✅ All | ✅ All* | ✅ All | All |
| **Viewer** | ❌ | ❌ | ❌ | Own tenant |

*\* Except own requests (anti-self-approval)*

---

## 📅 Day-by-Day Planning

### Day 1: Data Model + CRUD API

| Task | Files |
|------|-------|
| Define Pydantic model | `src/models/promotion_request.py` |
| Git service for requests | `src/services/promotion_request_service.py` |
| CRUD endpoints | `src/routers/promotion_requests.py` |
| Unit tests | `tests/test_promotion_requests.py` |

**Endpoints to create:**

```python
GET    /v1/requests/prod                    # List (filters: state, tenant, createdBy)
POST   /v1/requests/prod                    # Create request
GET    /v1/requests/prod/{id}               # Detail
GET    /v1/requests/prod/pending            # Pending requests for me
GET    /v1/requests/prod/my                 # My requests
```

---

### Day 2: Approval Workflow

| Task | Files |
|------|-------|
| Approve endpoint | `src/routers/promotion_requests.py` |
| Reject endpoint | `src/routers/promotion_requests.py` |
| RBAC validation | `src/auth/permissions.py` |
| Anti-self-approval check | `src/services/promotion_request_service.py` |
| Trigger AWX on approval | `src/services/awx_service.py` |

**Endpoints to create:**

```python
POST   /v1/requests/prod/{id}/approve       # Approve (+ optional comment)
POST   /v1/requests/prod/{id}/reject        # Reject (+ mandatory reason)
```

**Approve logic:**

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

### Day 3: AWX Integration + Callbacks

| Task | Files |
|------|-------|
| Create AWX job template for PROD | AWX config |
| AWX → API callback webhook | `src/webhooks/awx_callback.py` |
| Update status on success/failure | `src/services/promotion_request_service.py` |
| Retry logic on failure | `src/services/promotion_request_service.py` |

**Webhook callback:**

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

### Day 4: UI - List and Filters

| Task | Files |
|------|-------|
| ProductionRequests page | `src/pages/ProductionRequests.tsx` |
| RequestCard component | `src/components/requests/RequestCard.tsx` |
| Filters (state, tenant) | `src/components/requests/RequestFilters.tsx` |
| Status badge with colors | `src/components/requests/StatusBadge.tsx` |
| useRequests hook | `src/hooks/useRequests.ts` |

**UI structure:**

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

### Day 5: UI - Request Form

| Task | Files |
|------|-------|
| NewRequest page | `src/pages/NewProductionRequest.tsx` |
| Form with validation | `src/pages/NewProductionRequest.tsx` |
| API/Version selector | `src/components/requests/ApiVersionSelector.tsx` |
| Pre-checks fields | `src/components/requests/PreChecksForm.tsx` |
| Submit + redirect | `src/pages/NewProductionRequest.tsx` |

**Form fields:**

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

### Day 6: UI - Detail and Actions

| Task | Files |
|------|-------|
| RequestDetail page | `src/pages/RequestDetail.tsx` |
| Actions timeline | `src/components/requests/RequestTimeline.tsx` |
| Approve/Reject buttons | `src/components/requests/ApprovalActions.tsx` |
| Confirmation modal | `src/components/requests/ConfirmModal.tsx` |
| Rejection modal (reason) | `src/components/requests/RejectModal.tsx` |

**Detail page:**

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

### Day 7: Notifications + Polish

| Task | Files |
|------|-------|
| Kafka notifications | `src/services/notification_service.py` |
| Email templates | `src/templates/emails/` |
| Slack notifications | `src/services/slack_service.py` |
| UI loading states | Global |
| UI error handling | Global |
| E2E tests | `tests/e2e/` |

**Kafka events:**

```python
# Topics
TOPIC_PROMOTION_REQUESTS = "promotion-requests"

# Events
"request-created"      # New request
"request-approved"     # Request approved
"request-rejected"     # Request rejected
"deployment-started"   # Deployment started
"deployment-succeeded" # Deployment succeeded
"deployment-failed"    # Deployment failed
```

**Email templates:**

```
src/templates/emails/
├── request_created.html       # For approvers
├── request_approved.html      # For requester
├── request_rejected.html      # For requester
├── deployment_started.html    # For requester + approver
├── deployment_succeeded.html  # For everyone
└── deployment_failed.html     # For everyone + ops
```

---

## 🔌 Complete API Endpoints

```python
# src/routers/promotion_requests.py

# List and search
GET    /v1/requests/prod
       Query: ?state=pending&tenant=tenant-finance&createdBy=user@email
       Response: List[PromotionRequest]

# My requests
GET    /v1/requests/prod/my
       Response: List[PromotionRequest]

# Pending requests for me (approver)
GET    /v1/requests/prod/pending
       Response: List[PromotionRequest]

# Create a request
POST   /v1/requests/prod
       Body: CreatePromotionRequest
       Response: PromotionRequest

# Request detail
GET    /v1/requests/prod/{id}
       Response: PromotionRequest

# Approve
POST   /v1/requests/prod/{id}/approve
       Body: { comment?: string }
       Response: PromotionRequest

# Reject
POST   /v1/requests/prod/{id}/reject
       Body: { reason: string }  # Required
       Response: PromotionRequest

# Stats (for dashboard)
GET    /v1/requests/prod/stats
       Response: {
         pending: number,
         approvedToday: number,
         rejectedToday: number,
         deployedThisWeek: number
       }
```

---

## 📦 Pydantic Models

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
    apiVersion: str = "gostoa.dev/v1"
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

## 🖥️ React Components

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

## ✅ Final Checklist

### Backend

- [ ] PromotionRequest model
- [ ] Git service (CRUD requests)
- [ ] GET /requests/prod endpoint (list + filters)
- [ ] POST /requests/prod endpoint (create)
- [ ] GET /requests/prod/{id} endpoint (detail)
- [ ] POST /requests/prod/{id}/approve endpoint
- [ ] POST /requests/prod/{id}/reject endpoint
- [ ] RBAC validation
- [ ] Anti-self-approval check
- [ ] Trigger AWX on approval
- [ ] AWX webhook callback
- [ ] Update status deployed/failed

### Frontend

- [ ] ProductionRequests page (list)
- [ ] Filters (state, tenant, search)
- [ ] RequestCard component
- [ ] StatusBadge component
- [ ] NewProductionRequest page (form)
- [ ] Form validation
- [ ] RequestDetail page
- [ ] RequestTimeline component
- [ ] Approve button + confirmation
- [ ] Reject button + reason modal
- [ ] Loading states
- [ ] Error handling
- [ ] Toast notifications

### Notifications

- [ ] Kafka event request-created
- [ ] Kafka event request-approved
- [ ] Kafka event request-rejected
- [ ] Kafka event deployment-succeeded
- [ ] Kafka event deployment-failed
- [ ] Email to approvers (new request)
- [ ] Email to requester (approved/rejected)
- [ ] Slack notifications

### Tests

- [ ] Service unit tests
- [ ] Endpoint unit tests
- [ ] Full workflow test
- [ ] RBAC test
- [ ] Anti-self-approval test

---

## 🚀 Getting Started Commands

```bash
# Backend - Add files
touch src/models/promotion_request.py
touch src/services/promotion_request_service.py
touch src/routers/promotion_requests.py
touch src/webhooks/awx_callback.py

# Frontend - Add files
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

- Tickets are stored in Git → native audit trail
- The requester can NEVER approve their own request
- Approval automatically triggers AWX
- The AWX callback updates the status in Git
- Notifications at each workflow step
- Complete history preserved in the YAML ticket

---

Happy coding! 🎯
