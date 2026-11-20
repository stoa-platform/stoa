#!/usr/bin/env bash
set +x
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

export COMPOSE_FILE="$DIR/docker-compose.yml"
export COMPOSE_PROJECT_NAME="poc-roles-agents-floor-$(openssl rand -hex 6)"
export STOA_POC_BOOTSTRAP_SECRET="$(openssl rand -hex 24)"
export STOA_POC_UPSTREAM_API_KEY="floor-example-backend-marker"

runtime_root="$(mktemp -d /tmp/stoa-poc-floor.XXXXXXXX)"
runtime_root="$(cd "$runtime_root" && pwd -P)"
export STOA_POC_RUNTIME_DIR="$runtime_root/fixtures"

floor_file="/tmp/stoa-poc-floors/acme.floor.json"
role_file="$STOA_POC_RUNTIME_DIR/roles/acme.roles.jws"

cleanup() {
  local status=$?
  trap - EXIT
  if ! docker compose down -v --remove-orphans >/dev/null 2>&1; then
    echo "FAIL: could not clean up the floor test project" >&2
    status=1
  fi
  rm -rf -- "$runtime_root"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

select_role_policy() {
  cp "$runtime_root/acme.v$1.jws" "$role_file.next"
  chmod 0644 "$role_file.next"
  mv -f "$role_file.next" "$role_file"
}

assert_floor() {
  local version="$1"
  docker compose exec -T stoa-gateway cat "$floor_file" |
    python3 -c 'import json, sys; sys.exit(json.load(sys.stdin)["version"] != int(sys.argv[1]))' "$version"
  test "$(docker compose exec -T stoa-gateway stat -c '%a' "$floor_file")" = 600
}

volume_of() {
  docker inspect -f '{{range .Mounts}}{{if and (eq .Destination "/tmp/stoa-poc-floors") (eq .Type "volume")}}{{.Name}}{{end}}{{end}}' "$1"
}

expect_startup_refusal() {
  local container="$1" reason="$2" state attempt
  for attempt in $(seq 1 30); do
    state="$(docker inspect -f '{{.State.Status}}:{{.State.ExitCode}}' "$container")"
    case "$state" in
      exited:* | dead:*) break ;;
    esac
    sleep 1
  done

  if [[ "$state" != 'exited:1' ]] || ! docker logs "$container" 2>&1 | grep -F "$reason" >/dev/null; then
    printf 'FAIL: expected startup refusal (%s), got %s\n' "$reason" "$state" >&2
    return 1
  fi
}

echo "=== Building local images and generating signed role policy versions ==="
if ! docker compose build stoa-gateway upstream-mock >"$runtime_root/build.log" 2>&1; then
  tail -n 20 "$runtime_root/build.log" >&2
  exit 1
fi
python3 ./scripts/gen_fixtures.py "$STOA_POC_RUNTIME_DIR" --role-v2-out "$runtime_root/acme.v2.jws" >/dev/null
cp "$role_file" "$runtime_root/acme.v1.jws"

docker compose up -d --no-build --wait --wait-timeout 45 stoa-gateway >/dev/null 2>&1
assert_floor 1
echo "PASS: signed version 1 admitted on a fresh volume"

select_role_policy 2
docker compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 45 stoa-gateway >/dev/null 2>&1
assert_floor 2
before_id="$(docker compose ps -q stoa-gateway)"
before_volume="$(volume_of "$before_id")"
test -n "$before_volume"
echo "PASS: signed version 2 persisted with mode 0600"

docker compose kill -s SIGKILL stoa-gateway >/dev/null 2>&1
select_role_policy 1
docker compose up -d --no-deps --no-build --force-recreate stoa-gateway >/dev/null 2>&1
after_id="$(docker compose ps --all -q stoa-gateway)"
test -n "$after_id"
test "$after_id" != "$before_id"
test "$(volume_of "$after_id")" = "$before_volume"
expect_startup_refusal "$after_id" "role policy version rollback or conflicting content at same version"
echo "PASS: version 1 refused after SIGKILL and container recreation on the same volume"

select_role_policy 2
docker compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 45 stoa-gateway >/dev/null 2>&1
assert_floor 2
docker compose exec -T stoa-gateway chmod 000 "$floor_file"
docker compose up -d --no-deps --no-build --force-recreate stoa-gateway >/dev/null 2>&1
expect_startup_refusal "$(docker compose ps --all -q stoa-gateway)" "persisted anti-rollback floor is unreadable or corrupted"
echo "PASS: unreadable floor refused before readiness"

docker compose run --no-deps --rm -T --entrypoint /bin/chmod stoa-gateway 600 "$floor_file" >/dev/null 2>&1
docker compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 45 stoa-gateway >/dev/null 2>&1
assert_floor 2
test "$(volume_of "$(docker compose ps -q stoa-gateway)")" = "$before_volume"
echo "PASS: version 2 admitted again after restoring access"
