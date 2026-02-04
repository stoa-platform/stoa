@gateway @runtime @security
Feature: Gateway - Runtime access control

  @rpo @authorized @smoke
  Scenario: Health endpoint is accessible
    When I call "GET /health/ready"
    Then I receive a 200 response

  @rpo @unauthorized @negative
  Scenario: Protected endpoint requires authentication
    When I call "GET /v1/portal/apis" without API key
    Then I receive an auth error

  @rpo @invalid-key @negative
  Scenario: Invalid bearer token is rejected
    Given I have an invalid API key
    When I call "GET /v1/portal/apis"
    Then I receive an auth error

  @rpo @isolation @critical
  Scenario: Admin endpoints require authentication
    When I call "GET /v1/admin/prospects" without API key
    Then I receive an auth error

  @rate-limiting
  Scenario: Multiple rapid calls do not crash the gateway
    When I make many health check calls
    Then the gateway remains responsive

  @token-expiry
  Scenario: Expired token is rejected on protected endpoint
    Given I have an expired access token
    When I call "GET /v1/me"
    Then I receive an auth error
