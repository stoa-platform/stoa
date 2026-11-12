# Identity service HA proof (CAB-2555)

Static check of the Keycloak sizing this repository actually contains.
`failover-proof.sh` prints the bascule and refuses to run it. It does not
call kubectl, Helm, or Docker, and it is not pointed at a cluster.

```bash
python3 -B deploy/keycloak/ha-proof/verify_static.py
python3 -B -m unittest discover -s deploy/keycloak/ha-proof -p 'test_*.py' -v
bash deploy/keycloak/ha-proof/failover-proof.sh --plan
```

## Proven statically

- Production reference count is `keycloak.replicas: 3` (`values-prod.yaml`),
  staging `2`, dev `1`. The base `values.yaml` sets no replica count.
- Those counts are marked REFERENCE ONLY. Clustering (JGroups DNS_PING) is
  claimed in `stoa-infra` `charts/keycloak/`, which is not in this repo.
- No Deployment or StatefulSet for Keycloak is rendered here, so there is no
  in-repo pod anti-affinity, Keycloak PodDisruptionBudget, or Kubernetes
  readiness/liveness pair. The PDB in `values-prod.yaml` selects the gateway.
- The runnable definitions are single replica: `deploy/docker-compose`
  (`KC_CACHE=ispn`, no `KC_CACHE_STACK`, `container_name` blocks scale) and
  `quickstart` (`start-dev`, no cache). Infinispan on one process is not a
  shared session cache. One loss is not tolerable (`tolerated_losses=0`).

The unit tests lock this verdict (`HA_STATIC=fail`). They do not claim the
service is highly available.

## Not proven (needs a live run)

- That the `stoa-infra` chart really runs more than one Keycloak, with
  anti-affinity, a PDB, probes, and jdbc-ping or DNS_PING.
- That an existing session and a new token still succeed after one replica
  is stopped, then recover when it returns.

`--execute` exits 3 on purpose. Do not add a cluster target to this script
to make that exit go away. Change the sizing only in the chart that owns
Keycloak, then update the expected gaps in `test_ha_proof.py`.
