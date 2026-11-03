# Tenant claim mapper (CAB-2262, lot 1)

`deploy/keycloak/tenant-id-mapper.json` is the reviewed OIDC mapper payload for
`control-plane-ui`, `stoa-portal` and `control-plane-api`: `tenant_id` as a scalar string
in access tokens, ID tokens and userinfo. No value means no claim, not a rejected login.

Known limitation: Keycloak's standard `UserAttributeMapper` can inherit `tenant_id`
from a group when the user has no direct value. That is not an authorized assignment;
the static tests and the check below reject it, the mapper does not. A custom mapper is a follow-up.

## Read-only pre-apply check for an existing realm

Use an already configured admin client with visibility over every realm group.
Send GET requests only; never log raw responses, tokens or attribute values.

1. Enumerate `groups?first=0&max=100`, then `groups/{id}/children?first=0&max=100`
   recursively for every discovered group, paging by increasing `first` until an
   empty array is returned; do not rely on embedded `subGroups`. Fetch `groups/{id}`
   for every ID: no `attributes` object may hold the key `tenant_id`, even empty.
2. Read `users/profile`: exactly one `tenant_id` declaration, `multivalued: false`,
   `permissions.view` and `permissions.edit` both equal to `["admin"]`.
3. In the same profile, `unmanagedAttributePolicy` must be unset, `ADMIN_VIEW` or
   `ADMIN_EDIT`; `ENABLED` allows user editing and blocks apply.

Stop if any check fails or group visibility is incomplete. Have an authorized
operator reconcile the realm, then repeat the check before applying.

## Reconciliation limits for existing realms and clients

Fresh Compose realms and Helm bootstraps carry the mapper and profile; the bootstrap skips
existing clients, and a chart update or restart alone changes no existing realm. After the
check passes, update the existing tenant mapper on each client (or its default scope) from
the JSON payload instead of adding a second `tenant_id` writer. Preserve other mappers, client
settings and user attributes, never overwrite the realm, and keep groups free of `tenant_id`.
Offline check: `python3 -B -m unittest discover -s scripts/security -p test_regression_cab_2262_tenant_claim.py`
