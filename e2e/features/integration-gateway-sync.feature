@integration
Feature: Gateway Sync — CP API Contract Reflected at Gateway

  Contracts created and published via the CP API should be
  discoverable at the gateway layer through MCP tools.

  Background:
    Given the CP API and gateway are both reachable
    And I obtain a CP API token as "parzival"

  Scenario: Published contract with MCP binding appears in gateway discovery
    Given I create contract "e2e-gw-sync" with version "1.0.0" via CP API
    And I update contract "e2e-gw-sync" status to "published" via CP API
    And I enable "mcp" binding for contract "e2e-gw-sync" via CP API
    And I generate MCP tools for contract "e2e-gw-sync" via CP API
    When I query MCP generated tools for tenant "high-five" via CP API
    Then the integration response status is 200
    And the generated tools list includes contract "e2e-gw-sync"

  Scenario: Draft contract does not appear in gateway discovery
    Given I create contract "e2e-gw-draft-only" with version "1.0.0" via CP API
    When I query MCP generated tools for tenant "high-five" via CP API
    Then the generated tools list does not include contract "e2e-gw-draft-only"

  Scenario: Disabling a binding removes it from contract details
    Given I create contract "e2e-gw-disable" with version "1.0.0" via CP API
    And I update contract "e2e-gw-disable" status to "published" via CP API
    And I enable "rest" binding for contract "e2e-gw-disable" via CP API
    When I disable "rest" binding for contract "e2e-gw-disable" via CP API
    Then the integration response status is 200
    And the CP API contract "e2e-gw-disable" has binding "rest" disabled
