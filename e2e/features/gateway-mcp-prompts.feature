@gateway @mcp @api
Feature: Gateway - MCP Prompts & Completion (MCP 2025-11-25)
  The STOA Gateway exposes MCP prompts and completion endpoints.
  Currently returns empty results (no prompts registered yet) but validates
  correct MCP protocol behavior per spec (CAB-1472).

  @smoke @mcp
  Scenario: MCP capabilities advertise prompt support
    When I request MCP capabilities
    Then the MCP response status is 200
    And the MCP capabilities include "prompts"

  Scenario: List prompts returns empty array
    When I list MCP prompts
    Then the MCP response status is 200
    And the MCP response body has key "prompts"
    And the MCP response has 0 items in "prompts"

  Scenario: Get unknown prompt returns not-found error
    When I get MCP prompt "nonexistent-prompt"
    Then the MCP response status is 404
    And the MCP error contains "not found"

  Scenario: Completion returns empty suggestions
    When I request MCP completion for prompt "test" argument "query" value "hello"
    Then the MCP response status is 200
    And the MCP response body has key "completion"
    And the MCP completion has empty values
