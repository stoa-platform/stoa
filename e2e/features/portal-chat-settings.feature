@portal @chat-settings
Feature: Portal - Tenant Chat Settings

  As a tenant admin using the Developer Portal,
  I want to configure chat settings for my tenant
  So that I can control portal chat access and usage budgets.

  Background:
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible

  @smoke @critical
  Scenario: Tenant admin can navigate to chat settings page in Portal
    When I navigate to the chat settings page in Portal
    Then the Portal chat settings page loads successfully

  Scenario: Portal chat settings page shows both app toggles
    When I navigate to the chat settings page in Portal
    Then the Portal chat settings page loads successfully
    And the portal chat enable toggle is visible
    And the console chat enable toggle is visible

  Scenario: Tenant admin can save portal chat settings
    When I navigate to the chat settings page in Portal
    Then the Portal chat settings page loads successfully
    When I save the portal chat settings
    Then the portal chat settings save succeeds

  Scenario: Tenant admin can disable portal chat
    When I navigate to the chat settings page in Portal
    Then the Portal chat settings page loads successfully
    When I toggle the portal chat enable switch in Portal
    And I save the portal chat settings
    Then the portal chat settings save succeeds

  Scenario: Tenant admin can update daily budget in Portal
    When I navigate to the chat settings page in Portal
    Then the Portal chat settings page loads successfully
    When I set the portal daily budget to 75000
    And I save the portal chat settings
    Then the portal chat settings save succeeds

  @security @regression
  Scenario: Viewer cannot modify portal chat settings
    Given I am logged in as "aech" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the chat settings page in Portal
    Then the portal viewer cannot save chat settings
