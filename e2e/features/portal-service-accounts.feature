@portal @service-accounts
Feature: Portal - Service Accounts

  As an API consumer,
  I want to manage service accounts for machine-to-machine authentication
  So that my applications can securely access APIs without user credentials.

  @smoke @critical
  Scenario: User views service accounts page
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal service accounts page
    Then the portal service accounts page loads successfully

  Scenario: User can see service account list
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal service accounts page
    Then the service account list or empty state is displayed

  Scenario: Viewer can access service accounts page
    Given I am logged in as "aech" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal service accounts page
    Then the portal service accounts page loads successfully
