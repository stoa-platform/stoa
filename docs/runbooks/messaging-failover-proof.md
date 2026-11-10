# Messaging HA Failover Proof

> Reproducible proof that the retained messaging sizing survives the loss of one broker.
> Local only: Docker Compose on a workstation or a CI runner, never a live cluster.

## Retained sizing

| Setting | Value | Source |
|---------|-------|--------|
| Brokers | 3 | `deploy/redpanda/values.yaml` (production note: `statefulset.replicas: 3`) |
| Replication factor | 3 | [kafka-topics.md](kafka-topics.md) "Key Configuration", [event-backbone-ops.md](event-backbone-ops.md) |
| Replicas acknowledging a write | 2 | `min.insync.replicas: 2` in the same runbooks |

Redpanda acknowledges an `acks=all` write once a Raft majority of the partition's
replicas holds it. With replication factor 3 that majority is 2, which is the
`min.insync.replicas=2` guarantee of the runbooks. The sizing therefore tolerates
the loss of exactly one broker.

## What the proof does

`deploy/redpanda/ha-proof/failover-proof.sh` starts the three-broker cluster of
`deploy/redpanda/ha-proof/docker-compose.yml` (same Redpanda release as
`k8s/redpanda/statefulset.yaml`, pinned by digest) and runs five phases. Each phase
prints `PASS` or stops the run with `FAIL`:

1. **Baseline**: the cluster reports 3 healthy brokers. A topic with 3 partitions
   and replication factor 3 is created. Records are produced with `acks=all` and
   read back.
2. **Failure**: the broker leading partition 0 is stopped. The surviving brokers
   report it down.
3. **Failover**: every partition elects a leader among the two survivors.
4. **Availability**: new `acks=all` writes through a survivor are all
   acknowledged. Every record acknowledged before and during the outage is
   readable.
5. **Recovery**: the stopped broker restarts and rejoins. The cluster reports
   3 healthy brokers again, and the restarted broker serves every record.

The run ends with `RESULT: PASS` and tears the containers down.

## Running it

```bash
# Static checks (no Docker): sizing consistency, compose topology, script parsers
python3 -m pip install --require-hashes -r .github/workflows/requirements/pyyaml.txt
python3 -B -m unittest discover -s deploy/redpanda/ha-proof -p 'test_*.py' -v

# Live failover proof (needs a Docker daemon; about 1.5 GiB of memory for 3 brokers)
deploy/redpanda/ha-proof/failover-proof.sh
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `MESSAGING_HA_TIMEOUT` | `120` | Seconds allowed for each wait step |
| `MESSAGING_HA_RECORDS` | `50` | Records produced in each phase |
| `MESSAGING_HA_KEEP` | `0` | `1` keeps the containers for inspection |

CI: `.github/workflows/messaging-ha-proof.yml` runs both levels on pull requests
that touch messaging deployment files or these runbooks, and on manual dispatch.
It is not a required check.

## Scope and remaining gaps

The proof shows that the **retained sizing** keeps messaging available when one
broker is lost. It does not change any deployment. These deployment artifacts
still describe a single broker and do not have this property yet:

| Artifact | Current shape |
|----------|---------------|
| `k8s/redpanda/statefulset.yaml` | `replicas: 1`, `default_topic_replications: 1`, one advertised address for all pods, no PodDisruptionBudget |
| `deploy/redpanda/values.yaml` | `statefulset.replicas: 1` (dev profile; 3 brokers noted for production) |
| `deploy/docker-compose/docker-compose.yml` | one broker for local development |

When a deployment is moved to the retained sizing, run this proof again to check it
uses the same release, and create topics with replication factor 3 as described in
[kafka-topics.md](kafka-topics.md).
