#!/usr/bin/env bash
# Reproducible standalone image. FEATURES is empty (no Pingora, Kafka, or
# the Kubernetes watcher). The git SHA is the OCI revision label.
#
# Writes, next to the working directory:
#   stoa-gateway-<tag>.tar
#   stoa-gateway-<tag>.tar.sha256
#   stoa-gateway-<tag>.cdx.json          CycloneDX SBOM (syft, trivy fallback)
#   stoa-gateway-<tag>.trivy-high.txt    HIGH findings, to be triaged in writing
#
# Exits non-zero if Trivy reports any CRITICAL vulnerability.
# Does not push to a registry and does not talk to the cluster.
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"

SHA="${STOA_REVISION:-$(git rev-parse HEAD)}"
TAG="${STOA_IMAGE_TAG:-standalone}"
IMAGE="stoa-gateway:${TAG}"
OUT="${STOA_IMAGE_OUT:-$root/deploy/standalone}"
TAR="$OUT/stoa-gateway-${TAG}.tar"
TRIAGE="$OUT/IMAGE-TRIAGE.md"

if [[ ! -f stoa-gateway/Cargo.lock ]]; then
  echo "stoa-gateway/Cargo.lock is required" >&2
  exit 1
fi

echo "building ${IMAGE} revision ${SHA} FEATURES="
docker build \
  --build-arg FEATURES= \
  --build-arg REVISION="${SHA}" \
  --build-arg CACHEBUST="${SHA}" \
  -t "${IMAGE}" \
  -t "stoa-gateway:${SHA}" \
  stoa-gateway

revision=$(docker image inspect "${IMAGE}" -f '{{index .Config.Labels "org.opencontainers.image.revision"}}')
if [[ "$revision" != "$SHA" ]]; then
  echo "revision label is '${revision}', expected ${SHA}" >&2
  exit 1
fi
echo "label org.opencontainers.image.revision=${revision}"

mkdir -p "$OUT"
# Redirect, not -o: when docker runs as root the -o file is mode 0600 and
# the sha256 step cannot read it.
docker save "${IMAGE}" > "$TAR"
sha256sum "$TAR" | tee "${TAR}.sha256"

if command -v trivy >/dev/null 2>&1; then
  TRIVY=trivy
elif [[ -x /tmp/trivy ]]; then
  TRIVY=/tmp/trivy
else
  echo "installing trivy 0.58.1" >&2
  url="https://github.com/aquasecurity/trivy/releases/download/v0.58.1/trivy_0.58.1_Linux-64bit.tar.gz"
  if curl -fsSL -o /tmp/trivy.tgz "$url"; then
    tar -C /tmp -xzf /tmp/trivy.tgz trivy
  else
    echo "release tarball unavailable; copying the binary from aquasec/trivy:0.58.1" >&2
    docker pull aquasec/trivy:0.58.1
    # stdout redirect keeps the binary owned by the caller when docker is root.
    docker run --rm --entrypoint cat aquasec/trivy:0.58.1 /usr/local/bin/trivy > /tmp/trivy
    chmod a+rx /tmp/trivy
  fi
  TRIVY=/tmp/trivy
fi

echo "trivy CRITICAL (fail on any)"
"$TRIVY" image --input "$TAR" --severity CRITICAL --exit-code 1 --ignore-unfixed

echo "trivy HIGH (written for triage)"
"$TRIVY" image --input "$TAR" --severity HIGH --format table --ignore-unfixed | tee "$OUT/stoa-gateway-${TAG}.trivy-high.txt"

if command -v syft >/dev/null 2>&1; then
  syft "docker-archive:${TAR}" -o cyclonedx-json > "$OUT/stoa-gateway-${TAG}.cdx.json"
else
  "$TRIVY" image --input "$TAR" --format cyclonedx --output "$OUT/stoa-gateway-${TAG}.cdx.json"
fi
python3 -c 'import json,sys; n=len(json.load(open(sys.argv[1])).get("components") or []); print("sbom components", n); assert n>0' \
  "$OUT/stoa-gateway-${TAG}.cdx.json"

if [[ ! -f "$TRIAGE" ]]; then
  cat > "$TRIAGE" <<EOF
# Image HIGH triage

Image: \`${IMAGE}\`
Revision: \`${SHA}\`
Tar sha256: see \`stoa-gateway-${TAG}.tar.sha256\`

Trivy CRITICAL must be empty (the build script exits 1 otherwise).
Each HIGH below needs a one-line disposition before Friday: accept (base image, not reachable) or block.

| Vulnerability | Package | Disposition |
| --- | --- | --- |
| (paste from stoa-gateway-${TAG}.trivy-high.txt) |  |  |
EOF
  echo "wrote ${TRIAGE}; fill the HIGH table before the switch"
fi

echo "import on worker-3 (not run by this script):"
echo "  docker save ${IMAGE} | ssh worker-3 'sudo k3s ctr -n k8s.io images import -'"
echo "Deployment imagePullPolicy is Never. Do not kubectl apply from here."
