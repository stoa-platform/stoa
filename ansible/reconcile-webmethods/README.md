# 🔄 Ansible Playbook — webMethods Gateway Reconciliation

> **GitOps Reconciliation for webMethods API Gateway**
>
> This playbook automatically synchronizes APIs defined in Git to webMethods Gateway.

---

## 📋 Features

- ✅ **Create** new APIs (present in Git, missing from Gateway)
- ✅ **Update** modified APIs (diff Git vs Gateway)
- ✅ **Delete** orphaned APIs (optional)
- ✅ **Apply** security policies
- ✅ **Configure** backend aliases per environment
- ✅ **Notifications** via Slack/Discord/webhook
- ✅ **Dry-run mode** for simulation

---

## 🚀 Usage

### Local Execution

```bash
# Install dependencies
pip install ansible pyyaml

# Reconcile DEV
ansible-playbook reconcile-webmethods.yml -e "env=dev"

# Reconcile PROD (dry-run first)
ansible-playbook reconcile-webmethods.yml -e "env=prod" --check
ansible-playbook reconcile-webmethods.yml -e "env=prod"

# Without deleting orphans
ansible-playbook reconcile-webmethods.yml -e "env=dev delete_orphans=false"
```

### Via AWX

1. Import Job Template from `awx-job-template.yml`
2. Launch job using the form (environment, options)
3. Or trigger via webhook from ArgoCD/GitLab

---

## ⚙️ Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITOPS_DIR` | GitOps clone directory | `/opt/stoa-gitops` |
| `STOA_ENV` | Target environment | `dev` |
| `WM_GATEWAY_URL` | webMethods API URL | `http://apim-gateway:9072` |
| `WM_ADMIN_USER` | Gateway admin user | `Administrator` |
| `WM_ADMIN_PASSWORD` | Admin password | (required) |
| `DELETE_ORPHANS` | Delete orphaned APIs | `true` |
| `NOTIFY_WEBHOOK_URL` | Slack webhook | (optional) |
| `DISCORD_WEBHOOK_URL` | Discord webhook | (optional) |

---

## 📁 File Structure

```
ansible-webmethods/
├── reconcile-webmethods.yml    # Main playbook
├── awx-job-template.yml        # AWX configuration
├── README.md                   # This file
└── tasks/
    ├── load-git-apis.yml       # Load APIs from Git
    ├── fetch-gateway-apis.yml  # Fetch Gateway state
    ├── compute-diff.yml        # Calculate differences
    ├── compare-api.yml         # Compare single API
    ├── create-apis.yml         # Creation orchestration
    ├── create-single-api.yml   # Create single API
    ├── update-apis.yml         # Update orchestration
    ├── update-single-api.yml   # Update single API
    ├── delete-apis.yml         # Deletion orchestration
    ├── delete-single-api.yml   # Delete single API
    ├── apply-policies.yml      # Policy orchestration
    ├── apply-api-policies.yml  # Policies per API
    ├── apply-single-policy.yml # Apply single policy
    ├── configure-aliases.yml   # Alias orchestration
    ├── configure-single-alias.yml # Configure single alias
    └── notify.yml              # Notifications
```

---

## 🔄 Reconciliation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. LOAD                                                        │
│     ├── Load APIs from Git (webmethods/apis/*.yaml)             │
│     ├── Load Policies (webmethods/policies/*.yaml)              │
│     └── Load Aliases (webmethods/aliases/{env}.yaml)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. FETCH                                                       │
│     └── Retrieve current APIs from webMethods Gateway           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. DIFF                                                        │
│     ├── APIs to create (Git - Gateway)                          │
│     ├── APIs to delete (Gateway - Git)                          │
│     └── APIs to update (changes detected)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. APPLY                                                       │
│     ├── Create new APIs                                         │
│     ├── Update modified APIs                                    │
│     ├── Delete orphaned APIs (if enabled)                       │
│     ├── Apply policies                                          │
│     └── Configure aliases                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. NOTIFY                                                      │
│     └── Send summary (Slack/Discord/webhook)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔗 ArgoCD Integration

### Option 1: PostSync Hook

```yaml
# In ArgoCD Application
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  annotations:
    argocd.argoproj.io/sync-options: PostSync=true
spec:
  syncPolicy:
    syncOptions:
      - CreateNamespace=true
    automated:
      prune: true
      selfHeal: true
---
# Job triggered after sync
apiVersion: batch/v1
kind: Job
metadata:
  name: reconcile-webmethods
  annotations:
    argocd.argoproj.io/hook: PostSync
spec:
  template:
    spec:
      containers:
        - name: ansible
          image: ghcr.io/stoa-platform/ansible-runner:latest
          command: ["ansible-playbook", "reconcile-webmethods.yml"]
          env:
            - name: STOA_ENV
              value: "dev"
      restartPolicy: Never
```

### Option 2: Webhook → AWX

Configure a GitLab/GitHub webhook that triggers the AWX Job Template.

---

## 📊 Reconciliation Metrics

The playbook outputs metrics that can be scraped by Prometheus:

```
# HELP stoa_reconciliation_apis_total Total APIs reconciled
# TYPE stoa_reconciliation_apis_total gauge
stoa_reconciliation_apis_created{env="dev"} 2
stoa_reconciliation_apis_updated{env="dev"} 1
stoa_reconciliation_apis_deleted{env="dev"} 0
stoa_reconciliation_duration_seconds{env="dev"} 45
```

---

## 🔗 Links

- [CAB-367 — GitOps Reconciliation](https://linear.app/hlfh-workspace/issue/CAB-367)
- [stoa-gitops Repository](https://gitlab.com/cab6961310/stoa-gitops)
- [webMethods API Gateway REST API](https://documentation.softwareag.com/webmethods/api_gateway/)
