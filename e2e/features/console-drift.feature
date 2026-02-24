@console @drift
Feature: Console - Drift Detection

  As a platform administrator,
  I want to view gateway drift detection status
  So that I can identify gateways whose configuration has drifted from the desired state.

  @smoke
  Scenario: Admin views drift detection page
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the drift detection page
    Then the drift detection page loads successfully

  Scenario: Drift page shows gateway sync status
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the drift detection page
    Then gateway sync status information is visible
