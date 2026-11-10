#!/usr/bin/env bash
# Messaging HA failover proof (local, Docker Compose only).
#
# Starts the three-broker Redpanda cluster of docker-compose.yml (retained sizing:
# 3 brokers, replication factor 3, acks=all), then proves that losing one broker
# leaves messaging available:
#   1. baseline   - topic RF=3 created, records produced with acks=all and read back
#   2. failure    - the broker leading partition 0 is stopped; the cluster reports it down
#   3. failover   - every partition elects a leader among the survivors
#   4. available  - new acks=all writes succeed and every acknowledged record is readable
#   5. recovery   - the stopped broker rejoins and the cluster reports healthy again
#
# Never talks to a remote cluster: every rpk call runs inside the local containers.
# Usage: deploy/redpanda/ha-proof/failover-proof.sh
#   MESSAGING_HA_TIMEOUT  seconds allowed per wait step (default 120)
#   MESSAGING_HA_RECORDS  records produced per phase (default 50)
#   MESSAGING_HA_KEEP=1   keep the containers after the run (debugging)
set -euo pipefail

PROOF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$PROOF_DIR/docker-compose.yml"
BROKERS=(redpanda-0 redpanda-1 redpanda-2)
BROKER_COUNT=3
REPLICATION_FACTOR=3
# Redpanda acknowledges acks=all once a Raft majority holds the record: with RF=3
# that is 2 replicas, the min.insync.replicas=2 of docs/runbooks/kafka-topics.md.
MIN_INSYNC_REPLICAS=2
PARTITIONS=3
TOPIC="stoa.ha.failover-proof"
TIMEOUT="${MESSAGING_HA_TIMEOUT:-120}"
RECORDS="${MESSAGING_HA_RECORDS:-50}"

# --- pure helpers (unit-tested by test_failover_proof.py) -------------------

# Replicas needed to acknowledge a write in a Raft group of $1 replicas.
majority() { echo $(($1 / 2 + 1)); }

# Replicas that can be lost while writes stay acknowledged.
tolerated_failures() { echo $(($1 - $(majority "$1"))); }

# stdin: `rpk cluster info`; prints the host advertised by node id $1.
broker_host() {
  awk -v id="$1" '$1 ~ /^[0-9]+\*?$/ && NF >= 3 { node = $1; sub(/\*$/, "", node); if (node == id) { print $2; exit } }'
}

# stdin: `rpk topic describe -p`; prints "<partition> <leader>" per partition.
partition_leaders() {
  awk '$1 ~ /^[0-9]+$/ && $2 ~ /^-?[0-9]+$/ { print $1, $2 }'
}

# stdin: `rpk cluster health`; prints the down node ids, space separated.
nodes_down() {
  sed -n 's/^Nodes down:[[:space:]]*\[\(.*\)\][[:space:]]*$/\1/p'
}

# stdin: `rpk cluster health`; prints the number of nodes known to the cluster.
node_count() {
  sed -n 's/^All nodes:[[:space:]]*\[\(.*\)\][[:space:]]*$/\1/p' | wc -w | tr -d ' '
}

# stdin: `rpk cluster health`; succeeds when the cluster reports itself healthy.
is_healthy() {
  grep -Eq '^Healthy:[[:space:]]+true[[:space:]]*$'
}

# --- docker helpers ---------------------------------------------------------

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# rpk inside broker $1, bootstrapped on that broker only (it is known to be up).
rpk_on() {
  local broker="$1"
  shift
  timeout "$TIMEOUT" docker compose -f "$COMPOSE_FILE" exec -T "$broker" \
    rpk "$@" -X "brokers=$broker:9092" -X "admin.hosts=$broker:9644"
}

log() { printf '[ha-proof] %s\n' "$*"; }
pass() { printf '[ha-proof] PASS %s\n' "$*"; }
fail() {
  printf '[ha-proof] FAIL %s\n' "$*" >&2
  exit 1
}

# Retry "$@" every 2 s until it succeeds or TIMEOUT elapses.
wait_for() {
  local what="$1" deadline=$((SECONDS + TIMEOUT))
  shift
  until "$@"; do
    ((SECONDS < deadline)) || fail "timed out after ${TIMEOUT}s waiting for: $what"
    sleep 2
  done
}

cluster_healthy_with_all_nodes() {
  local health
  health="$(rpk_on "$1" cluster health 2>/dev/null)" || return 1
  is_healthy <<<"$health" && [[ "$(node_count <<<"$health")" == "$BROKER_COUNT" ]]
}

node_reported_down() {
  local health
  health="$(rpk_on "$1" cluster health 2>/dev/null)" || return 1
  [[ " $(nodes_down <<<"$health") " == *" $2 "* ]]
}

