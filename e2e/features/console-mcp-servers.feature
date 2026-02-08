@console @mcp-servers
Feature: Console - External MCP Servers

  As a platform admin,
  I want to manage external MCP servers and view error snapshots
  So that I can monitor MCP integrations.

  @smoke @critical
  Scenario: Admin views External MCP Servers list
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the External MCP Servers page
    Then the External MCP Servers page loads successfully

  @smoke
  Scenario: Admin views MCP Error Snapshots
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the MCP Error Snapshots page
    Then the MCP Error Snapshots page loads successfully

  @security
  Scenario: Viewer cannot access External MCP Servers
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate directly to "/external-mcp-servers"
    Then I receive an access denied error or redirect

  @security
  Scenario: Viewer cannot access Error Snapshots
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate directly to "/mcp/errors"
    Then I receive an access denied error or redirect
