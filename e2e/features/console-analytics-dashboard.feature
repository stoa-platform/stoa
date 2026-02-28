@console @analytics
Feature: Console - Analytics Dashboard

  As a tenant admin or platform admin,
  I want to access the Analytics Dashboard
  So that I can monitor API consumer usage, tool calls, and performance metrics.

  @smoke @critical
  Scenario: Tenant admin views Analytics Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Analytics Dashboard page
    Then the Analytics Dashboard page loads successfully

  @smoke
  Scenario: Platform admin views Analytics Dashboard
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the Analytics Dashboard page
    Then the Analytics Dashboard page loads successfully

  @rbac
  Scenario: Viewer can access Analytics Dashboard in read-only mode
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Analytics Dashboard page
    Then the Analytics Dashboard page loads successfully

  Scenario: Analytics Dashboard displays consumer usage data
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Analytics Dashboard page
    Then the Analytics Dashboard page loads successfully
    And the Analytics Dashboard displays consumer data

  Scenario: DevOps user can access Analytics Dashboard
    Given I am logged in to Console as "art3mis" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Analytics Dashboard page
    Then the Analytics Dashboard page loads successfully

  Scenario: Analytics Dashboard shows time range controls
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Analytics Dashboard page
    Then the Analytics Dashboard page loads successfully
    And the Analytics Dashboard shows time range selector

  @rbac
  Scenario: Viewer sees Analytics Dashboard in read-only mode
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Analytics Dashboard page
    Then the Analytics Dashboard page loads successfully
    And the Analytics Dashboard hides export or write actions

  @isolation @security
  Scenario: IOI admin sees only own tenant analytics
    Given I am logged in to Console as "sorrento" from team "ioi"
    And the STOA Console is accessible
    When I navigate to the Analytics Dashboard page
    Then the Analytics Dashboard page loads successfully
    And no analytics data from tenant "high-five" is visible
