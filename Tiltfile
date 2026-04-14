# -*- mode: Python -*-
# =============================================================================
# STOA Platform — Tilt Local Development
# =============================================================================
#
# Prerequisites:
#   brew install tilt k3d
#   k3d cluster create --config ../stoa-infra/deploy/tilt/k3d-config.yaml
#   cp deploy/docker-compose/.env.example deploy/docker-compose/.env
#   docker compose -f ../stoa-infra/deploy/tilt/docker-compose-stateful.yml \
#     --env-file deploy/docker-compose/.env up -d
#
# Usage:
#   tilt up        # start k8s workloads (stateful services must be running)
#   tilt down      # stop k8s workloads
#
# Architecture:
#   Docker Compose (manual): postgres, keycloak, redpanda
#   k3d (via Tilt):          control-plane-api, control-plane-ui, portal, stoa-gateway
#
# =============================================================================

infra_repo = '../stoa-infra'
k3d_cluster = 'stoa-dev'

allow_k8s_contexts('k3d-stoa-dev')
default_registry('localhost:5111')

# ── Stub secrets (needed by Helm chart envFrom) ──────────────────────────────
k8s_yaml(blob("""
apiVersion: v1
kind: Secret
metadata:
  name: stoa-local-secrets
type: Opaque
stringData:
  token: "unused"
  project-id: "0"
  webhook-secret: "unused"
"""))

# ── Image builds ─────────────────────────────────────────────────────────────

docker_build(
    'stoa-platform/control-plane-api',
    context='control-plane-api',
    dockerfile='control-plane-api/Dockerfile',
)

docker_build(
    'stoa-platform/control-plane-ui',
    context='.',
    dockerfile='control-plane-ui/Dockerfile.dev',
    only=['control-plane-ui/', 'shared/', 'tsconfig.base.json'],
)

docker_build(
    'stoa-platform/portal',
    context='.',
    dockerfile='portal/Dockerfile.dev',
    only=['portal/', 'shared/', 'tsconfig.base.json'],
)

docker_build(
    'stoa-platform/stoa-gateway',
    context='stoa-gateway',
    dockerfile='stoa-gateway/Dockerfile',
)

# ── Helm Charts ──────────────────────────────────────────────────────────────

k8s_yaml(helm(
    infra_repo + '/charts/control-plane-api',
    values=[infra_repo + '/deploy/tilt/values-local/control-plane-api.yaml'],
))
k8s_resource('stoa-control-plane-api', port_forwards=['8000:8000'], labels=['workloads'])

k8s_yaml(helm(
    infra_repo + '/charts/control-plane-ui',
    values=[infra_repo + '/deploy/tilt/values-local/control-plane-ui.yaml'],
))
k8s_resource('control-plane-ui', port_forwards=['5173:5173'], labels=['workloads'])

k8s_yaml(helm(
    infra_repo + '/charts/stoa-portal',
    values=[infra_repo + '/deploy/tilt/values-local/stoa-portal.yaml'],
))
k8s_resource('stoa-portal', port_forwards=['5174:5174'], labels=['workloads'])

k8s_yaml(helm(
    infra_repo + '/charts/stoa-gateway',
    values=[infra_repo + '/deploy/tilt/values-local/stoa-gateway.yaml'],
))
k8s_resource('stoa-gateway', port_forwards=['8081:8080'], labels=['workloads'])
