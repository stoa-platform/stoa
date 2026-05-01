@portal @service-accounts
Feature: Portal - Service Accounts

  As an API consumer,
  I want to manage service accounts for machine-to-machine authentication
  So that my applications can securely access APIs without user credentials.

  @smoke @critical
  Scenario: Tenant admin views service accounts page
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal service accounts page
    Then the portal service accounts page loads successfully

  Scenario: Tenant admin can see service account list
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal service accounts page
    Then the service account list or empty state is displayed

  Scenario: Viewer cannot access service accounts page
    Given I am logged in as "aech" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal service accounts page
    Then I receive an access denied error
