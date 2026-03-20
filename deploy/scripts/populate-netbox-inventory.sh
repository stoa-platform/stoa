#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Netbox Inventory Population
# =============================================================================
# Populates Netbox with the full STOA VPS fleet (14 VMs) via REST API.
# Creates sites, clusters, VMs with IPs, roles, and tags.
# Removes obsolete Hetzner entries.
#
# Usage:
#   NETBOX_API_TOKEN=nbt_xxx ./deploy/scripts/populate-netbox-inventory.sh
#
# Prerequisites:
#   - Netbox running at https://netbox.gostoa.dev with working API token
#   - curl and jq installed
#
# WARNING: This script modifies live Netbox data. Run manually, not in CI.
# =============================================================================

set -euo pipefail

NETBOX_URL="${NETBOX_URL:-https://netbox.gostoa.dev}"
NETBOX_API_TOKEN="${NETBOX_API_TOKEN:?NETBOX_API_TOKEN is required (format: nbt_KEY.TOKEN or legacy token)}"
API="${NETBOX_URL}/api"

# Common curl wrapper
nb_api() {
  local method="$1" endpoint="$2"
  shift 2
  curl -sf -X "${method}" \
    "${API}${endpoint}" \
    -H "Authorization: Token ${NETBOX_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    "$@"
}

# Create or get by name — returns ID
create_or_get() {
  local endpoint="$1" name="$2" payload="$3"
  local existing
  existing=$(nb_api GET "${endpoint}?name=${name}" | jq -r '.results[0].id // empty')
  if [ -n "${existing}" ]; then
    echo "  [exists] ${name} (ID: ${existing})" >&2
    echo "${existing}"
    return
  fi
  local result
  result=$(nb_api POST "${endpoint}" -d "${payload}")
  local id
  id=$(echo "${result}" | jq -r '.id')
  echo "  [created] ${name} (ID: ${id})" >&2
  echo "${id}"
}

# Create or get tag by slug
create_or_get_tag() {
  local name="$1" slug="$2" color="$3"
  local existing
  existing=$(nb_api GET "/extras/tags/?slug=${slug}" | jq -r '.results[0].id // empty')
  if [ -n "${existing}" ]; then
    echo "${existing}"
    return
  fi
  nb_api POST "/extras/tags/" -d "{\"name\":\"${name}\",\"slug\":\"${slug}\",\"color\":\"${color}\"}" | jq -r '.id'
}

# Create VM with IP
create_vm() {
  local name="$1" cluster_id="$2" role_id="$3" vcpus="$4" memory="$5" disk="$6" ip="$7" tags_json="$8" comments="$9"

  # Check if VM exists
  local existing
  existing=$(nb_api GET "/virtualization/virtual-machines/?name=${name}" | jq -r '.results[0].id // empty')
  if [ -n "${existing}" ]; then
    echo "  [exists] VM ${name} (ID: ${existing})" >&2
    return
  fi

  local vm_payload
  vm_payload=$(cat <<VMJSON
{
  "name": "${name}",
  "cluster": ${cluster_id},
  "role": ${role_id},
  "status": "active",
  "vcpus": ${vcpus},
  "memory": ${memory},
  "disk": ${disk},
  "tags": ${tags_json},
  "comments": "${comments}"
}
VMJSON
)

  local vm_result vm_id
  vm_result=$(nb_api POST "/virtualization/virtual-machines/" -d "${vm_payload}")
  vm_id=$(echo "${vm_result}" | jq -r '.id')
  echo "  [created] VM ${name} (ID: ${vm_id})" >&2

  # Create interface
  local iface_id
  iface_id=$(nb_api POST "/virtualization/interfaces/" \
    -d "{\"virtual_machine\":${vm_id},\"name\":\"eth0\",\"enabled\":true}" | jq -r '.id')

  # Create IP and assign to interface
  if [ -n "${ip}" ] && [ "${ip}" != "null" ]; then
    local ip_result ip_id
    ip_result=$(nb_api POST "/ipam/ip-addresses/" \
      -d "{\"address\":\"${ip}/32\",\"assigned_object_type\":\"virtualization.vminterface\",\"assigned_object_id\":${iface_id},\"status\":\"active\"}")
    ip_id=$(echo "${ip_result}" | jq -r '.id')

    # Set as primary IPv4
    nb_api PATCH "/virtualization/virtual-machines/${vm_id}/" \
      -d "{\"primary_ip4\":${ip_id}}" > /dev/null
    echo "    [ip] ${ip} assigned" >&2
  fi
}

