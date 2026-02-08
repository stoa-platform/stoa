@portal @mcp-servers
Feature: Portal - MCP Servers and Applications

  As an API consumer on the Developer Portal,
  I want to browse MCP servers and view application details
  So that I can discover and use AI tools.

  @smoke @critical
  Scenario: User views MCP Servers list
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the MCP servers page
    Then the MCP servers page loads successfully

  Scenario: User views MCP Server detail
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the MCP servers page
    And I click on the first MCP server
    Then the MCP server detail page loads

  @smoke
  Scenario: User views Application detail
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to my applications page
    And I click on the first application
    Then the application detail page loads

  @isolation @security
  Scenario: IOI user sees only their MCP servers
    Given I am logged in as "sorrento" from community "ioi"
    And the STOA Portal is accessible
    When I navigate to the MCP servers page
    Then the MCP servers page loads successfully
    And I do not see servers from "high-five"

  Scenario: User searches MCP servers
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the MCP servers page
    And I search for a server by name
    Then the server search results are displayed
