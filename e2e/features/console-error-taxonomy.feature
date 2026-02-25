@console @executions
Feature: Console - Execution View and Error Taxonomy

  As a tenant admin or platform admin,
  I want to access the Execution View dashboard
  So that I can analyze tool execution results and error taxonomy.

  @smoke @critical
  Scenario: Tenant admin views Execution View dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Execution View page
    Then the Execution View page loads successfully

  @smoke
  Scenario: Platform admin views Execution View dashboard
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the Execution View page
    Then the Execution View page loads successfully

  @rbac
  Scenario: Viewer can access Execution View dashboard
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Execution View page
    Then the Execution View page loads successfully

  Scenario: Execution View displays error taxonomy chart
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Execution View page
    Then the Execution View page loads successfully
    And the Error Taxonomy chart is visible
