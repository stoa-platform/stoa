@portal @advanced
Feature: Portal - Advanced features

  As an API Consumer on the Developer Portal,
  I want to access advanced features like service accounts and analytics
  So that I can manage my API integrations.

  Scenario: User views service accounts page
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the service accounts page
    Then the service accounts page loads

  Scenario: User views usage analytics
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the usage analytics page
    Then the analytics page loads with usage data

  Scenario: User views webhooks page
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the webhooks page
    Then the webhooks page loads
