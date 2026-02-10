# OpenShift Delta

This page documents differences when deploying STOA Platform on OpenShift instead of standard Kubernetes (EKS).

## Security Context Constraints (SCC) vs Pod Security

| Concept | Kubernetes (EKS) | OpenShift |
|---------|-------------------|-----------|
| Pod security | Kyverno `restrict-privileged` policy | SCC (Security Context Constraints) |
| Non-root enforcement | `runAsNonRoot: true` in securityContext | `restricted-v2` SCC (default) |
| Privilege escalation | `allowPrivilegeEscalation: false` | Enforced by `restricted-v2` SCC |
| Capabilities | `drop: [ALL]` | `restricted-v2` drops all by default |

STOA is already compatible with OpenShift's `restricted-v2` SCC because all containers:

- Run as non-root
- Set `privileged: false` explicitly
- Drop all capabilities
- Use `seccompProfile: RuntimeDefault`

No SCC changes are needed. Verify with:

```bash
oc get scc restricted-v2 -o yaml
oc adm policy who-can use scc restricted-v2
```

## Routes vs Ingress

| Concept | Kubernetes (EKS) | OpenShift |
|---------|-------------------|-----------|
| External access | Ingress + nginx-ingress-controller | Route (OpenShift Router) |
| TLS termination | Ingress TLS annotation | Route TLS configuration |
| Cert management | cert-manager | Built-in or cert-manager |

### Creating Routes

Replace Ingress resources with OpenShift Routes:

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: control-plane-api
  namespace: stoa-system
spec:
  host: api.<BASE_DOMAIN>
  to:
    kind: Service
    name: control-plane-api
    weight: 100
  port:
    targetPort: 8000
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

Routes to create:

| Route | Host | Service | Port |
|-------|------|---------|------|
| control-plane-api | `api.<BASE_DOMAIN>` | control-plane-api | 8000 |
| control-plane-ui | `console.<BASE_DOMAIN>` | control-plane-ui | 80 |
| portal | `portal.<BASE_DOMAIN>` | portal | 80 |
| mcp-gateway | `mcp.<BASE_DOMAIN>` | mcp-gateway | 8080 |
| keycloak | `auth.<BASE_DOMAIN>` | keycloak | 8080 |

## Container Registry

| Concept | Kubernetes (EKS) | OpenShift |
|---------|-------------------|-----------|
| Registry | GHCR (GitHub Container Registry) | OpenShift Internal Registry |
| Auth | GITHUB_TOKEN | ServiceAccount tokens |
| Image reference | `ghcr.io/stoa-platform/<name>` | `image-registry.openshift-image-registry.svc:5000/stoa-system/<name>` |

### Using the Internal Registry

```bash
# Tag and push to internal registry
oc registry login
docker tag stoa/control-plane-api:latest \
  $(oc registry info)/stoa-system/control-plane-api:latest
docker push $(oc registry info)/stoa-system/control-plane-api:latest
```

Or use ImageStreams:

```yaml
apiVersion: image.openshift.io/v1
kind: ImageStream
metadata:
  name: control-plane-api
  namespace: stoa-system
spec:
  lookupPolicy:
    local: true
```

## `oc` Equivalents

| kubectl Command | oc Equivalent | Notes |
|----------------|--------------|-------|
| `kubectl get pods -n stoa-system` | `oc get pods -n stoa-system` | Same syntax |
| `kubectl apply -f` | `oc apply -f` | Same syntax |
| `kubectl logs` | `oc logs` | Same syntax |
| `kubectl exec` | `oc exec` | Same syntax |
| `kubectl get ingress` | `oc get routes` | Different resource |
| `kubectl port-forward` | `oc port-forward` | Same syntax |
| `kubectl set image` | `oc set image` | Same syntax |
| `kubectl rollout restart` | `oc rollout restart` | Same syntax |
| N/A | `oc new-project stoa-system` | Creates namespace + project |
| N/A | `oc adm policy add-scc-to-user` | SCC management |
| N/A | `oc registry login` | Internal registry auth |

## Helm Values for OpenShift

Override these values when deploying on OpenShift:

```yaml
global:
  openshift: true
  registry: "image-registry.openshift-image-registry.svc:5000/stoa-system"

ingress:
  enabled: false     # Use Routes instead

route:
  enabled: true
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

## Network Policies

OpenShift uses the same NetworkPolicy API as Kubernetes, but the default network plugin (OVN-Kubernetes) may behave differently from Calico/Cilium on EKS.

Verify network policies work:

```bash
oc get networkpolicy -n stoa-system
oc describe networkpolicy -n stoa-system
```

## Monitoring on OpenShift

OpenShift ships with a built-in monitoring stack (Prometheus + Alertmanager). To use it:

1. Create a `ServiceMonitor` for each STOA component (instead of Prometheus scrape configs)
2. Use the OpenShift Console's Monitoring section for dashboards
3. Or install Grafana separately in a custom namespace

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: control-plane-api
  namespace: stoa-system
spec:
  selector:
    matchLabels:
      app: control-plane-api
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

## Known Differences

| Area | Impact | Mitigation |
|------|--------|-----------|
| UID ranges | OpenShift assigns random UIDs | Already compatible (non-root, no hardcoded UID) |
| Filesystem | Some dirs read-only by default | nginx containers already handle this |
| DNS | CoreDNS config may differ | Use `DNS_RESOLVER` env var |
| Storage classes | Different default SC name | Set `storageClassName` in Helm values |
| Operator Hub | CRDs may conflict with OLM | Apply CRDs before Helm install |
