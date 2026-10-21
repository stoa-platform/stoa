#!/usr/bin/env bash
# Retarget Service/gateway (port 9080 -> container 8080, selector app=stoa-gateway)
# and narrow Ingress host api.gostoa.dev to /apis.
# Do not `kubectl apply -k` this directory: apply merges selector keys and 502s.
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
exec python3 "$dir/../../switch.py" stoa
