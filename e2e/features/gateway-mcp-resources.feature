@gateway @mcp @api
Feature: Gateway - MCP Resource Discovery (MCP 2025-11-25)
  The STOA Gateway exposes registered tools as MCP resources per the MCP spec.
  REST endpoints: POST /mcp/resources/list, POST /mcp/resources/read,
  POST /mcp/resources/templates/list (CAB-1472).

  @smoke @mcp
  Scenario: MCP capabilities advertise resource support
    When I request MCP capabilities
    Then the MCP response status is 200
    And the MCP response body has key "capabilities"
    And the MCP capabilities include "resources"

  Scenario: List resources returns valid structure
    When I list MCP resources
    Then the MCP response status is 200
    And the MCP response body has key "resources"

  Scenario: List resource templates returns RFC 6570 template
    When I list MCP resource templates
    Then the MCP response status is 200
    And the MCP response body has key "resourceTemplates"
    And the first resource template has uriTemplate "stoa://tools/{name}"

  Scenario: Read resource with unsupported URI scheme returns error
    When I read MCP resource "https://evil.example.com/stolen"
    Then the MCP response status is 400
    And the MCP error contains "unsupported"

  Scenario: Read resource for unknown tool returns not found
    When I read MCP resource "stoa://tools/nonexistent-tool-xyz"
    Then the MCP response status is 404
    And the MCP error contains "not found"

  @wip
  Scenario: Read resource for registered tool returns tool schema
    When I list MCP resources
    And I read the first available MCP resource
    Then the MCP response status is 200
    And the MCP response body has key "contents"
    And the first content has valid JSON text
