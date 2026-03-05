@portal @profile
Feature: Portal - User Profile

  As an API consumer,
  I want to view and manage my profile information
  So that I can keep my account details up to date.

  @smoke @regression
  Scenario: User views profile page
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal profile page
    Then the portal profile page loads successfully

  @regression
  Scenario: Profile shows user information
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal profile page
    Then user profile information is displayed
