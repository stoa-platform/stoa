@gateway @security @sender-constraint
Feature: Gateway - Sender-Constraint Middleware (CAB-1607)

  The sender-constraint middleware validates RFC 8705 (mTLS) and RFC 9449
  (DPoP) token bindings. When a JWT access token contains a `cnf`
  (confirmation) claim, the gateway verifies that the presented proof
  (client certificate or DPoP proof) matches the binding in the token.

  Bypass paths: /.well-known/*, /oauth/*, /mcp/sse, /mcp/ws, /mcp/tools/*,
  /mcp/v1/*, /health, /ready, /metrics, /admin/*

  Background:
    Given the STOA Gateway is accessible

  # -----------------------------------------------------------------------
  # Bypass paths — these should NOT trigger sender-constraint checks
  # -----------------------------------------------------------------------

  @smoke
  Scenario: Health endpoint bypasses sender-constraint
    When I call "GET /health" without any credentials
    Then the proxy returns status other than 401

  @smoke
  Scenario: Ready endpoint bypasses sender-constraint
    When I call "GET /ready" without any credentials
    Then the proxy returns status other than 401

  Scenario: Metrics endpoint bypasses sender-constraint
    When I call "GET /metrics" without any credentials
    Then the proxy returns status other than 401

  Scenario: OAuth endpoints bypass sender-constraint
    When I call "GET /.well-known/oauth-protected-resource" without any credentials
    Then the proxy returns status other than 401

  Scenario: MCP capabilities bypass sender-constraint
    When I call "GET /mcp/capabilities" without any credentials
    Then the proxy returns status other than 401

  # -----------------------------------------------------------------------
  # mTLS binding validation (RFC 8705)
  # -----------------------------------------------------------------------

  @security
  Scenario: Matching mTLS certificate thumbprint is accepted
    Given I have a cert-bound token for consumer "api-consumer-001"
    When I call "POST /mcp/v1/tools/invoke" with mTLS headers
    Then I receive a 200 response

  @security
  Scenario: Mismatched mTLS certificate thumbprint is rejected
    Given I have a cert-bound token for consumer "api-consumer-001"
    When I call "POST /mcp/v1/tools/invoke" with wrong mTLS certificate
    Then I receive an auth error

  @security
  Scenario: Missing mTLS certificate when token requires it
    Given I have a cert-bound token for consumer "api-consumer-001"
    When I call "POST /mcp/v1/tools/invoke" without mTLS certificate
    Then I receive an auth error

  # -----------------------------------------------------------------------
  # DPoP binding validation (RFC 9449 cnf.jkt)
  # -----------------------------------------------------------------------

  @security
  Scenario: Valid DPoP proof with matching cnf.jkt is accepted
    Given I have a DPoP-bound access token for consumer "api-consumer-001"
    When I send a DPoP-protected request to "POST /mcp/v1/tools/invoke"
    Then I receive a 200 response

  @security
  Scenario: Missing DPoP proof when token has cnf.jkt binding
    Given I have a DPoP-bound access token for consumer "api-consumer-001"
    When I call "POST /mcp/v1/tools/invoke" without DPoP proof
    Then I receive a 401 error

  # -----------------------------------------------------------------------
  # Non-bypass paths — sender-constraint MUST be checked
  # -----------------------------------------------------------------------

  Scenario: LLM proxy paths are NOT bypassed by sender-constraint
    Given I have a DPoP-bound access token for consumer "api-consumer-001"
    When I call "POST /v1/messages" without DPoP proof
    Then I receive a 401 error
