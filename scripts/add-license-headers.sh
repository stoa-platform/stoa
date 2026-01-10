#!/bin/bash
# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0

# add-license-headers.sh - Wrapper script for license header tool
# 
# Usage:
#   ./add-license-headers.sh              # Add headers to all files
#   ./add-license-headers.sh --check      # Check mode (for CI)
#   ./add-license-headers.sh --dry-run    # Preview changes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default paths to process
PATHS="${@:-.}"

# Check if Python script exists
if [[ -f "$SCRIPT_DIR/add-license-headers.py" ]]; then
    python3 "$SCRIPT_DIR/add-license-headers.py" $PATHS
else
    echo "Error: add-license-headers.py not found in $SCRIPT_DIR"
    exit 1
fi
