# Rollback to APISIX

`rollback.sh` restores the selector, the port 9080 targetPort, and the
`api.gostoa.dev` Ingress paths captured by the first
`../use-stoa-gateway/switch.sh` into ConfigMap `stoa/stoa-gateway-switch-backup`.

It does not guess `app: apisix`. If that ConfigMap is gone, set
`STOA_APISIX_SELECTOR` from `kubectl -n stoa get svc gateway -o yaml` first.

`kubectl apply -k deploy/standalone` does not list Service `gateway`, the
Ingress, or the backup ConfigMap, so a later apply leaves this rollback in place.
