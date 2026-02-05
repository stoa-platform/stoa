@portal @applications
Feature: Portal - Applications and Profile

  As an API Consumer on the Developer Portal,
  I want to manage my applications and view my profile
  So that I can organize my API consumption.

  @smoke
  Scenario: User views applications list
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to my applications page
    Then the applications page loads successfully

  Scenario: User creates a new application
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to my applications page
    And I create an application named "E2E Test App"
    Then the application "E2E Test App" appears in the list

  @smoke
  Scenario: User views profile page
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to my profile page
    Then the profile page loads with user information
