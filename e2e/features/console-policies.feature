@console @policies
Feature: Console - Policies Management

  As a platform operator,
  I want to manage API policies such as rate limiting and CORS
  So that I can enforce governance rules across deployed APIs.

  @smoke @critical
  Scenario: Admin views policies page
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the policies page
    Then the policies page loads successfully

  Scenario: Tenant admin views policies
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the policies page
    Then the policies page loads successfully

  Scenario: Viewer cannot modify policies
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the policies page
    Then policy write actions are hidden or disabled
