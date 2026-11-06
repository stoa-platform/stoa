# Reconcile publication safety

The local reconcile command ports the publication and drift safety rules from
console prototype into the current `stoa-go` command layout. It consumes a local
YAML or JSON governance snapshot and writes a separate private status file.
Fetching governance content and committing status to a remote are outside this
command. It never invokes Git or pushes status.

## Snapshot contract

The top-level `targets` array contains named targets. Each target requires
`adminURL`, `gatewayURL`, and `tokenEnv` (an environment variable name, never a
credential value). `contracts` contains native gateway UAC documents with
`name`, `tenant_id`, `version`, `status: published`, `classification`, and
`endpoints`. A stable, nonempty `description` is the ownership marker; changing
it requires explicit ownership migration. Only the supplied contracts are
probed or repaired. Removing one from the snapshot does not delete it.

Each target can declare `inboundAuth.audience`, `inboundAuth.realm`,
`inboundAuth.issuer`, `inboundAuth.jwksUri`, and `inboundAuth.discoveryURL`.
Issuer, JWKS and discovery values identify forbidden realm audiences; the
identity-provider configuration itself remains gateway-owned. The audience
may alternatively be present on each contract. A target-level audience takes
precedence. Empty, wildcard, `account` (case-insensitive), and configured realm
names are rejected. The default realm name is also excluded.

`options.allowUnauthenticatedREST: true` explicitly permits an open route only
for classification H. VH and VVH reject that option. Accepted anonymous access
is recorded as `protection: unprotected` and produces `result: degraded`.
The admin bearer is never sent with anonymous data-plane probes or redirected
requests. Error messages omit response bodies and configured addresses.

## Publication and rollback

Publication checks ownership before the POST. JWT publication sends
`inboundAuth: jwt` and `inboundAuthAudience` together in `POST /admin/contracts`.
There is no separate policies POST. Verification reads back ownership, version,
status, authentication mode and audience, then probes the route anonymously.
Only HTTP 401 or 403 proves anonymous access is denied.

A failure after a successful POST restores the previous complete live document,
including its original authentication fields and unknown extension fields.
An open or generic-audience predecessor cannot be restored without the H-only
opt-in: the newly published owned contract is removed and the refusal reported.
A foreign-owned live contract is never deleted or restored over. If ownership
cannot be read, rollback fails closed and reports the failure. Rollback has its
own bounded context so caller cancellation does not immediately abort cleanup.
A rejected POST relies on the gateway's existing binder transaction rollback.

## Drift and status

Every pass probes desired contracts. Repairs call `ForeignObjects` again before
publishing and report `drift collision` on foreign ownership. A probe error
prevents writes for that pass. The sorted missing set, desired-content digest
and target-configuration digest make failed or unresolved repairs sticky across
process restarts. An unchanged failure does not cause repeated publication or
status writes. A changed set, content or target configuration retries repair.

Status is atomically replaced with permissions `0600`. It contains digests,
missing identities, per-target errors and protection state, never credentials.
`--once` returns an error for `failed` and `drift-unresolved`; `ok` and explicitly
accepted `degraded` return success. Continuous mode remains cancellable.

## Gateway compatibility

The gateway accepts both camelCase publication fields and snake_case read-back
fields. Its binder records the audience alongside the JWT policy, and the REST
proxy validates signed tokens against the contract's audience. This uses the
existing JWT validator and leaves binder rollback unchanged. Older gateways
that ignore the audience fail the adapter's read-back verification and trigger
rollback; they cannot silently appear protected.
