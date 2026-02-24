@portal @usage
Feature: Portal - Usage Dashboard

  As an API consumer,
  I want to view my API usage metrics and execution history
  So that I can monitor my consumption and optimize my integrations.

  @smoke @critical
  Scenario: User views usage dashboard
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal usage dashboard
    Then the usage dashboard page loads successfully

  Scenario: Usage page shows metrics or empty state
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal usage dashboard
    Then usage metrics or an empty state are displayed

  Scenario: User views execution history
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal execution history
    Then the execution history page loads successfully
