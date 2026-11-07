# Site Backup, Restore and Verification

## Scope and recovery contract

For operators recovering their own site. All commands below are **operator-run
examples**, not evidence of a tested restore. Run from the repository root at the
recorded release. Variables denote site-selected resources or protected local
backup files; no access information belongs in this document or incident reports.

The [admin installation guide](../admin/installation.md) establishes the boundary:
`charts/stoa-platform/` installs the Rust gateway and supporting resources, not
PostgreSQL, Keycloak, the Control Plane API or storage services. A successful Helm
install alone cannot recover a platform. For a gateway-only site, mark externally
owned services below as external and obtain recovery evidence from their owners.

Before backup, the site recovery owner must record:

- Recovery point objective (RPO), recovery time objective (RTO), retention and
  drill frequency; these are site decisions, not guarantees provided by this repo.
- Release commit, image digests, chart version, component/database versions,
  enabled features and the owners of each dependency.
- A common recovery checkpoint: pause configuration changes and writes using the
  site's maintenance procedure, then record backup start/end times and any skew.
  There is no cross-service consistent snapshot or write-quiescence tool here.
- An encrypted, independently stored backup set and a restricted manifest of
  timestamps, format, sizes, integrity evidence and expected object/record counts.
  Record verification results, never secret values or real resource addresses.

## What must be backed up

