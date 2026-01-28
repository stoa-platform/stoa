package stoa.federation

import future.keywords.if
import future.keywords.in

default allow := false

# Map tenant endpoints to expected token issuers
expected_issuer := {
    "alpha": "http://keycloak:8080/realms/demo-org-alpha",
    "beta":  "http://keycloak:8080/realms/demo-org-beta",
    "gamma": "http://keycloak:8080/realms/demo-org-gamma",
}

# Allow if the token issuer matches the tenant's expected issuer
allow if {
    expected := expected_issuer[input.tenant]
    input.token.iss == expected
}

# Allow if audience includes the federation API
allow if {
    expected := expected_issuer[input.tenant]
    input.token.iss == expected
    "stoa-federation-api" in input.token.aud
}

# Deny reason for debugging
deny_reason := sprintf(
    "Issuer '%s' not authorized for tenant '%s' (expected '%s')",
    [input.token.iss, input.tenant, expected_issuer[input.tenant]]
) if {
    not allow
}

# Validate token is not expired (requires time input)
token_valid if {
    input.token.exp > input.current_time
}

# Check realm claim matches tenant
realm_match if {
    input.token.stoa_realm == concat("demo-org-", input.tenant)
}