# Every partition of TOPIC has a leader other than node $2, as seen from broker $1.
leaders_avoid_node() {
  local described leaders
  described="$(rpk_on "$1" topic describe "$TOPIC" -p 2>/dev/null)" || return 1
  leaders="$(partition_leaders <<<"$described")"
  [[ "$(wc -l <<<"$leaders" | tr -d ' ')" == "$PARTITIONS" ]] || return 1
  ! awk -v down="$2" '$2 == -1 || $2 == down { found = 1 } END { exit !found }' <<<"$leaders"
}

# Produce RECORDS records "<phase>-<n>" with acks=all through broker $1.
produce_phase() {
  local broker="$1" phase="$2" out acked
  out="$(seq 1 "$RECORDS" | sed "s/^/$phase-/" |
    rpk_on "$broker" topic produce "$TOPIC" --acks=-1)" || fail "$phase: produce through $broker exited non-zero"
  acked="$(grep -c '^Produced to partition' <<<"$out" || true)"
  [[ "$acked" == "$RECORDS" ]] || fail "$phase: $acked/$RECORDS records acknowledged with acks=all"
  pass "$phase: $RECORDS/$RECORDS records acknowledged with acks=all through $broker"
}

# Read the whole topic through broker $1 and compare with the phases produced so far.
assert_all_records() {
  local broker="$1" expected got
  shift
  expected="$(for phase in "$@"; do seq 1 "$RECORDS" | sed "s/^/$phase-/"; done | sort)"
  got="$(rpk_on "$broker" topic consume "$TOPIC" --offset start \
    --num "$(($# * RECORDS))" --format '%v\n' | sort)" || fail "consume through $broker failed"
  [[ "$got" == "$expected" ]] || fail "records read through $broker differ from records acknowledged ($*)"
  pass "all $(($# * RECORDS)) acknowledged records readable through $broker (phases: $*)"
}

cleanup() {
  if [[ "${MESSAGING_HA_KEEP:-0}" == "1" ]]; then
    log "MESSAGING_HA_KEEP=1: containers left running (compose -f $COMPOSE_FILE down -v)"
  else
    compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}

main() {
  local tolerated
  tolerated="$(tolerated_failures "$REPLICATION_FACTOR")"
  [[ "$(majority "$REPLICATION_FACTOR")" == "$MIN_INSYNC_REPLICAS" ]] ||
    fail "acks=all majority of RF=$REPLICATION_FACTOR is not min.insync.replicas=$MIN_INSYNC_REPLICAS"
  ((tolerated >= 1)) || fail "RF=$REPLICATION_FACTOR tolerates no broker loss"
  log "sizing: $BROKER_COUNT brokers, RF=$REPLICATION_FACTOR, acks=all needs $MIN_INSYNC_REPLICAS, tolerates $tolerated loss"

  trap cleanup EXIT
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  compose up -d --quiet-pull

  # 1. baseline
  wait_for "$BROKER_COUNT healthy brokers" cluster_healthy_with_all_nodes redpanda-0
  pass "baseline: cluster healthy with $BROKER_COUNT brokers"
  rpk_on redpanda-0 topic create "$TOPIC" -p "$PARTITIONS" -r "$REPLICATION_FACTOR" >/dev/null
  wait_for "leaders on $TOPIC" leaders_avoid_node redpanda-0 -1
  produce_phase redpanda-0 before
  assert_all_records redpanda-0 before

  # 2. failure: stop the broker leading partition 0, forcing a leader election
  local leader victim survivor
  leader="$(rpk_on redpanda-0 topic describe "$TOPIC" -p | partition_leaders | awk '$1 == 0 { print $2 }')"
  victim="$(rpk_on redpanda-0 cluster info | broker_host "$leader")"
  [[ " ${BROKERS[*]} " == *" $victim "* ]] || fail "leader $leader of partition 0 maps to unknown host '$victim'"
  for survivor in "${BROKERS[@]}"; do [[ "$survivor" != "$victim" ]] && break; done
  log "stopping $victim (node $leader, leader of partition 0); observing from $survivor"
  compose stop "$victim" >/dev/null
  wait_for "node $leader reported down" node_reported_down "$survivor" "$leader"
  pass "failure: cluster reports node $leader ($victim) down"

  # 3. failover
  wait_for "leaders off node $leader" leaders_avoid_node "$survivor" "$leader"
  pass "failover: all $PARTITIONS partitions led by surviving brokers"

  # 4. availability with one broker lost
  produce_phase "$survivor" during
  assert_all_records "$survivor" before during

  # 5. recovery
  compose start "$victim" >/dev/null
  wait_for "$victim to rejoin" cluster_healthy_with_all_nodes "$survivor"
  pass "recovery: $victim rejoined, cluster healthy with $BROKER_COUNT brokers"
  assert_all_records "$victim" before during

  log "RESULT: PASS - losing 1 of $BROKER_COUNT brokers kept messaging available with no acknowledged record lost"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
