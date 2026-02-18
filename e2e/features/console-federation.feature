@console @federation
Feature: Console - MCP Federation Management

  As a platform administrator,
  I want to manage master accounts and sub-accounts for MCP federation
  So that enterprise customers can delegate agent access with centralized policy enforcement.

  @smoke @critical
  Scenario: Admin views Federation Accounts page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    Then the Federation Accounts page loads successfully

  Scenario: Admin creates a master account
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    And I create a master account named "E2E Federation Partner" with max 5 sub-accounts
    Then the master account "E2E Federation Partner" appears in the list

  Scenario: Admin views master account detail
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    And I click on the master account "E2E Federation Partner"
    Then I see the master account detail page
    And the usage breakdown section is visible

  Scenario: Admin creates a sub-account
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    And I click on the master account "E2E Federation Partner"
    And I create a sub-account named "Agent Alpha"
    Then the API key reveal dialog is displayed
    And I dismiss the API key dialog
    And the sub-account "Agent Alpha" appears in the sub-accounts table

  Scenario: Admin manages tool allow-list for sub-account
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    And I click on the master account "E2E Federation Partner"
    And I open the tool allow-list for sub-account "Agent Alpha"
    Then the tool allow-list modal is displayed

  Scenario: Admin changes usage period
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    And I click on the master account "E2E Federation Partner"
    And I change the usage period to "30" days
    Then the usage breakdown reflects the selected period

  Scenario: Admin suspends a master account
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    And I click on the master account "E2E Federation Partner"
    And I suspend the master account
    And I confirm the action
    Then the master account status shows "Suspended"

  @security
  Scenario: Viewer cannot create master accounts
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    Then the Create Master Account button is not visible or disabled

  Scenario: Admin deletes a master account
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Federation Accounts page
    And I delete the master account "E2E Federation Partner"
    And I confirm the deletion
    Then the master account "E2E Federation Partner" is no longer in the list
