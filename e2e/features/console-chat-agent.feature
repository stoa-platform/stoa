@console @chat-agent
Feature: Console - Chat Agent

  As a tenant admin or platform admin,
  I want to interact with the STOA Chat Agent in the Console
  So that I can explore APIs, get help, and test agentic tool calls.

  @smoke @critical
  Scenario: Tenant admin opens the Chat Agent panel
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    Then the Chat Agent interface is visible

  @smoke
  Scenario: Chat Agent responds to a simple greeting
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "Hello"
    Then the Chat Agent returns a response

  Scenario: Chat Agent lists available tools
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "What tools do you have access to?"
    Then the Chat Agent returns a response
    And the response mentions available tools

  Scenario: Chat Agent handles an API-related query
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "List my APIs"
    Then the Chat Agent returns a response

  @security
  Scenario: Viewer can read Chat Agent conversation history
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    Then the Chat Agent interface is visible

  Scenario: Chat Agent session can be cleared
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "Hello"
    And the Chat Agent returns a response
    And I clear the Chat Agent conversation
    Then the Chat Agent conversation is empty

  Scenario: Platform admin uses Chat Agent with elevated context
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "Show me platform-wide API statistics"
    Then the Chat Agent returns a response

  # CAB-1839: Mutation confirmation flow
  @regression
  Scenario: Tenant admin sees confirmation dialog before tool mutation executes
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "Create a new API named test-api-e2e"
    Then a tool confirmation dialog appears
    And the confirmation dialog shows the proposed action

  @regression
  Scenario: Tenant admin can confirm a tool mutation
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "Create a new API named test-api-e2e"
    And a tool confirmation dialog appears
    And I confirm the tool execution
    Then the Chat Agent returns a response

  @regression
  Scenario: Tenant admin can reject a tool mutation
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "Delete all my APIs"
    And a tool confirmation dialog appears
    And I reject the tool execution
    Then the tool execution is cancelled

  # CAB-1839: RBAC — cpi-admin vs viewer
  @security @regression
  Scenario: Viewer cannot trigger mutation tool calls
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "Create a new API named viewer-test"
    Then the Chat Agent does not execute mutations for viewer

  @security @regression
  Scenario: CPI admin can confirm mutations with full platform scope
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I open the Chat Agent panel
    And I send the message "List all tenant APIs across the platform"
    Then the Chat Agent returns a response
