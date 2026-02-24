@portal @credentials
Feature: Portal - Credential Mappings

  As an API consumer,
  I want to view and manage my credential mappings
  So that I can configure how my applications authenticate with backend APIs.

  @smoke @critical
  Scenario: User views credential mappings page
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal credentials page
    Then the portal credentials page loads successfully

  Scenario: Credential page loads with list or empty state
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal credentials page
    Then credential mappings list or empty state is displayed

  @isolation @security
  Scenario: IOI user cannot see high-five credentials
    Given I am logged in as "sorrento" from tenant "ioi"
    And the STOA Portal is accessible
    When I navigate to the portal credentials page
    Then no credentials from tenant "high-five" are visible
