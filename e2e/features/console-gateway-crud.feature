@console @gateway
Feature: Console - Gateway CRUD

  As a platform admin,
  I want to manage gateway instances
  So that I can control the data plane.

  Scenario: Admin creates a new gateway instance
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the gateways page
    And I click the create gateway button
    And I fill in the gateway form with name "e2e-test-gw" and URL "https://gw.example.com"
    And I submit the gateway form
    Then the gateway "e2e-test-gw" appears in the gateway list

  Scenario: Admin lists all gateway instances
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the gateways page
    Then the gateway list page loads successfully
    And the gateway list contains at least one entry

  Scenario: Admin views gateway details with status badge
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the gateways page
    And I click on the first gateway
    Then the gateway detail page loads
    And the gateway status badge is visible

  Scenario: Admin updates gateway configuration
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the gateways page
    And I click on the gateway named "e2e-test-gw"
    And I click the edit gateway button
    And I update the gateway display name to "e2e-test-gw-updated"
    And I save the gateway changes
    Then I see the updated gateway name "e2e-test-gw-updated"

  Scenario: Admin deletes a gateway instance
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the gateways page
    And I click on the gateway named "e2e-test-gw-updated"
    And I click the delete gateway button
    And I confirm the gateway deletion
    Then the gateway "e2e-test-gw-updated" is no longer in the gateway list

  @security
  Scenario: Viewer cannot create or delete gateways
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateways page
    Then the gateway list page loads successfully
    And the create gateway button is not visible or disabled