echo "=== STOA Netbox Inventory Population ==="
echo "Netbox URL: ${NETBOX_URL}"
echo ""

# ─── Tags ────────────────────────────────────────────────────────────────────
echo "[1/6] Creating tags..."
TAG_HEGEMON=$(create_or_get_tag "hegemon" "hegemon" "4caf50")
TAG_GATEWAY=$(create_or_get_tag "gateway" "gateway" "2196f3")
TAG_TOOLING=$(create_or_get_tag "tooling" "tooling" "ff9800")
TAG_PROD=$(create_or_get_tag "production" "production" "f44336")
TAG_STAGING=$(create_or_get_tag "staging" "staging" "9c27b0")
echo "  Tags ready."

# ─── Sites ───────────────────────────────────────────────────────────────────
echo ""
echo "[2/6] Creating sites..."
SITE_CONTABO=$(create_or_get "/dcim/sites/" "Contabo Nuremberg" \
  '{"name":"Contabo Nuremberg","slug":"contabo-nuremberg","status":"active","description":"Contabo VPS L fleet — HEGEMON workers","physical_address":"Nuremberg, Germany"}')
SITE_OVH_GRA=$(create_or_get "/dcim/sites/" "OVH GRA" \
  '{"name":"OVH GRA","slug":"ovh-gra","status":"active","description":"OVH Gravelines — production MKS + VPS","physical_address":"Gravelines, France"}')
SITE_OVH_SBG=$(create_or_get "/dcim/sites/" "OVH SBG" \
  '{"name":"OVH SBG","slug":"ovh-sbg","status":"active","description":"OVH Strasbourg — gateway VPS","physical_address":"Strasbourg, France"}')

# ─── Cluster Types ───────────────────────────────────────────────────────────
echo ""
echo "[3/6] Creating cluster types and clusters..."
CTYPE_VPS=$(create_or_get "/virtualization/cluster-types/" "VPS Fleet" \
  '{"name":"VPS Fleet","slug":"vps-fleet","description":"Virtual Private Server fleet"}')
CTYPE_K8S=$(create_or_get "/virtualization/cluster-types/" "Kubernetes" \
  '{"name":"Kubernetes","slug":"kubernetes","description":"Managed Kubernetes cluster"}')

# ─── Clusters ────────────────────────────────────────────────────────────────
CLUSTER_HEGEMON=$(create_or_get "/virtualization/clusters/" "HEGEMON Fleet" \
  "{\"name\":\"HEGEMON Fleet\",\"slug\":\"hegemon-fleet\",\"type\":${CTYPE_VPS},\"site\":${SITE_CONTABO},\"description\":\"5x Contabo VPS L — autonomous AI workers\"}")
CLUSTER_GW_VPS=$(create_or_get "/virtualization/clusters/" "OVH Gateway VPS" \
  "{\"name\":\"OVH Gateway VPS\",\"slug\":\"ovh-gateway-vps\",\"type\":${CTYPE_VPS},\"site\":${SITE_OVH_GRA},\"description\":\"Gateway benchmark VPS (Kong, Gravitee, webMethods)\"}")
CLUSTER_TOOLING=$(create_or_get "/virtualization/clusters/" "OVH Tooling" \
  "{\"name\":\"OVH Tooling\",\"slug\":\"ovh-tooling\",\"type\":${CTYPE_VPS},\"site\":${SITE_OVH_GRA},\"description\":\"n8n, Netbox, PocketBase, Healthchecks, Uptime Kuma\"}")
