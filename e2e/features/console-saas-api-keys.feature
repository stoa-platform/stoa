@console @saas @wip
Feature: Console - SaaS API Keys Management

  As a tenant admin,
  I want to create and manage scoped API keys
  So that I can authenticate requests to backend APIs through the gateway.

  @smoke @critical
  Scenario: Admin views API Keys page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the API Keys page
    Then the API Keys page loads successfully

  Scenario: Admin creates an API key
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the API Keys page
    And I create an API key named "E2E Test Key"
    Then the key reveal dialog shows the new key
    And I dismiss the key reveal dialog

  Scenario: Admin revokes an API key
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the API Keys page
    And I revoke the API key "E2E Test Key"
    And I confirm the deletion
    Then the API key "E2E Test Key" shows as revoked

  @security
  Scenario: Viewer cannot create API keys
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the API Keys page
    Then the Create Key button is not visible or disabled
