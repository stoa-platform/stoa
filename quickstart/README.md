# STOA quickstart

Start the control plane and STOA Gateway, declare one API, and check that the gateway enforces access control.

Publisher: CAB Ingénierie — France. License: Apache 2.0.

## Prerequisites

| Tool | Requirement |
| --- | --- |
| Bash | The shell used by `verify.sh`. |
| curl | Calls the control plane and the gateway from the host. |
| openssl | `verify.sh` generates the caller client secret with `openssl rand`. |
| Docker Engine | Runs the stack. |
| Docker Compose | **2.1.1 or newer.** `docker compose up --wait` was added in 2.1.1. Check with `docker compose version`. |
| GNU `timeout` | Bounds `docker compose up` to 300 seconds. It ships with coreutils on Linux and is absent on macOS. |

On macOS, either install coreutils and use `gtimeout`, or use the Perl alternative (Perl ships with macOS):

```bash
brew install coreutils
gtimeout 300 docker compose up --wait
```

```bash
perl -e 'alarm shift; exec @ARGV' 300 docker compose up --wait
```

`verify.sh` bounds its own run (120 seconds by default, override with `VERIFY_TIMEOUT`). It uses `timeout` or `gtimeout` when one of them is on `PATH`, and otherwise Perl. It does not require GNU `timeout`.

## What this stack is

| Service | Role |
| --- | --- |
| `control-plane` | Control plane API. It starts and answers `GET /health`. |
| `postgres` | Database for the control plane. |
| `keycloak` | Token issuer for the caller. Image: `quay.io/keycloak/keycloak`, not GHCR. |
| `gateway` | STOA Gateway. Serves the declared API. |
| `backend` | Fake HTTP backend. `GET /` returns 200. |

There is no Redpanda. Its license is BSL, and this path does not need a broker: Kafka consumers on the control plane are off, and the gateway does not enable Kafka. Redis is not included. Nothing in this path needs it.

Third-party images and the control plane image are pinned by digest. None use a `latest` tag. The published control plane image is linux/amd64. The gateway build is `cargo build --release --locked` from `stoa-gateway/Cargo.lock`.

The gateway container is built from this repository with the default features: no Kafka and no Pingora. Its local tag is `stoa-quickstart-gateway:0.9.25`, the version in `stoa-gateway/Cargo.toml`. That tag is the crate version of this checkout. It is not a pull of a registry image. The image on GHCR is built with Pingora, and that proxy closes the connection when it forwards the quickstart call, so this stack does not pull it.

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
- `Authorization: Bearer invalid` → `401`
- Keycloak client-credentials token → `200` from the fake backend

## Run

From this directory, on Linux:

```bash
timeout 300 docker compose up --wait
./verify.sh
```

On macOS, replace the first command with `gtimeout` or the Perl one-liner in Prerequisites. `./verify.sh` is the same on both.

`docker compose up --wait` builds the gateway on first run, pulls the pinned images, and exits when every service is healthy. The 300 second bound fails the run if that takes 300 seconds or more. `./verify.sh` exits non-zero unless declaration succeeds, the anonymous call returns 401, the invalid token returns 401, and the call with a token returns 200.

Host ports are bound to `127.0.0.1`:

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
- `stoa-quickstart-gateway:0.9.25`, built by `quickstart/Dockerfile.gateway` from this checkout (Rust 1.93, Debian bookworm, `cargo build --locked`, no Kafka, no Pingora)
- `nginx:1.27.5-alpine`
