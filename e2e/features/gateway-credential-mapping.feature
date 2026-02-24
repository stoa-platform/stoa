@gateway @credential-mapping
Feature: Gateway - Per-consumer credential mapping (CAB-1432)

  The gateway resolves per-consumer backend credentials from the
  ConsumerCredentialStore and injects them before forwarding to the
  backend API. Falls back to route-level BYOK when no consumer mapping
  exists.

  Background:
    Given a test route "test-route-cm" exists with backend "https://httpbin.org/get"

  @credential-mapping @crud
  Scenario: Create a per-consumer credential mapping via admin API
    When I upsert a consumer credential mapping:
      | route_id       | consumer_id | auth_type | header_name | header_value |
      | test-route-cm  | consumer-a  | api_key   | X-Api-Key   | key-alpha    |
    Then the credential mapping response status is 200
    And the consumer credential list contains 1 entry for route "test-route-cm"

  @credential-mapping @injection @critical
  Scenario: Gateway injects correct backend credential for consumer A
    Given a consumer credential mapping exists:
      | route_id       | consumer_id | auth_type | header_name | header_value   |
      | test-route-cm  | consumer-a  | api_key   | X-Api-Key   | key-for-alpha  |
    When consumer "consumer-a" calls the proxied route "test-route-cm"
    Then the backend receives header "X-Api-Key" with value "key-for-alpha"

  @credential-mapping @injection @critical
  Scenario: Gateway injects different credential for consumer B on same route
    Given a consumer credential mapping exists:
      | route_id       | consumer_id | auth_type | header_name | header_value  |
      | test-route-cm  | consumer-a  | api_key   | X-Api-Key   | key-for-alpha |
    And a consumer credential mapping exists:
      | route_id       | consumer_id | auth_type | header_name | header_value  |
      | test-route-cm  | consumer-b  | api_key   | X-Api-Key   | key-for-beta  |
    When consumer "consumer-b" calls the proxied route "test-route-cm"
    Then the backend receives header "X-Api-Key" with value "key-for-beta"

  @credential-mapping @fallback
  Scenario: Gateway falls back to route-level BYOK when no consumer mapping
    Given a route-level BYOK credential exists for "test-route-cm":
      | header_name | header_value   |
      | X-Api-Key   | byok-fallback  |
    And no consumer credential mapping exists for "consumer-x" on "test-route-cm"
    When consumer "consumer-x" calls the proxied route "test-route-cm"
    Then the backend receives header "X-Api-Key" with value "byok-fallback"

  @credential-mapping @negative
  Scenario: Anonymous consumer with no mapping and no BYOK gets no injection
    Given no consumer credential mapping exists for "anonymous" on "test-route-cm"
    And no route-level BYOK credential exists for "test-route-cm"
    When an anonymous consumer calls the proxied route "test-route-cm"
    Then the backend does not receive header "X-Api-Key"

  @credential-mapping @crud @delete
  Scenario: Delete a consumer credential mapping
    Given a consumer credential mapping exists:
      | route_id       | consumer_id | auth_type | header_name | header_value |
      | test-route-cm  | consumer-d  | api_key   | X-Api-Key   | key-delete   |
    When I delete the consumer credential for "consumer-d" on route "test-route-cm"
    Then the credential mapping response status is 200
    And the consumer credential list has 0 entries for "consumer-d" on "test-route-cm"
