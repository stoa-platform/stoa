@console @chat-settings
Feature: Console - Tenant Chat Settings

  As a tenant admin or platform admin,
  I want to configure chat settings for my tenant
  So that I can control which apps have chat access and set usage budgets.

  Background:
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible

  @smoke @critical
  Scenario: Tenant admin can navigate to chat settings page
    When I navigate to the chat settings page in Console
    Then the Console chat settings page loads successfully

  Scenario: Chat settings page shows both app toggles
    When I navigate to the chat settings page in Console
    Then the Console chat settings page loads successfully
    And the console chat enable toggle is visible
    And the portal chat enable toggle is visible

  Scenario: Chat settings page shows the daily budget input
    When I navigate to the chat settings page in Console
    Then the Console chat settings page loads successfully
    And the daily budget input is visible

  Scenario: Tenant admin can save chat settings
    When I navigate to the chat settings page in Console
    Then the Console chat settings page loads successfully
    When I save the chat settings
    Then the chat settings save succeeds

  Scenario: Tenant admin can disable console chat
    When I navigate to the chat settings page in Console
    Then the Console chat settings page loads successfully
    When I toggle the console chat enable switch
    And I save the chat settings
    Then the chat settings save succeeds

  Scenario: Tenant admin can set a custom daily budget
    When I navigate to the chat settings page in Console
    Then the Console chat settings page loads successfully
    When I set the daily budget to 50000
    And I save the chat settings
    Then the chat settings save succeeds

  @security @regression
  Scenario: Viewer cannot modify chat settings
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the chat settings page in Console
    Then the viewer cannot save chat settings

  @security
  Scenario: CPI admin can configure chat settings for any tenant
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the chat settings page in Console
    Then the Console chat settings page loads successfully
    And the console chat enable toggle is visible

  # CAB-1854: system prompt configuration (planned, not yet in Phase 1 API)
  @wip
  Scenario: Tenant admin can set a system prompt
    When I navigate to the chat settings page in Console
    Then the Console chat settings page loads successfully
    When I set the system prompt to "You are a helpful STOA API assistant."
    And I save the chat settings
    Then the chat settings save succeeds
