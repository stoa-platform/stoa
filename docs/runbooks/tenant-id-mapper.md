# Tenant claim mapper (CAB-2262, lot 1)

`deploy/keycloak/tenant-id-mapper.json` is the reviewed OIDC mapper payload for
`control-plane-ui`, `stoa-portal` and `control-plane-api` in the shared realm.
It maps the effective `tenant_id` attribute as a scalar string to access tokens,
ID tokens and userinfo, without a hardcoded tenant value. The API client remains
bearer-only in Helm; that client does not itself issue tokens.

Keycloak 26.5.3's standard `UserAttributeMapper` can inherit `tenant_id` from a
group when the user has no direct value. Such inheritance is **not an authorized
tenant assignment**. Static guards and the pre-apply check below prohibit
`tenant_id` on groups, including subgroups; the mapper does not enforce this.
A custom mapper is a follow-up and is not included in this PR. When neither a
direct nor an inherited value exists, the claim is omitted. The mapper does not
reject login or token issuance: denial of tenant-scoped requests without the
claim belongs to lot 2. Do not assign a default tenant to make requests succeed.

## Read-only pre-apply check for an existing realm

Use an already configured admin client with visibility over every realm group.
Perform only GET requests; do not change credentials or log raw responses,
tokens, group names or attribute values. With `kcadm.sh`, use `get` with the
relative endpoint below and `-r "$REALM"`; query parameters use `-q key=value`.

1. Enumerate `groups?first=0&max=100`, then recursively enumerate
   `groups/{id}/children?first=0&max=100` for every discovered group. Page each
   endpoint by increasing `first` until it returns an empty array; do not rely
   on embedded `subGroups`, which may be absent or incomplete. Fetch
   `groups/{id}` for every discovered ID and list only the IDs whose
   `attributes` object contains the key `tenant_id`, even if its value is empty.
   The resulting list **must be empty**.
2. Read `users/profile`. Require exactly one `tenant_id` declaration with
   `permissions.view` and `permissions.edit` both equal to `["admin"]`, and
   `multivalued: false`. Keep the separate `tenant` attribute unchanged.
3. In the same profile, require `unmanagedAttributePolicy` to be unset/disabled,
   `ADMIN_VIEW` or `ADMIN_EDIT`. `ENABLED` allows user editing and blocks apply.

Stop before applying if any check fails or visibility is incomplete. Have an
authorized operator reconcile the configuration, then repeat the read-only
check. The [Keycloak group API](https://github.com/keycloak/keycloak/blob/26.5.3/services/src/main/java/org/keycloak/services/resources/admin/GroupResource.java)
defines the paginated children endpoint; [profile policy values](https://github.com/keycloak/keycloak/blob/26.5.3/core/src/main/java/org/keycloak/representations/userprofile/config/UPConfig.java)
distinguish administrator-only unmanaged attributes from `ENABLED`.

## Application after Christophe's approval

- Fresh Compose realm: the existing `stoa-identity` default client scope already
  carries this mapper for all three clients in
  `deploy/docker-compose/init/keycloak-realm.json`. Its exported
  `UserProfileProvider` component declares `tenant_id` as single-valued and
  administrator-only.
- Fresh Helm installation with bootstrap enabled: the bootstrap creates the
  realm and built-in profile component in one request, then creates the mapper
  directly on all three clients. It skips existing clients and does not run
  when the Keycloak Operator manages the realm.
- Existing realm: after the pre-apply check, an authorized operator must
  reconcile only this mapper on each client (or its existing default client
  scope), using the JSON payload. Inspect effective direct and default-scope
  mappers first; update the existing tenant mapper instead of adding competing
  writers of `tenant_id`. Preserve other mappers, client settings and user
  attributes. Do not overwrite the realm.
- Production Keycloak is configured separately in `stoa-infra`. This repository
  does not establish the current production realm state. A chart update or
  restart alone does not update existing realm/client definitions.

After that approved action, verify new Console and Portal sessions locally:
an assigned user's access token, ID token and userinfo must contain the assigned
`tenant_id`; a user without a direct value or a group-provided value must have
no claim. Do not save or print raw tokens. Provision `tenant_id` only through
the trusted admin path; its profile permissions prevent account self-service
editing. Keep group attributes free of `tenant_id` after application as well.

Offline configuration check (Python 3.11, PyYAML, Helm):

```sh
python3 -B -m unittest discover -s scripts/security -p test_tenant_claim.py -v
```

This checks exports and rendered payloads, not live token issuance. Run the
behavior checks only with a local Docker context; they create and remove a
disposable Keycloak 26.5.3 container and never use an existing realm:

```sh
python3 -B scripts/security/tenant_claim_behaviour.py
```

The inherited-value case deliberately creates a group attribute in the test
realm. Its claim must be present to record the known, guarded limitation;
that result does not authorize group-based tenant assignments.
Startup imports skip existing realms ([Keycloak import documentation](https://www.keycloak.org/server/importExport)).
