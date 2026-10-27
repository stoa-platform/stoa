#!/usr/bin/env bash
# Use the same offline bootstrap implementation as the Helm job.
set -euo pipefail
set +x
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
export PYTHONDONTWRITEBYTECODE=1
export KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
export KEYCLOAK_REALM="${KEYCLOAK_REALM:-stoa}"
exec python3 "$root/charts/stoa-platform/files/first_admin/main.py" "$@"
