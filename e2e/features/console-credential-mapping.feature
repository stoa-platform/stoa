@console @credential-mapping
Feature: Console - Credential Mapping UI (CAB-1432)

  As a tenant admin or devops user,
  I want to manage per-consumer credential mappings via the Console UI
  So that I can configure which backend credentials each consumer uses.

  Background:
    Given the STOA Console is accessible

  @smoke @critical
  Scenario: Admin sees the Credential Mappings page on a gateway
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the gateways page
    And I open the first available gateway
    And I click the "Credential Mapping" tab
    Then the Credential Mapping tab loads successfully

  Scenario: Admin creates a new credential mapping
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the gateways page
    And I open the first available gateway
    And I click the "Credential Mapping" tab
    And I add a credential mapping for consumer "consumer-e2e" with header "X-Api-Key" and value "test-key-e2e"
    Then the credential mapping for "consumer-e2e" appears in the list

  Scenario: Admin edits an existing credential mapping
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the gateways page
    And I open the first available gateway
    And I click the "Credential Mapping" tab
    And a credential mapping for "consumer-e2e" exists
    And I edit the credential mapping for "consumer-e2e" changing the value to "updated-key"
    Then the credential mapping for "consumer-e2e" shows the updated value

  Scenario: Admin deletes a credential mapping
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the gateways page
    And I open the first available gateway
    And I click the "Credential Mapping" tab
    And a credential mapping for "consumer-e2e" exists
    And I delete the credential mapping for "consumer-e2e"
    Then the credential mapping for "consumer-e2e" is no longer in the list

  @security
  Scenario: Viewer cannot manage credential mappings
    Given I am logged in to Console as "aech" from team "high-five"
    When I navigate to the gateways page
    And I open the first available gateway
    And I click the "Credential Mapping" tab
    Then the add credential mapping button is not visible or disabled

  @security
  Scenario: Viewer cannot see credential values
    Given I am logged in to Console as "aech" from team "high-five"
    When I navigate to the gateways page
    And I open the first available gateway
    And I click the "Credential Mapping" tab
    Then credential header values are masked or hidden from viewers
