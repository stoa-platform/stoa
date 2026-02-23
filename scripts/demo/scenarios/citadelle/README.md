# La Citadelle — Public Sector Demo

**Theme**: French public sector ministry — API interoperability for citizen services.

**Compliance context**: RGS (Referentiel General de Securite), SecNumCloud

## Scenario Overview

La Citadelle is a fictional French ministry ("Ministere de l'Interoperabilite
Numerique") that exposes citizen-facing APIs through STOA. The scenario
demonstrates:

1. **Citizen Identity Verification** — FranceConnect-style identity checks
2. **Secure Document Management** — eIDAS signatures, archival with integrity hashes
3. **Inter-Ministry Data Exchange** — structured data exchange with schema validation

## Personas

| Username | Role | Description | Password |
|----------|------|-------------|----------|
| `durand` | tenant-admin | RSSI / Responsable Securite des SI | `Durand2026!` |
| `martin` | devops | Developpeur services citoyens | `Martin2026!` |
| `leroy` | viewer | Administratrice ministere | `Leroy2026!` |

## APIs

| API | Category | Endpoints | Description |
|-----|----------|-----------|-------------|
| citizen-identity-api | Identity | 3 | Verification d'identite, profil citoyen, documents |
| document-management-api | Documents | 4 | Depot, consultation, suivi statut, signature |
| interop-api | Interop | 4 | Echange inter-ministeres, catalogue de schemas |

## Plans

| Plan | Rate Limit | Approval | Use Case |
|------|-----------|----------|----------|
| Souverain | 60/min | Required | External partners, controlled access |
| Interne | 300/min | Auto | Internal ministry applications |

## Demo Walkthrough

### Setup

```bash
export ADMIN_PASSWORD=<keycloak-admin-password>
./scripts/demo/setup.sh --scenario=citadelle
```

### Talking Points

1. **Portal view (as `martin`)**: Browse the API catalog, see citizen-identity-api
   with its OpenAPI spec, subscribe to the Souverain plan

2. **Console view (as `durand`)**: Approve subscription requests, review audit logs,
   manage access policies — demonstrate the RSSI's control over API access

3. **Interoperability**: Show the exchange API — structured data exchange between
   ministries with full traceability and schema validation

4. **Compliance posture**: Highlight rate limiting, API key requirements, audit
   logging — all contributing to the RGS compliance posture

### Teardown

```bash
./scripts/demo/teardown.sh --scenario=citadelle
```

## Compliance Disclaimer

> This demo illustrates technical capabilities that support RGS compliance
> posture, including data sovereignty controls and secure API interoperability.
> STOA Platform is not RGS-certified or SecNumCloud-qualified. Organizations
> must consult ANSSI guidelines and qualified auditors for official evaluation.
