package stoa.federation

import future.keywords.if
import future.keywords.in

default allow := false

# Map tenant endpoints to expected realm suffix
expected_realm := {
    "alpha": "demo-org-alpha",
    "beta":  "demo-org-beta",
    "gamma": "demo-org-gamma",
}

# Allow if the token issuer ends with the expected realm path
# This handles any Keycloak base URL (direct, via proxy, docker-internal)
allow if {
    realm := expected_realm[input.tenant]
    endswith(input.token.iss, concat("/", ["realms", realm]))
}

# Deny reason for debugging
deny_reason := sprintf(
    "Issuer '%s' not authorized for tenant '%s' (expected realm '%s')",
    [input.token.iss, input.tenant, expected_realm[input.tenant]]
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
