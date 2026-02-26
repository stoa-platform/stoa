@gateway @modes
Feature: Gateway - Proxy and Shadow Mode Operations

  As a platform admin,
  I want to verify proxy and shadow gateway modes work correctly
  So that I can deploy gateways in different operational configurations.

  @smoke @critical
  Scenario: Proxy mode gateway health check
    Given the STOA Gateway is accessible
    When I send a health check to the proxy mode gateway
    Then the gateway responds with healthy status

  @smoke
  Scenario: Shadow mode gateway health check
    Given the STOA Gateway is accessible
    When I send a health check to the shadow mode gateway
    Then the gateway responds with healthy status

  Scenario: Proxy mode forwards requests to upstream
    Given the STOA Gateway is accessible
    And the gateway is configured in proxy mode
    When I send a request through the proxy gateway
    Then the request is forwarded to the upstream service
    And the response includes proxy headers

  Scenario: Shadow mode duplicates traffic without affecting response
    Given the STOA Gateway is accessible
    And the gateway is configured in shadow mode
    When I send a request through the shadow gateway
    Then the primary response is returned unchanged
    And the shadow copy is sent asynchronously

  Scenario: Proxy mode applies rate limiting
    Given the STOA Gateway is accessible
    And the gateway is configured in proxy mode with rate limiting
    When I send requests exceeding the rate limit
    Then the gateway returns 429 Too Many Requests

  Scenario: Shadow mode records comparison metrics
    Given the STOA Gateway is accessible
    And the gateway is configured in shadow mode
    When I send a request through the shadow gateway
    Then shadow comparison metrics are recorded
