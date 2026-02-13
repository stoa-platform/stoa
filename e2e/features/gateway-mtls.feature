@gateway @mtls @security
Feature: Gateway - mTLS Certificate Binding (RFC 8705)
  # X-SSL-Client-* headers simulate TLS termination by a reverse proxy (F5/nginx).
  # In production, the proxy terminates mTLS and injects these headers.
  # The gateway validates the cert fingerprint against the JWT cnf.x5t#S256 claim.

  Background:
    Given I have a cert-bound token for consumer "api-consumer-001"

  @smoke @mtls
  Scenario: Valid cert-bound token with matching certificate
    When I call "POST /mcp/v1/tools/invoke" with mTLS headers
    Then I receive a 200 response

  @security @mtls
  Scenario: Stolen token with wrong certificate is rejected
    When I call "POST /mcp/v1/tools/invoke" with wrong mTLS certificate
    Then I receive a 403 error
    And the error message contains "MTLS_BINDING_MISMATCH"

  @security @mtls
  Scenario: Token without certificate on protected route
    When I call "POST /mcp/v1/tools/invoke" without mTLS certificate
    Then I receive a 401 error
    And the error message contains "MTLS_CERT_REQUIRED"

  # Edge cases — require --profile=mixed seed data (CAB-872)

  @security @mtls @edge-case
  Scenario: Revoked consumer cannot obtain new credentials
    When I attempt to authenticate as consumer "api-consumer-099"
    Then the authentication is rejected

  @security @mtls @edge-case
  Scenario: Expired certificate is rejected at gateway
    When I call "POST /mcp/v1/tools/invoke" with expired mTLS certificate
    Then I receive a 403 error
    And the error message contains "MTLS_CERT_EXPIRED"
