@console @diagnostics
Feature: Console - Platform Diagnostics

  As a platform administrator,
  I want to view platform diagnostics and health checks
  So that I can monitor the overall health of the STOA platform.

  @smoke @critical
  Scenario: Admin views diagnostics page
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the diagnostics page
    Then the diagnostics page loads successfully

  Scenario: Diagnostics shows health checks
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the diagnostics page
    Then health check status indicators are visible

  Scenario: Admin views error snapshots
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the error snapshots page
    Then the error snapshots page loads successfully
