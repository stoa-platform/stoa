#!/usr/bin/env bash
# Render deploy/standalone manifests from params.env and apply them.
# Does not apply secret.yaml (placeholder only).
set -euo pipefail

dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
set -a
source "$dir/params.env"
set +a

: "${STOA_NODE_HOSTNAME:?set STOA_NODE_HOSTNAME in params.env}"
: "${STOA_NAMESPACE:?set STOA_NAMESPACE in params.env}"
: "${STOA_PUBLIC_HOST:?set STOA_PUBLIC_HOST in params.env}"
: "${STOA_IMAGE:?set STOA_IMAGE in params.env}"

render() {
  sed \
    -e "s/__NODE_HOSTNAME__/${STOA_NODE_HOSTNAME}/g" \
    -e "s/__NAMESPACE__/${STOA_NAMESPACE}/g" \
    -e "s/__PUBLIC_HOST__/${STOA_PUBLIC_HOST}/g" \
    -e "s|__IMAGE__|${STOA_IMAGE}|g" \
    "$1"
}

if [[ "${1:-}" == "--print" ]]; then
  for f in namespace.yaml configmap.yaml deployment.yaml service.yaml ingress.yaml; do
    echo "---"
    render "$dir/$f"
  done
  exit 0
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for f in namespace.yaml configmap.yaml deployment.yaml service.yaml ingress.yaml; do
  render "$dir/$f" >"$tmp/$f"
done

kubectl apply -f "$tmp/namespace.yaml"

if ! kubectl -n "$STOA_NAMESPACE" get secret stoa-gateway-admin >/dev/null 2>&1; then
  echo "Secret ${STOA_NAMESPACE}/stoa-gateway-admin is missing." >&2
  echo "Create it before the Deployment is applied:" >&2
  echo "  kubectl -n ${STOA_NAMESPACE} create secret generic stoa-gateway-admin --from-literal=STOA_ADMIN_API_TOKEN=\"\$(openssl rand -hex 32)\"" >&2
  exit 1
fi

kubectl apply -f "$tmp/configmap.yaml" -f "$tmp/deployment.yaml" -f "$tmp/service.yaml" -f "$tmp/ingress.yaml"
