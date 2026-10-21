#!/usr/bin/env bash
# Proves the Perl fallback kills a TERM-ignoring child at VERIFY_TIMEOUT.
# GNU timeout and gtimeout are absent from PATH. SPDX-License-Identifier: Apache-2.0
set -euo pipefail

cd "$(dirname "$0")"

bin="$(mktemp -d)"
trap 'rm -rf "$bin"' EXIT
for cmd in bash perl dirname; do
  ln -s "$(command -v "$cmd")" "$bin/$cmd"
done
if PATH="$bin" command -v timeout >/dev/null 2>&1 || PATH="$bin" command -v gtimeout >/dev/null 2>&1; then
  echo "bound-test: timeout is still visible" >&2
  exit 1
fi

start="$(PATH="$bin" perl -MTime::HiRes=time -e 'printf "%.3f\n", time')"
set +e
PATH="$bin" VERIFY_TIMEOUT=1 VERIFY_BOUND_FIXTURE=1 ./verify.sh >/dev/null
status=$?
set -e
elapsed="$(PATH="$bin" perl -MTime::HiRes=time -e 'printf "%.3f\n", time - $ARGV[0]' "$start")"

if [[ "$status" -ne 124 ]]; then
  echo "bound-test: expected exit 124, got $status (elapsed ${elapsed}s)" >&2
  exit 1
fi
if ! PATH="$bin" perl -e 'exit($ARGV[0] < 2.5 ? 0 : 1)' "$elapsed"; then
  echo "bound-test: elapsed ${elapsed}s, bound was 1s" >&2
  exit 1
fi
echo "bound-test: exit 124 in ${elapsed}s"
