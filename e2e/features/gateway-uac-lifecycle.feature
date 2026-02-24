@gateway @uac @uac-lifecycle
Feature: Gateway - UAC Contract Lifecycle

  As a platform operator,
  I want to manage the full lifecycle of UAC contracts on the gateway
  So that APIs are consistently exposed as MCP tools with versioning and rollback support.

  @smoke @critical
  Scenario: Deploy a UAC contract and verify tool is discoverable
    Given a UAC contract "e2e-lifecycle-contract" is deployed for tenant "oasis"
    When I list MCP tools on the gateway for tenant "oasis"
    Then the tool from contract "e2e-lifecycle-contract" is listed

  Scenario: Update a UAC contract with a new version
    Given a UAC contract "e2e-lifecycle-contract" is deployed for tenant "oasis"
    When I update the UAC contract "e2e-lifecycle-contract" with version "2"
    Then the updated contract is active on the gateway
    And the MCP tool reflects the updated version

  Scenario: Delete a UAC contract removes the tool
    Given a UAC contract "e2e-cleanup-contract" is deployed for tenant "oasis"
    When I delete the UAC contract "e2e-cleanup-contract" from the gateway
    Then the tool from contract "e2e-cleanup-contract" is no longer listed

  Scenario: UAC contract enforces rate limiting
    Given a UAC contract "e2e-ratelimit-contract" is deployed with rate limit "5" per minute
    When I call the UAC contract tool "10" times rapidly
    Then at least one response has status "429"

  @security
  Scenario: UAC contract is tenant-isolated
    Given a UAC contract "e2e-isolation-contract" is deployed for tenant "oasis"
    When I list MCP tools on the gateway for tenant "high-five"
    Then the tool from contract "e2e-isolation-contract" is not listed

  Scenario: Deploy a UAC contract with CORS policy
    Given a UAC contract "e2e-cors-contract" is deployed with CORS allowed origin "https://console.gostoa.dev"
    When I call the UAC contract tool with Origin "https://console.gostoa.dev"
    Then the response includes CORS headers

  Scenario: Gateway health check passes after contract deployment
    Given a UAC contract "e2e-health-contract" is deployed for tenant "oasis"
    When I check the gateway health endpoint
    Then the gateway reports healthy status
