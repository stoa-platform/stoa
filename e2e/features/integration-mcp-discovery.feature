@integration
Feature: MCP Discovery — Contract to MCP Tool Pipeline

  End-to-end flow: create contract → enable MCP binding →
  generate tools → verify via discovery endpoint.

  Background:
    Given the CP API and gateway are both reachable
    And I obtain a CP API token as "parzival"

  Scenario: Generate MCP tools from a published contract
    Given I create contract "e2e-mcp-gen" with version "2.0.0" via CP API
    And I update contract "e2e-mcp-gen" status to "published" via CP API
    And I enable "mcp" binding for contract "e2e-mcp-gen" via CP API
    When I generate MCP tools for contract "e2e-mcp-gen" via CP API
    Then the integration response status is 200
    And the MCP tools generation count is greater than 0

  Scenario: List MCP tools for a contract
    Given I create contract "e2e-mcp-list" with version "1.0.0" via CP API
    And I update contract "e2e-mcp-list" status to "published" via CP API
    And I enable "mcp" binding for contract "e2e-mcp-list" via CP API
    And I generate MCP tools for contract "e2e-mcp-list" via CP API
    When I list MCP tools for contract "e2e-mcp-list" via CP API
    Then the integration response status is 200
    And the MCP tools list is not empty

  Scenario: Enable multiple bindings on the same contract
    Given I create contract "e2e-multi-bind" with version "1.0.0" via CP API
    And I update contract "e2e-multi-bind" status to "published" via CP API
    When I enable "rest" binding for contract "e2e-multi-bind" via CP API
    And I enable "mcp" binding for contract "e2e-multi-bind" via CP API
    Then the CP API contract "e2e-multi-bind" has binding "rest" enabled
    And the CP API contract "e2e-multi-bind" has binding "mcp" enabled

  Scenario: Contract version is reflected in MCP tools
    Given I create contract "e2e-mcp-ver" with version "3.0.0" via CP API
    And I update contract "e2e-mcp-ver" status to "published" via CP API
    And I enable "mcp" binding for contract "e2e-mcp-ver" via CP API
    When I generate MCP tools for contract "e2e-mcp-ver" via CP API
    Then the generated MCP tools have version "3.0.0"
