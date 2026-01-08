# Gateway OIDC Configuration Drift Prevention

## Problem Statement

Le 8 janvier 2026, nous avons identifié une dérive de configuration dans le Gateway webMethods :
- **Stratégie OIDC-ControlPlaneApp** : `clientId` était `stoa-console` au lieu de `control-plane-ui`
- Cela causait des erreurs 401 "Audience match failed" car les tokens Keycloak ont `azp: control-plane-ui`

Cette dérive est survenue car des modifications manuelles ont été effectuées via l'UI Gateway, contournant l'Infrastructure as Code (Ansible).

---

## Root Cause Analysis

### What Happened
1. Initial deployment via Ansible with correct `clientId: control-plane-ui`
2. Someone modified the strategy manually via Gateway UI to use `stoa-console`
3. No mechanism to detect or prevent this drift

### Why It Happened
- Gateway UI allows unrestricted modifications
- No automated drift detection
- No reconciliation mechanism (like ArgoCD for K8s resources)

---

## Prevention Plan

### 1. Automated Drift Detection (Short-term)

Create a scheduled job to compare Gateway state vs. desired state in Ansible.

**Implementation:**

```yaml
# ansible/playbooks/detect-gateway-drift.yaml
---
- name: Detect Gateway OIDC Configuration Drift
  hosts: localhost
  connection: local
  gather_facts: false

  vars_files:
    - ../vars/secrets.yaml
    - ../vars/platform-config.yaml

  tasks:
    - name: Get current Gateway strategies
      uri:
        url: "{{ gateway.internal_url }}/rest/apigateway/strategies"
        method: GET
        user: "{{ gateway_user }}"
        password: "{{ gateway_password }}"
        force_basic_auth: true
        headers:
          Accept: "application/json"
      register: current_strategies

    - name: Check OIDC-ControlPlaneApp configuration
      set_fact:
        control_plane_strategy: "{{ current_strategies.json.strategies | selectattr('name', 'equalto', 'OIDC-ControlPlaneApp') | list | first }}"

    - name: Detect drift in clientId
      assert:
        that:
          - control_plane_strategy.clientId == 'control-plane-ui'
        fail_msg: |
          DRIFT DETECTED!
          Expected clientId: control-plane-ui
          Actual clientId: {{ control_plane_strategy.clientId }}
        success_msg: "No drift detected - clientId is correct"

    - name: Detect drift in audience
      assert:
        that:
          - control_plane_strategy.audience == 'account'
        fail_msg: |
          DRIFT DETECTED!
          Expected audience: account
          Actual audience: {{ control_plane_strategy.audience }}
        success_msg: "No drift detected - audience is correct"
```

**K8s CronJob to run detection:**

```yaml
# charts/stoa-platform/templates/gateway-drift-detection-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: gateway-drift-detection
  namespace: stoa-system
spec:
  schedule: "0 */4 * * *"  # Every 4 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: drift-detector
              image: ansible/ansible-runner:latest
              command:
                - ansible-playbook
                - /playbooks/detect-gateway-drift.yaml
              envFrom:
                - secretRef:
                    name: ansible-secrets
          restartPolicy: OnFailure
```

---

### 2. Gateway Read-Only Mode (Medium-term)

Configure Gateway to restrict modifications:

**Option A: LDAP/AD Integration with Role Restrictions**
- Create read-only LDAP groups for most users
- Only automation service accounts can modify

**Option B: API Gateway API Key Rotation**
- Rotate admin credentials after each Ansible run
- Store new credentials in AWS Secrets Manager
- Prevents manual login

---

### 3. GitOps for Gateway (Long-term)

Implement a GitOps approach similar to ArgoCD:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GitOps for webMethods Gateway                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   1. Desired State (Git)                                             │
│      └─> ansible/vars/gateway-oidc-config.yaml                       │
│                                                                      │
│   2. Reconciliation Controller                                       │
│      └─> K8s Operator or CronJob                                     │
│          ├─> Reads desired state from Git                            │
│          ├─> Compares with actual Gateway state                      │
│          └─> Applies corrections if drift detected                   │
│                                                                      │
│   3. Notification                                                    │
│      └─> Slack/Email alerts on drift detection                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Custom Operator Approach:**

Create a K8s operator that:
1. Watches a ConfigMap or CRD with desired Gateway configuration
2. Periodically checks Gateway state via API
3. Applies corrections automatically
4. Sends alerts on drift

---

### 4. Configuration Source of Truth

Create a single YAML file that defines all OIDC configurations:

```yaml
# ansible/vars/gateway-oidc-apps.yaml
---
# This is the SINGLE SOURCE OF TRUTH for Gateway OIDC configuration
# DO NOT modify Gateway manually - use Ansible playbooks only

gateway_oidc_apps:
  control_plane_ui:
    strategy:
      name: OIDC-ControlPlaneApp
      type: OAUTH2
      auth_server: KeycloakOIDC
      client_id: control-plane-ui
      audience: account
    application:
      name: ControlPlaneApp
      identifier:
        key: openIdClaims
        name: azp
        value: control-plane-ui
    apis:
      - Control-Plane-API
      - Gateway-Admin-API

  awx_automation:
    strategy:
      name: OIDC-AWXAutomation
      type: OAUTH2
      auth_server: KeycloakOIDC
      client_id: awx-automation
      audience: control-plane-api
    application:
      name: AWXAutomation
      identifier:
        key: openIdClaims
        name: azp
        value: awx-automation
    apis:
      - Control-Plane-API
```

---

### 5. Alerts on Drift

Integrate with monitoring:

```yaml
# Prometheus AlertManager rule
groups:
  - name: gateway-drift
    rules:
      - alert: GatewayOIDCConfigurationDrift
        expr: gateway_oidc_drift_detected == 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Gateway OIDC configuration drift detected"
          description: "The Gateway OIDC configuration has drifted from the desired state. Run ansible-playbook bootstrap-platform.yaml to reconcile."
```

---

## Recommended Actions

| Priority | Action | Effort |
|----------|--------|--------|
| 1 | Add drift detection playbook | Low |
| 2 | Create K8s CronJob for detection | Low |
| 3 | Add Slack/Email alerts | Low |
| 4 | Create single source of truth YAML | Medium |
| 5 | Implement auto-reconciliation | Medium |
| 6 | Gateway RBAC restrictions | High |
| 7 | Custom K8s Operator | High |

---

## Immediate Fix Applied

On 2026-01-08, the following fix was applied:

```bash
# Strategy OIDC-ControlPlaneApp
curl -X PUT http://localhost:5555/rest/apigateway/strategies/{id} \
  -d '{"clientId": "control-plane-ui", ...}'
```

This corrected the `clientId` from `stoa-console` to `control-plane-ui`.

---

## Documentation Updates

Added to CLAUDE.md:
- Docker build requirements for multi-arch images
- Gateway OIDC configuration drift prevention reference

---

## Contact

For questions about Gateway OIDC configuration:
- Platform Team: admin@cab-i.com
- GitOps Repository: https://gitlab.com/cab6961310/stoa-gitops