CLUSTER_INFRA=$(create_or_get "/virtualization/clusters/" "OVH Infra" \
  "{\"name\":\"OVH Infra\",\"slug\":\"ovh-infra\",\"type\":${CTYPE_VPS},\"site\":${SITE_OVH_GRA},\"description\":\"Infisical, Vault, monitoring\"}")
CLUSTER_MKS=$(create_or_get "/virtualization/clusters/" "OVH MKS GRA9" \
  "{\"name\":\"OVH MKS GRA9\",\"slug\":\"ovh-mks-gra9\",\"type\":${CTYPE_K8S},\"site\":${SITE_OVH_GRA},\"description\":\"Production Kubernetes — 3x B2-15 nodes\"}")

# ─── Roles ───────────────────────────────────────────────────────────────────
echo ""
echo "[4/6] Creating device roles..."
ROLE_WORKER=$(create_or_get "/dcim/device-roles/" "AI Worker" \
  '{"name":"AI Worker","slug":"ai-worker","color":"4caf50","vm_role":true,"description":"HEGEMON autonomous AI worker"}')
ROLE_GATEWAY=$(create_or_get "/dcim/device-roles/" "API Gateway" \
  '{"name":"API Gateway","slug":"api-gateway","color":"2196f3","vm_role":true,"description":"API gateway benchmark instance"}')
ROLE_TOOLING_R=$(create_or_get "/dcim/device-roles/" "Tooling" \
  '{"name":"Tooling","slug":"tooling","color":"ff9800","vm_role":true,"description":"DevOps tooling services"}')
ROLE_INFRA=$(create_or_get "/dcim/device-roles/" "Infrastructure" \
  '{"name":"Infrastructure","slug":"infrastructure","color":"607d8f","vm_role":true,"description":"Core infrastructure services"}')

# ─── Virtual Machines ────────────────────────────────────────────────────────
echo ""
echo "[5/6] Creating virtual machines..."

# HEGEMON workers (5x Contabo VPS L — 8 vCPU, 24 GB, 200 GB NVMe)
create_vm "hegemon-w1" "${CLUSTER_HEGEMON}" "${ROLE_WORKER}" 8 24576 200 "62.171.178.49"  "[{\"id\":${TAG_HEGEMON}},{\"id\":${TAG_PROD}}]" "Role: backend | SSH key: id_ed25519_stoa"
create_vm "hegemon-w2" "${CLUSTER_HEGEMON}" "${ROLE_WORKER}" 8 24576 200 "161.97.93.225"  "[{\"id\":${TAG_HEGEMON}},{\"id\":${TAG_PROD}}]" "Role: frontend | SSH key: id_ed25519_stoa"
create_vm "hegemon-w3" "${CLUSTER_HEGEMON}" "${ROLE_WORKER}" 8 24576 200 "167.86.75.214"  "[{\"id\":${TAG_HEGEMON}},{\"id\":${TAG_PROD}}]" "Role: mcp | SSH key: id_ed25519_stoa"
create_vm "hegemon-w4" "${CLUSTER_HEGEMON}" "${ROLE_WORKER}" 8 24576 200 "5.189.152.183"  "[{\"id\":${TAG_HEGEMON}},{\"id\":${TAG_PROD}}]" "Role: auth | SSH key: id_ed25519_stoa"
create_vm "hegemon-w5" "${CLUSTER_HEGEMON}" "${ROLE_WORKER}" 8 24576 200 "144.91.82.96"   "[{\"id\":${TAG_HEGEMON}},{\"id\":${TAG_PROD}}]" "Role: qa | SSH key: id_ed25519_stoa"

