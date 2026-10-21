#!/usr/bin/env bash
# 1. Require stoa-gateway:standalone on worker-3 at the revision in
#    deploy/standalone/IMAGE-REVISION (imagePullPolicy is Never).
# 2. Set STOA_TRUSTED_PROXIES to the current ingress-nginx pod IPs.
#    The manifest keeps the sentinel. A node /24 is never written.
#    The switch stops if the sentinel is still there.
# 3. Restart the deployment so the process reads those IPs, then retarget
#    Service/gateway and narrow Ingress stoa-api to /apis.
# Do not `kubectl apply -k` this directory: apply merges selector keys and 502s.
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
python3 "$dir/../../switch.py" preflight
exec python3 "$dir/../../switch.py" stoa
