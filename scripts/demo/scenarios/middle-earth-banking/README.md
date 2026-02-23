# Bank of Gondor — Financial Services Demo

**Theme**: Fantasy bank — financial services APIs with regulatory compliance posture.

**Compliance context**: DORA (Digital Operational Resilience Act), NIS2

## Scenario Overview

The Bank of Gondor is a fictional financial institution that exposes core
banking APIs through STOA. The scenario demonstrates:

1. **Account Management** — KYC/AML-aware account operations
2. **Payment Processing** — SEPA and instant payments with SCA
3. **Risk Assessment** — Credit scoring and DORA ICT risk reporting

## Personas

| Username | Role | Description | Password |
|----------|------|-------------|----------|
| `gandalf` | tenant-admin | CISO / Risk Manager | `Gandalf2026!` |
| `aragorn` | devops | Trading Desk Developer | `Aragorn2026!` |
| `elrond` | viewer | Bank CTO / Architecture Review | `Elrond2026!` |

## APIs

| API | Category | Endpoints | Description |
|-----|----------|-----------|-------------|
| account-api | Banking | 4 | Account CRUD, balance inquiry, KYC status |
| payment-api | Payments | 4 | SEPA payments, status tracking, cancellation |
| risk-assessment-api | Risk | 4 | Risk scoring, assessment results, reporting |

## Plans

| Plan | Rate Limit | Approval | Use Case |
|------|-----------|----------|----------|
| Regulated | 30/min | Required | Internal regulated operations |
| Partner | 120/min | Required | External partner integrations (Rohan, etc.) |

## Demo Walkthrough

### Setup

```bash
export ADMIN_PASSWORD=<keycloak-admin-password>
./scripts/demo/setup.sh --scenario=middle-earth-banking
```

### Talking Points

1. **Portal view (as `aragorn`)**: Browse financial APIs, see OpenAPI specs
   with PSD2-compliant endpoints, subscribe to the Regulated plan

2. **Console view (as `gandalf`)**: CISO perspective — approve subscription
   requests, review rate limits, manage strict access policies for
   regulated workloads

3. **Risk & Compliance**: Demonstrate the risk-assessment-api with DORA
   ICT risk reporting — show how API governance supports the bank's
   compliance posture

4. **Multi-tenant isolation**: Show that Gondor's APIs are completely
   isolated from other tenants — Rohan partner can only access APIs
   through the Partner plan

### Teardown

```bash
./scripts/demo/teardown.sh --scenario=middle-earth-banking
```

## Compliance Disclaimer

> This demo illustrates technical capabilities relevant to DORA and NIS2
> compliance posture, including audit logging, access control, and incident
> response readiness. STOA Platform does not provide financial regulatory
> advice. Organizations must engage qualified compliance officers and auditors
> for official DORA/NIS2 assessment.
