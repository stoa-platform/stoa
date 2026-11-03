# Tenant claim mapper (CAB-2262, lot 1)

`deploy/keycloak/tenant-id-mapper.json` is the reviewed OIDC mapper payload for
`control-plane-ui`, `stoa-portal` and `control-plane-api` in the shared realm.
It copies the user attribute `tenant_id` as a scalar string to access tokens,
ID tokens and userinfo. There is no hardcoded tenant or fallback. The API client
remains bearer-only in Helm; that client does not itself issue tokens.

An absent attribute produces no tenant claim. The mapper does not reject login
or token issuance: denial of tenant-scoped requests without the claim belongs
to lot 2. Do not assign a default tenant to make those requests succeed.

## Application after Christophe's approval

- Fresh Compose realm: the existing `stoa-identity` default client scope already
  carries this mapper for all three clients in
  `deploy/docker-compose/init/keycloak-realm.json`.
- Fresh Helm installation with bootstrap enabled: the bootstrap creates the
  mapper directly on all three clients. It skips existing clients and does not
  run when the Keycloak Operator manages the realm.
- Existing realm: an authorized operator must reconcile only this mapper on
  each client (or its existing default client scope), using the JSON payload.
  Inspect effective direct and default-scope mappers first; update the existing
  tenant mapper instead of adding competing writers of `tenant_id`. Preserve
  other mappers, client settings and user attributes. Do not overwrite the realm.
- Production Keycloak is configured separately in `stoa-infra`. This repository
  does not establish the current production realm state. A chart update or
  restart alone does not update existing realm/client definitions.

After that approved action, verify new Console and Portal sessions locally:
an assigned user's access token, ID token and userinfo must contain the assigned
`tenant_id`; an unassigned user's outputs must omit it. Do not save or print raw
tokens. The tenant attribute must be provisioned through the trusted admin path.

Offline configuration check (Python 3.11, PyYAML, Helm):

```sh
python3 -B -m unittest discover -s scripts/security -p test_tenant_claim.py -v
```

This checks exports and rendered payloads, not live token issuance. Startup
imports skip existing realms ([Keycloak import documentation](https://www.keycloak.org/server/importExport)).
