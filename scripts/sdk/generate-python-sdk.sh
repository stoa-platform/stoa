#!/usr/bin/env bash
# Generate a typed Python SDK from the STOA Control-Plane API OpenAPI spec.
#
# Usage:
#   ./scripts/sdk/generate-python-sdk.sh            # generate SDK
#   ./scripts/sdk/generate-python-sdk.sh --validate  # generate + import check
#
# Prerequisites:
#   pip install openapi-python-client ruff
#
# Output:
#   control-plane-api/sdk/python/stoa-platform-client/
#
# The generated SDK uses httpx (async) + pydantic v2 models.
# It is NOT committed to git — regenerate from openapi-snapshot.json as needed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SPEC_FILE="${REPO_ROOT}/control-plane-api/openapi-snapshot.json"
CONFIG_FILE="${REPO_ROOT}/scripts/sdk/config.yaml"
OUTPUT_DIR="${REPO_ROOT}/control-plane-api/sdk/python"
PACKAGE_DIR="${OUTPUT_DIR}/stoa-platform-client"

validate=false
if [[ "${1:-}" == "--validate" ]]; then
    validate=true
fi

# --- Preflight checks ---

if ! command -v openapi-python-client &>/dev/null; then
    echo "ERROR: openapi-python-client not found."
    echo "Install: pip install openapi-python-client"
    exit 1
fi

if [[ ! -f "$SPEC_FILE" ]]; then
    echo "ERROR: OpenAPI spec not found at ${SPEC_FILE}"
    echo "Run the FastAPI app to regenerate it, or check the path."
    exit 1
fi

# --- Generate ---

echo "==> Generating Python SDK from $(basename "$SPEC_FILE")..."
echo "    Spec: ${SPEC_FILE}"
echo "    Config: ${CONFIG_FILE}"
echo "    Output: ${OUTPUT_DIR}"

mkdir -p "$OUTPUT_DIR"

# Remove previous generation for idempotent output
if [[ -d "$PACKAGE_DIR" ]]; then
    echo "    Removing previous generation..."
    rm -rf "$PACKAGE_DIR"
fi

cd "$OUTPUT_DIR"

openapi-python-client generate \
    --path "$SPEC_FILE" \
    --config "$CONFIG_FILE" \
    2>&1 | tail -5

if [[ ! -d "$PACKAGE_DIR" ]]; then
    echo "ERROR: Generation failed — output directory not created."
    echo "Check the OpenAPI spec for compatibility issues."
    exit 1
fi

# Count generated files
model_count=$(find "$PACKAGE_DIR" -name "*.py" -path "*/models/*" | wc -l | tr -d ' ')
api_count=$(find "$PACKAGE_DIR" -name "*.py" -path "*/api/*" | wc -l | tr -d ' ')
echo "==> Generated: ${model_count} models, ${api_count} API modules"

# --- Validate (optional) ---

if $validate; then
    echo "==> Validating SDK import..."
    cd "$PACKAGE_DIR"

    # Install SDK deps in a temporary venv
    python3 -m venv /tmp/stoa-sdk-validate 2>/dev/null || true
    source /tmp/stoa-sdk-validate/bin/activate

    pip install -q -e . 2>&1 | tail -2

    python3 -c "
from stoa_platform_client import Client, AuthenticatedClient
print('  Client:', Client.__module__)
print('  AuthenticatedClient:', AuthenticatedClient.__module__)
print('  SDK import OK')
"
    validation_status=$?

    deactivate 2>/dev/null || true

    if [[ $validation_status -ne 0 ]]; then
        echo "ERROR: SDK import validation failed."
        exit 1
    fi
fi

echo "==> Done. SDK at: ${PACKAGE_DIR}"
