# CAB-2173 Verification

Date: 2026-04-25
Ticket: CAB-2173

## Rust

| Command | Result |
|---------|--------|
| `cargo fmt --check` in `stoa-gateway` | PASS |
| `cargo clippy --all-targets -- -D warnings` in `stoa-gateway` | PASS |
| `cargo test mode::decision` in `stoa-gateway` | PASS, 5 tests |
| `cargo test mode::sidecar` in `stoa-gateway` | PASS, 29 tests |
| `cargo test sidecar_mode_exposes_authz_without_mcp_routes` in `stoa-gateway` | PASS, proves sidecar exposes `/authz` and does not mount `/mcp`. |

## Helm and Manifests

| Command | Result |
|---------|--------|
| `helm lint charts/stoa-platform` | PASS, only chart icon recommendation. |
| `helm template stoa-sidecar ./charts/stoa-platform -n stoa-system --set stoaGateway.enabled=false --set stoaSidecar.enabled=true --set stoaSidecar.mainGateway.enabled=true` | PASS. Rendered `Deployment/webmethods-with-stoa-sidecar` with containers `webmethods` and `stoa-sidecar`, labels `stoa.io/deployment-kind=sidecar`, and annotation `stoa.io/topology=same-pod-sidecar`. |
| `helm template stoa-sidecar-fail ./charts/stoa-platform -n stoa-system --set stoaGateway.enabled=false --set stoaSidecar.enabled=true --set stoaSidecar.mainGateway.enabled=false` | Expected FAIL. Helm stops with the sidecar topology guardrail message. |
| `rg "STOA_SIDECAR_UPSTREAM_URL|Kong DB-less \\+ STOA Gateway sidecar|In prod, Kong would use ext_authz|stoa-sidecar" deploy/k3d k8s/gateways/base/stoa-link-wm scripts/traffic/link-traffic-seed.sh` | PASS by no matches. Misleading standalone demo wording/env var removed from the touched manifests/scripts. |
| `git diff --check` | PASS |

## Footprint

| Measurement | Result |
|-------------|--------|
| `cargo build --release` in `stoa-gateway` | PASS, default feature set. |
| `ls -lh stoa-gateway/target/release/stoa-gateway` | `27M`, timestamp `Apr 25 09:48`. |
| `stat -f "%z bytes %Sm" stoa-gateway/target/release/stoa-gateway` | `28153520 bytes`, `Apr 25 09:48:42 2026`. |

The release binary was measured after CAB-2173 changes using default features.
Optional dependencies for Kafka, Kubernetes watchers, and Pingora remain feature
gated in `Cargo.toml`; they are not required for the lean sidecar build.

## Remaining Boundaries

- No container image was built in this verification pass, so compressed image
  size remains a release-pipeline measurement.
- No live webMethods or Kong cluster smoke was run; this ticket proves the
  route/runtime split, Helm topology, manifest labelling, and local Rust
  behavior.