| Asset | Required recovery content | Repository basis and limits |
|-------|---------------------------|-----------------------------|
| Control Plane database | Schema and data: tenants, APIs, subscriptions, policies and other release-specific tables; separately preserve roles/grants | [PostgreSQL script](../../scripts/backup/backup-postgres.sh) produces plain SQL plus gzip with no owner/grants; [admin guide](../admin/backup-restore.md) also describes custom-format dumps. Formats are not interchangeable. |
| Identity database | Complete Keycloak database, realm configuration, users, credentials, clients and signing-key provider dependencies | [Legacy realm procedure](../admin/backup-restore.md#keycloak-backup) supplies export/import examples, not a complete identity recovery guarantee. Use a database-consistent backup and the site's Keycloak procedure; partial realm export is insufficient. |
| Configuration | Reviewed Helm values without secret values, release/image pins, policy files, GitOps revisions, custom resource instances and external service configuration | [Chart](../../charts/stoa-platform/), [installation guide](../installation.md) and [policy template](../../charts/stoa-platform/templates/stoa-gateway-policy-configmap.yaml). CRD definitions alone do not back up custom resource instances. No complete configuration exporter exists here. |
| Gateway state | Authoritative API/tool registrations, routes, policies, bindings, trust configuration and every configured local persistence store | [Gateway state](../../stoa-gateway/src/state.rs) and [deployment template](../../charts/stoa-platform/templates/stoa-gateway-deployment.yaml). Inventory the enabled features; the chart provides no general gateway snapshot/restore command. Rebuild caches from their authoritative source; do not promise preservation of sessions, counters or in-flight work. |
| Object storage | Specifications, artifacts, bucket metadata/access policy and versions required at the checkpoint | [Object-store procedure](../admin/backup-restore.md#minio--s3-backup) describes mirrors. A mirror alone does not establish recovery of versions, retention settings or access policy. |
| Secrets and trust | Secret-store data plus its database/configuration, encryption dependencies, certificates, private signing keys and public trust material | [Secrets management status](README.md#secrets-management), [API configuration](../../control-plane-api/src/config.py) and [gateway configuration](../../stoa-gateway/src/config.rs). See the key custody requirement below. |
| Optional dependencies | Event logs/offsets, audit evidence, search indexes that cannot be rebuilt, automation state, dashboards and alert configuration | [Event backbone operations](event-backbone-ops.md), [AWX script](../../scripts/backup/backup-awx.sh). Owners must classify rebuildable data and supply service-specific backups; no unified restore exists. |

The gateway also has a durable audit write-ahead log (WAL), configured in
[gateway configuration](../../stoa-gateway/src/config.rs) and recovered by
[the audit spool](../../stoa-gateway/src/audit/spool.rs). Preserve the complete
spool, including acknowledgement records, at a quiesced checkpoint using the
site storage procedure. The chart does not provide a dedicated persistent volume
for it. Do not treat its temporary volume as a backup or replay only selected
segments; reconcile pending events and duplicates with the audit sink on restore.

### Root and signing keys: mandatory offline custody

Conceptually, root/seal/recovery keys belong to the site's secret-management or
key-management trust boundary. Private signing keys belong to the identity
provider, Control Plane policy signer, gateway service identity or site PKI,
depending on the enabled feature. Runtime mounts and database snapshots are not
an independent key escrow. Public verification keys alone cannot restore signing.

The Control Plane's policy signer loads private key material from a configured
file ([signer](../../control-plane-api/src/services/policy_artifact_signer.py));
the gateway separately loads a client assertion private key and pinned policy
verification keys ([configuration](../../stoa-gateway/src/config.rs)). Preserve
key identifiers, algorithms, certificate chains and matching public trust pins
alongside the protected private material. Recovering only one side breaks trust.

**Root/recovery material and signing keys must be backed up offline**, encrypted
and separate from service backups. The site's security owner must designate
named human key custodians in a restricted local custody register; record only
roles here. Use independent custodians and dual control for recovery. The
platform operator holds the service backup; security custodians hold the offline
key escrow and the means to unlock it. Neither this repository nor this runbook
asserts who currently holds any site's keys.

For non-exportable HSM/KMS keys, custodians must maintain and test the provider's
supported offline recovery/escrow arrangement. If this cannot recover the needed
key, record an unmet recovery requirement; do not claim full restore coverage.
A root login token is not a seal/recovery key. Never regenerate, rotate, print or
commit keys as part of this procedure. No offline key escrow or custody tooling
is supplied by this repository.

## Backup procedure

1. Assign a recovery owner and key custodians; complete the inventory above.
   Confirm that backups can be decrypted independently of the failed site.
2. Capture configuration and the checkpoint manifest with the site's approved
   export mechanism. Do not dump Secret objects into a public archive or report.
3. Back up each database using the correct service/version procedure. For the
   Control Plane database, the following plain SQL example is adapted from
   `perform_backup` in [backup-postgres.sh](../../scripts/backup/backup-postgres.sh).
   Set the variables locally; `$BACKUP_FILE` must be a protected new output file.

   ```bash
   set -o pipefail
   kubectl exec -n "$PG_NAMESPACE" "$PG_POD_NAME" -- \
     pg_dump -U "$PG_USER" -d "$PG_DATABASE" \
     --no-owner --no-privileges --format=plain | gzip > "$BACKUP_FILE"
   gunzip -t "$BACKUP_FILE"
   ```

   Require success from the dump, compression and integrity check, plus nonzero
   size. Arrange encryption and off-site/offline copying through the site backup
   system before accepting the backup. This example does not implement either.
   The script's automated path requires AWS tooling and also prunes old backups
   and can send notifications; it is not a side-effect-free backup validator.
4. Capture identity, object storage and optional dependencies at the agreed
   checkpoint. Preserve roles/grants separately because the example omits them.
5. Custodians confirm offline key coverage without exposing material. Verify an
   independent copy is readable/decryptable and record the next restore drill.

## Restore procedure

1. Declare the recovery point, expected loss since that point and recovery owner.
   Keep traffic and writes disabled. Preserve the current state separately when
   available. Use an isolated recovery target first; never overwrite the sole
   surviving copy. If any required dependency or key is missing, stop acceptance.
2. Have custodians recover the secret/key-management trust boundary and verify
   decryption and key identity. [The runbook index](README.md#secrets-management)
   identifies OpenBao (ADR-075) as the platform team's secret manager, while
   [backup-vault.sh](../../scripts/backup/backup-vault.sh) targets HashiCorp Vault
   Raft. That script is **not a reviewed OpenBao restore procedure**. It uses forced
   snapshot restore and may continue after inconclusive inspection. Sites still
   using Vault must supply a reviewed provider-specific procedure, including
   seal/recovery dependencies; other backends need their own procedure.
3. Provision compatible database/storage dependencies using the site procedure.
   Restore the identity database and its signing-provider dependencies before
   enabling authentication. Do not run a realm bootstrap or demo/seed procedure.
4. Restore the Control Plane database into a fresh isolated database. For a
   **custom-format** dump made using the [admin guide](../admin/backup-restore.md),
   these commands are the guide's fresh-database variant, parameterized for the
   site's libpq connection configuration. `$RESTORE_DATABASE` must be a new name.

   ```bash
   createdb -U "$PG_USER" "$RESTORE_DATABASE"
   pg_restore -U "$PG_USER" -d "$RESTORE_DATABASE" "$CUSTOM_DUMP_FILE"
   ```

   Never feed `.sql.gz` to `pg_restore`. The PostgreSQL script's `--restore`
   handles its own plain SQL format but drops/recreates the selected database,
   suppresses a drop error and does not enable SQL stop-on-error. Its exit status
   and table count are insufficient proof of success. A reviewed, fail-fast
   plain SQL import into an isolated target remains a tooling gap; do not run the
   destructive wrapper blindly. Resolve all import errors and restore required
   roles/grants before proceeding.
5. Restore object data and service metadata using the site storage procedure.
   Restore the recorded Control Plane release against the recovered database.
   Review migration compatibility before applying any migration; the
   [admin guide](../admin/backup-restore.md#post-restore) documents Alembic, but
   automatically migrating to a newer head invalidates same-release recovery.
6. Restore reviewed values, policies, custom resource instances and trust mounts.
   With external services recovered, reinstall the recorded gateway release.
   This parameterized command comes from [installation](../installation.md#install-with-helm):

   ```bash
   helm upgrade --install "$RELEASE" ./charts/stoa-platform \
     -n "$NAMESPACE" --create-namespace -f "$VALUES_FILE"
   ```

   Use the recorded chart checkout and image digests; review existing CRDs
   separately, because Helm does not upgrade them. Reconcile gateway registrations
   from the authoritative configuration. There is no universal command here to
   restore local state or replay all gateway/event work exactly once.

## Verification and return to service

The recovery owner records pass/fail evidence for **every applicable row**. A
missing check is a failed acceptance gate, even if pods are healthy.

| Check | Acceptance evidence |
|-------|---------------------|
| Backup integrity | Correct checkpoint, format, decryption, readable independent copy and successful database import with no unresolved errors. |
| Database fidelity | Schema/migration revision and site baseline counts agree; representative tenant/API/subscription relationships and grants are intact. Do not rely on legacy fixed table counts. |
| Identity and keys | Existing authorized user can authenticate; recovered signer verifies against the expected public key identifier; old valid trust chains still work. Custodians attest offline recovery without disclosing keys. |
| Gateway | Deployment ready; `/health` and `/ready` pass as defined by the [deployment probes](../../charts/stoa-platform/templates/stoa-gateway-deployment.yaml). Readiness alone does not prove data recovery. |
| Functional access | A pre-existing authorized identity can invoke a known restored API/tool; unauthorized and cross-tenant attempts are denied; policy signatures and bindings are enforced. Use site-owned test fixtures, not seed scripts. |
| Dependencies | Required object versions readable; audit/event continuity and offsets reconciled; caches warmed; any lost sessions/counters or unreplayable work explicitly accounted for. |
| Operational recovery | Measured recovery duration and actual recovery point satisfy the site's RTO/RPO; monitoring and the next backup are operational. |

For deployment readiness, this command is parameterized from the
[installation verification](../installation.md#verify-the-gateway):

```bash
kubectl rollout status deployment/stoa-gateway -n "$NAMESPACE"
```

The repository has no end-to-end restore acceptance harness. Perform the
functional checks through the site's approved interfaces and retain redacted
results. Resume writes/traffic only after the recovery owner and security owner
accept the evidence. On failure, keep isolation, preserve evidence and recover
again from the independent checkpoint; do not rotate keys or apply an improvised
database swap. Record gaps, actual loss and follow-up owners after each drill.