# Gateway VPS (OVH)
create_vm "kong-vps"       "${CLUSTER_GW_VPS}" "${ROLE_GATEWAY}" 2 4096  40 "51.83.45.13"    "[{\"id\":${TAG_GATEWAY}}]" "Kong DB-less | Admin :8001 | Proxy :8000"
create_vm "gravitee-vps"   "${CLUSTER_GW_VPS}" "${ROLE_GATEWAY}" 2 4096  40 "54.36.209.237"  "[{\"id\":${TAG_GATEWAY}}]" "Gravitee APIM v4 | Mgmt :8083 | GW :8082"
create_vm "webmethods-vps" "${CLUSTER_GW_VPS}" "${ROLE_GATEWAY}" 4 8192  80 "51.255.201.17"  "[{\"id\":${TAG_GATEWAY}}]" "webMethods API GW 10.15 | Admin :9072 | HTTP :5555"

# Tooling VPS (shared n8n host)
create_vm "n8n-tooling-vps" "${CLUSTER_TOOLING}" "${ROLE_TOOLING_R}" 4 8192 80 "51.254.139.205" "[{\"id\":${TAG_TOOLING}},{\"id\":${TAG_PROD}}]" "n8n + Netbox + PocketBase + Healthchecks + Uptime Kuma | Traefik reverse proxy"

# Infrastructure VPS
create_vm "infisical-vps" "${CLUSTER_INFRA}" "${ROLE_INFRA}" 2 4096 40 "213.199.45.108" "[{\"id\":${TAG_PROD}}]" "Infisical vault.gostoa.dev | Caddy TLS"
create_vm "spare-gra-vps" "${CLUSTER_INFRA}" "${ROLE_INFRA}" 2 4096 40 "51.255.193.129" "[{\"id\":${TAG_PROD}}]" "HashiCorp Vault hcvault.gostoa.dev | OVH GRA6"
create_vm "push-gra-vps"  "${CLUSTER_INFRA}" "${ROLE_INFRA}" 2 4096 40 "51.83.110.210"  "[{\"id\":${TAG_PROD}}]" "Pushgateway push.gostoa.dev | Prometheus metrics relay"

# ─── Cleanup obsolete entries ────────────────────────────────────────────────
echo ""
echo "[6/6] Checking for obsolete Hetzner entries..."

# Find and delete VMs with "hetzner" in name or from Hetzner sites
HETZNER_VMS=$(nb_api GET "/virtualization/virtual-machines/?q=hetzner" | jq -r '.results[].id // empty')
HETZNER_SITE_VMS=$(nb_api GET "/virtualization/virtual-machines/?q=staging" | jq -r '.results[] | select(.comments | test("hetzner|Hetzner"; "i")) | .id // empty' 2>/dev/null || true)

for vm_id in ${HETZNER_VMS} ${HETZNER_SITE_VMS}; do
  if [ -n "${vm_id}" ]; then
    vm_name=$(nb_api GET "/virtualization/virtual-machines/${vm_id}/" | jq -r '.name')
    echo "  [delete] Obsolete VM: ${vm_name} (ID: ${vm_id})"
    nb_api DELETE "/virtualization/virtual-machines/${vm_id}/" || true
  fi
done

# Delete Hetzner sites
HETZNER_SITES=$(nb_api GET "/dcim/sites/?q=hetzner" | jq -r '.results[].id // empty')
for site_id in ${HETZNER_SITES}; do
  if [ -n "${site_id}" ]; then
    site_name=$(nb_api GET "/dcim/sites/${site_id}/" | jq -r '.name')
    echo "  [delete] Obsolete site: ${site_name} (ID: ${site_id})"
    nb_api DELETE "/dcim/sites/${site_id}/" || true
  fi
done

echo "  Cleanup done."

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Inventory Population Complete ==="
echo ""
VM_COUNT=$(nb_api GET "/virtualization/virtual-machines/" | jq -r '.count')
SITE_COUNT=$(nb_api GET "/dcim/sites/" | jq -r '.count')
CLUSTER_COUNT=$(nb_api GET "/virtualization/clusters/" | jq -r '.count')
echo "  Sites:    ${SITE_COUNT}"
echo "  Clusters: ${CLUSTER_COUNT}"
echo "  VMs:      ${VM_COUNT}"
echo ""
echo "Verify: ${NETBOX_URL}/api/virtualization/virtual-machines/"
echo ""
