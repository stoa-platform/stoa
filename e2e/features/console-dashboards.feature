@console @dashboards
Feature: Console - Dashboards and Embeds

  As a tenant admin or platform admin,
  I want to access dashboards and embedded views
  So that I can monitor operations, usage, and infrastructure.

  @smoke @critical
  Scenario: Tenant admin views Operations Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Operations Dashboard page
    Then the Operations Dashboard page loads successfully

  @smoke
  Scenario: Tenant admin views My Usage dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the My Usage page
    Then the My Usage page loads successfully

  @smoke
  Scenario: Admin views Business Analytics dashboard
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the Business Analytics page
    Then the Business Analytics page loads successfully

  @smoke
  Scenario: Tenant admin views Deployments page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Deployments page
    Then the Deployments page loads successfully

  @smoke
  Scenario: Tenant admin views Gateway Status page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Gateway Status page
    Then the Gateway Status page loads successfully

  @smoke
  Scenario: Tenant admin views Gateway Modes page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Gateway Modes page
    Then the Gateway Modes page loads successfully

  @smoke @embed
  Scenario: Tenant admin views Observability embed
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Observability embed page
    Then the Observability embed page loads successfully

  @smoke @embed
  Scenario: Tenant admin views Logs embed
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Logs embed page
    Then the Logs embed page loads successfully

  @smoke @embed
  Scenario: Tenant admin views Identity Management embed
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Identity Management embed page
    Then the Identity Management embed page loads successfully
