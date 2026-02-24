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
