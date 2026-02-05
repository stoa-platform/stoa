@console @gateways
Feature: Console - Gateway and Deployment management

  As a platform operator,
  I want to view registered gateways and their deployments
  So that I can monitor multi-gateway operations.

  @critical @smoke
  Scenario: Tenant admin views gateway list
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateways page
    Then the gateway list page loads successfully

  Scenario: Tenant admin views gateway detail
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateways page
    And I click on the first gateway
    Then the gateway detail page loads

  @critical
  Scenario: Tenant admin views deployments dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateway deployments page
    Then the deployments dashboard loads with sync status cards

  @admin
  Scenario: Platform admin sees all gateways
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the gateways page
    Then the gateway list page loads successfully
