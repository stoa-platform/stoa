# Gateway URL Contract

This runbook fixes the naming contract used by Console, GatewayInstance CRDs,
and WebMethods operations.

## URL Fields

| Field | Meaning | WebMethods examples |
|---|---|---|
| `base_url` / `adminUrl` | Internal admin endpoint used by the Control Plane or reconciler. May be cluster-local or container-local. | `http://stoa-link-wm-staging:8080` |
| `public_url` / `publicUrl` | Public runtime URL for this STOA or third-party runtime instance. | `https://staging-wm-k3s.gostoa.dev`, `https://vps-wm-link.gostoa.dev` |
| `target_gateway_url` / `targetGatewayUrl` | Third-party gateway target controlled by STOA Link or STOA Connect. | `https://staging-wm.gostoa.dev` |
| `ui_url` / `uiUrl` | Third-party gateway web UI. This is never a STOA Link runtime URL. | `https://staging-wm-ui.gostoa.dev` |

## WebMethods Surface Matrix

| Environment | Surface | `publicUrl` | `targetGatewayUrl` | `uiUrl` |
|---|---|---|---|---|
| dev | Connect VPS | `https://dev-wm.gostoa.dev` | `https://dev-wm.gostoa.dev` | `https://dev-wm-ui.gostoa.dev` |
| dev | Link K8s | `https://dev-wm-k3s.gostoa.dev` | `https://dev-wm.gostoa.dev` | `https://dev-wm-ui.gostoa.dev` |
| staging | Connect VPS | `https://staging-wm.gostoa.dev` | `https://staging-wm.gostoa.dev` | `https://staging-wm-ui.gostoa.dev` |
| staging | Link K8s | `https://staging-wm-k3s.gostoa.dev` | `https://staging-wm.gostoa.dev` | `https://staging-wm-ui.gostoa.dev` |
| prod | Connect VPS | `https://vps-wm.gostoa.dev` | `https://vps-wm.gostoa.dev` | `https://vps-wm-ui.gostoa.dev` |
| prod | Link VPS | `https://vps-wm-link.gostoa.dev` | `https://vps-wm.gostoa.dev` | `https://vps-wm-ui.gostoa.dev` |

## Invalid States

- A non-prod WebMethods `uiUrl` must not point to `https://vps-wm-ui.gostoa.dev`.
- A WebMethods `uiUrl` must not point to a STOA Link runtime such as `*-wm-k3s.gostoa.dev`
  or `vps-wm-link.gostoa.dev`.
- A WebMethods Link runtime has `publicUrl != targetGatewayUrl`.
- A WebMethods Connect registration has `publicUrl == targetGatewayUrl`.

## Operational Checks

For WebMethods, smoke the public target and UI separately:

```bash
curl -fsS https://dev-wm.gostoa.dev/health
curl -fsSI https://dev-wm-ui.gostoa.dev/
curl -fsS https://dev-wm-k3s.gostoa.dev/health

curl -fsS https://staging-wm.gostoa.dev/health
curl -fsSI https://staging-wm-ui.gostoa.dev/
curl -fsS https://staging-wm-k3s.gostoa.dev/health

curl -fsS https://vps-wm.gostoa.dev/health
curl -fsSI https://vps-wm-ui.gostoa.dev/
curl -fsS https://vps-wm-link.gostoa.dev/health
```

If the Link runtime is healthy but `targetGatewayUrl` or `uiUrl` returns 5xx,
debug the WebMethods VPS or its Caddy upstream before changing Console URL data.
