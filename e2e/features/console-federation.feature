@federation @console @wip
Feature: Console - Federation Master Account Management

  As a tenant admin,
  I want to manage federation master accounts in the Console
  So that I can aggregate developer/agent connections under a single billing entity.

  Background:
    Given the STOA Console is accessible

  @smoke
  Scenario: Admin sees federation page
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the Federation page
    Then the Federation page loads successfully

  Scenario: Admin creates a federation master account
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the Federation page
    And I create a master account named "E2E Federation Master"
    Then the master account "E2E Federation Master" appears in the list

  Scenario: Admin creates a sub-account under master
    Given I am logged in to Console as "parzival" from team "high-five"
    And a master account "E2E Federation Master" exists
    When I navigate to the Federation detail page for "E2E Federation Master"
    And I create a sub-account named "E2E Sub-Account Agent"
    Then the sub-account "E2E Sub-Account Agent" appears in the sub-accounts table
    And the sub-account has an API key

  Scenario: Admin revokes a sub-account
    Given I am logged in to Console as "parzival" from team "high-five"
    And a master account "E2E Federation Master" exists
    When I navigate to the Federation detail page for "E2E Federation Master"
    And I revoke the sub-account "E2E Sub-Account Agent"
    And I confirm the action
    Then the sub-account "E2E Sub-Account Agent" shows status "revoked"

  Scenario: Admin bulk revokes all sub-accounts
    Given I am logged in to Console as "parzival" from team "high-five"
    And a master account "E2E Federation Master" exists
    When I navigate to the Federation detail page for "E2E Federation Master"
    And I click the bulk revoke button
    And I confirm the action
    Then all sub-accounts show status "revoked"

  Scenario: Admin views usage dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And a master account "E2E Federation Master" exists
    When I navigate to the Federation detail page for "E2E Federation Master"
    Then the usage breakdown section is visible
    And the usage chart displays data

  @rbac
  Scenario: Viewer cannot create master accounts
    Given I am logged in to Console as "aech" from team "high-five"
    When I navigate to the Federation page
    Then the create master account button is not visible

  @rbac
  Scenario: Devops cannot revoke sub-accounts
    Given I am logged in to Console as "art3mis" from team "high-five"
    And a master account "E2E Federation Master" exists
    When I navigate to the Federation detail page for "E2E Federation Master"
    Then the revoke button is not visible

  Scenario: Admin deletes a federation master account
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the Federation page
    And I delete the master account "E2E Federation Master"
    And I confirm the action
    Then the master account "E2E Federation Master" is no longer in the list
