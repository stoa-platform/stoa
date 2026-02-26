@console @security
Feature: Console - Identity Governance

  As a tenant admin or platform admin,
  I want to review identity governance policies and access reviews
  So that I can ensure proper access control across my tenant.

  @smoke @critical
  Scenario: Tenant admin views Access Review Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Access Review Dashboard page
    Then the Access Review Dashboard page loads successfully

  @smoke
  Scenario: Platform admin views Access Review Dashboard
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the Access Review Dashboard page
    Then the Access Review Dashboard page loads successfully

  @rbac
  Scenario: Viewer can access Access Review Dashboard
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Access Review Dashboard page
    Then the Access Review Dashboard page loads successfully

  Scenario: Access Review Dashboard displays OAuth clients
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Access Review Dashboard page
    Then the Access Review Dashboard page loads successfully
    And the Access Review Dashboard displays client summary cards

  @rbac
  Scenario: Admin sees action buttons on Access Review Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Access Review Dashboard page
    Then the Access Review Dashboard page loads successfully
    And the Access Review Dashboard shows action buttons for admin
