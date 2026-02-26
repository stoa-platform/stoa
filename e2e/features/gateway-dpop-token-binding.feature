@gateway @dpop @security
Feature: Gateway - DPoP Token Binding (RFC 9449)
  # DPoP (Demonstrating Proof-of-Possession) binds access tokens to client key pairs
  # via DPoP JWT proofs sent in the DPoP header. The gateway validates the 10-step
  # chain: parse JWT, verify typ=dpop+jwt, verify asymmetric alg, verify jwk public-only,
  # verify signature, verify htm/htu match, verify iat freshness, verify jti uniqueness,
  # verify ath binding (SHA-256 of access token).
  #
  # All scenarios except the smoke test are tagged @wip because the DPoP infrastructure
  # (Keycloak realm config + test key material) is not yet available in E2E environments.

  Background:
    Given I have a DPoP-bound access token for consumer "api-consumer-001"

  @smoke @dpop
  Scenario: Gateway health check is reachable for DPoP tests
    When I call "GET /health" without DPoP proof
    Then I receive a 200 response

  @wip @security @dpop
  Scenario: Valid DPoP proof with correct binding is accepted
    When I send a DPoP-protected request to "POST /mcp/v1/tools/invoke"
    Then I receive a 200 response

  @wip @security @dpop
  Scenario: Missing DPoP header when DPoP is required
    When I call "POST /mcp/v1/tools/invoke" without DPoP proof
    Then I receive a 401 error
    And the error message contains "missing DPoP header"

  @wip @security @dpop
  Scenario: Symmetric algorithm (HS256) is rejected
    When I send a DPoP proof with algorithm "HS256" to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "is not allowed"

  @wip @security @dpop
  Scenario: Expired DPoP proof (iat too old) is rejected
    When I send an expired DPoP proof to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "iat is too old"

  @wip @security @dpop
  Scenario: DPoP proof from the future is rejected
    When I send a future-dated DPoP proof to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "iat is in the future"

  @wip @security @dpop
  Scenario: Wrong HTTP method binding (htm mismatch)
    When I send a DPoP proof with htm "GET" to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "htm mismatch"

  @wip @security @dpop
  Scenario: Wrong URI binding (htu mismatch)
    When I send a DPoP proof with wrong htu to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "htu mismatch"

  @wip @security @dpop
  Scenario: Replay attack (same jti used twice) is detected
    When I send a DPoP proof and replay it to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "replay detected"

  @wip @security @dpop
  Scenario: Missing ath claim for token binding
    When I send a DPoP proof without ath claim to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "missing 'ath' claim"

  @wip @security @dpop
  Scenario: ath hash mismatch (wrong access token hash)
    When I send a DPoP proof with wrong ath to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "ath mismatch"

  @wip @security @dpop
  Scenario: Combined mTLS + DPoP dual binding is accepted
    Given I also have mTLS credentials for consumer "api-consumer-001"
    When I send a dual-bound request with mTLS and DPoP to "POST /mcp/v1/tools/invoke"
    Then I receive a 200 response

  @wip @security @dpop
  Scenario: DPoP proof with private key material in JWK is rejected
    When I send a DPoP proof with private key in jwk to "POST /mcp/v1/tools/invoke"
    Then I receive a 401 error
    And the error message contains "private key material"
