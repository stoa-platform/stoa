#!/usr/bin/env bash
# Restore the Service/gateway selector, targetPort, and Ingress paths saved
# by the first switch. Root `kubectl apply -k deploy/standalone` does not
# touch those objects, so it will not undo this.
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
exec python3 "$dir/../../switch.py" apisix
