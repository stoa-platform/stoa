@console @ai
Feature: Console - LLM Cost Management

  As a tenant admin or platform admin,
  I want to monitor LLM costs and manage provider budgets
  So that I can control AI spending across my tenant.

  @smoke @critical
  Scenario: Tenant admin views LLM Cost Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the LLM Cost Dashboard page
    Then the LLM Cost Dashboard page loads successfully

  @smoke
  Scenario: Platform admin views LLM Cost Dashboard
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the LLM Cost Dashboard page
    Then the LLM Cost Dashboard page loads successfully

  @rbac
  Scenario: Viewer can access LLM Cost Dashboard
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the LLM Cost Dashboard page
    Then the LLM Cost Dashboard page loads successfully

  Scenario: LLM Cost Dashboard displays budget overview
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the LLM Cost Dashboard page
    Then the LLM Cost Dashboard page loads successfully
    And the LLM Cost Dashboard displays budget cards

  Scenario: LLM Cost Dashboard displays provider list
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the LLM Cost Dashboard page
    Then the LLM Cost Dashboard page loads successfully
    And the LLM Cost Dashboard displays provider table

  @rbac
  Scenario: Admin sees delete actions on LLM Cost Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the LLM Cost Dashboard page
    Then the LLM Cost Dashboard page loads successfully
    And the LLM Cost Dashboard shows admin actions
