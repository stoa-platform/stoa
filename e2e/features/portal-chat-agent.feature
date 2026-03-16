@portal @chat-agent
Feature: Portal - Chat Agent

  As a developer using the STOA Developer Portal,
  I want to interact with the Chat Agent
  So that I can explore APIs and get contextual help.

  @smoke @critical
  Scenario: Developer opens the Chat Agent panel
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I open the Portal Chat Agent panel
    Then the Portal Chat Agent interface is visible

  @smoke
  Scenario: Developer sends a message and receives a response
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I open the Portal Chat Agent panel
    And I send the portal chat message "Hello"
    Then the Portal Chat Agent returns a response

  Scenario: Developer asks about available APIs
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I open the Portal Chat Agent panel
    And I send the portal chat message "What APIs are available?"
    Then the Portal Chat Agent returns a response

  @security
  Scenario: Viewer role can open Chat Agent but not execute mutations
    Given I am logged in as "aech" from community "high-five"
    And the STOA Portal is accessible
    When I open the Portal Chat Agent panel
    Then the Portal Chat Agent interface is visible
    And the Portal Chat Agent does not offer mutation tools to viewer

  Scenario: CPI admin can access Chat Agent with elevated context
    Given I am logged in as "anorak" platform admin
    And the STOA Portal is accessible
    When I open the Portal Chat Agent panel
    And I send the portal chat message "List all tenant APIs"
    Then the Portal Chat Agent returns a response
