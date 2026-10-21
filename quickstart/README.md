# STOA quickstart

Start the control plane and STOA Gateway, declare one API, and check that the gateway enforces access control.

Publisher: CAB Ingénierie — France. License: Apache 2.0.

## What this stack is

| Service | Role |
| --- | --- |
| `control-plane` | Control plane API. It starts and answers `GET /health`. |
| `postgres` | Database for the control plane. |
| `keycloak` | Token issuer for the caller. Image: `quay.io/keycloak/keycloak`, not GHCR. |
| `gateway` | STOA Gateway. Serves the declared API. |
| `backend` | Fake HTTP backend. `GET /` returns 200. |

There is no Redpanda. Its license is BSL, and this path does not need a broker: Kafka consumers on the control plane are off, and the gateway does not enable Kafka. Redis is not included. Nothing in this path needs it.

Third-party images and the control plane image are pinned by digest. None use a `latest` tag. The published control plane image is linux/amd64.

The gateway container is built from this repository with community features: no Kafka and no Pingora. The image on GHCR is built with Pingora, and that proxy closes the connection when it forwards the quickstart call, so this stack does not pull it. The first `docker compose up` compiles the gateway and then reuses `stoa-quickstart-gateway:community`.

Demo passwords in the compose file are the placeholder `placeholder-only`. They are not production credentials. `verify.sh` generates the caller client secret when it runs and does not print it.

## R1 declaration is the gateway admin API

The API is declared with:

```http
POST /admin/contracts
```

and `inboundAuth` set to `jwt`. That stores a `jwt_validation` policy on the route the gateway generates.

`POST /v1/tenants/{id}/apis` on the control plane is not used. On `main`, that route is published without a valid JWT policy. **The control plane does not protect the gateway route.** A later version will declare the API through the control plane. This quickstart does not claim that it does.

`verify.sh` then calls the gateway route:

- no `Authorization` header → `401`
- Keycloak client-credentials token → `200` from the fake backend

## Run

Docker Compose v2 and `openssl` are required. From this directory:

```bash
timeout 300 docker compose up --wait
./verify.sh
```

`docker compose up --wait` builds the gateway on first run, pulls the pinned images, and exits when every service is healthy. The `timeout 300` bound fails the run if that takes 300 seconds or more. `./verify.sh` exits non-zero unless declaration succeeds, the anonymous call returns 401, and the call with a token returns 200.

Ports on the host:

| Port | Service |
| --- | --- |
| 8000 | Control plane `GET /health` |
| 8080 | Keycloak |
| 8081 | Gateway |

Stop the stack with `docker compose down`.

## Images

Digest pins live in `docker-compose.yml`.

- `postgres:16.10-alpine`
- `quay.io/keycloak/keycloak:26.5.3`
- `ghcr.io/stoa-platform/control-plane-api:1.14.1`
- `stoa-quickstart-gateway:community`, built by `quickstart/Dockerfile.gateway` from this checkout (Rust 1.93, Debian bookworm, no Kafka, no Pingora)
- `nginx:1.27.5-alpine`
