# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0

# .pre-commit-config.yaml snippet for license headers
#
# Add this to your existing .pre-commit-config.yaml:
#
# repos:
#   - repo: local
#     hooks:
#       - id: license-headers
#         name: Check license headers
#         entry: python scripts/add-license-headers.py --check
#         language: python
#         types: [file]
#         pass_filenames: false

# Alternative: GitHub Actions workflow
# 
# .github/workflows/license-check.yml:
#
# name: License Headers Check
# on: [push, pull_request]
# jobs:
#   check-headers:
#     runs-on: ubuntu-latest
#     steps:
#       - uses: actions/checkout@v4
#       - uses: actions/setup-python@v5
#         with:
#           python-version: '3.11'
#       - name: Check license headers
#         run: python scripts/add-license-headers.py --check src/
