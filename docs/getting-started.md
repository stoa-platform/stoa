# Getting Started with STOA Platform

This guide will help you get STOA Platform running quickly.

## Prerequisites

- **Docker** and **Docker Compose** (for local development)
- **Node.js 18+** (for UI development)
- **Python 3.11+** (for API development)
- **kubectl** (for Kubernetes deployment)
- **Helm 3+** (for Kubernetes deployment)

## Quick Start (Local Development)

### 1. Clone the Repository

```bash
git clone https://github.com/PotoMitan/stoa.git
cd stoa
```

### 2. Start Control-Plane API

```bash
cd control-plane-api
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

### 3. Start Console UI (API Provider Interface)

```bash
cd control-plane-ui
npm install
npm start
```

Access the Console UI at `http://localhost:3000`

### 4. Start Developer Portal (API Consumer Interface)

```bash
cd portal
npm install
npm run dev
```

Access the Developer Portal at `http://localhost:5173`

### 5. Start STOA Gateway

```bash
cd stoa-gateway
cargo run
```

## Kubernetes Deployment

The Helm chart currently deploys the Rust STOA Gateway and supporting resources.
The Control Plane API, console, Developer Portal, Keycloak and data services are
**not yet provided by the chart** and must be managed separately.

Follow the [gateway installation guide](./installation.md) to prepare values,
install the chart and verify the gateway. Docker Compose and local development
steps above have a different scope from the Helm release.

## Local Test Accounts

Create your own local test accounts in the separately configured Keycloak realm.
Replace the placeholders below with unique users and passwords from your secret
manager before testing; these are not accounts created by the Helm chart.

| User | Password | Role |
|------|----------|------|
| `<YOUR_TEST_ADMIN_USER>` | `REPLACE_FROM_VAULT` | CPI Admin |
| `<YOUR_TEST_VIEWER_USER>` | `REPLACE_FROM_VAULT` | Viewer |

## Next Steps

1. [Configure your environment](./configuration.md)
2. [Learn the architecture](./ARCHITECTURE-COMPLETE.md)
3. [Set up GitOps](./GITOPS-SETUP.md)
4. [Configure observability](./OBSERVABILITY.md)

## Getting Help

- Check the [documentation index](./README.md)
- Review [runbooks](./runbooks/) for operational issues
- Open an issue on [GitHub](https://github.com/PotoMitan/stoa/issues)
