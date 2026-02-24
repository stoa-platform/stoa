@portal @webhooks
Feature: Portal - Webhooks

  As an API consumer,
  I want to configure webhooks for my subscriptions
  So that I can receive real-time event notifications.

  @smoke @critical
  Scenario: User views webhooks page
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal webhooks page
    Then the portal webhooks page loads successfully

  Scenario: User can see webhook configuration options
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal webhooks page
    Then webhook configuration options are visible

  @isolation @security
  Scenario: IOI user cannot see high-five webhooks
    Given I am logged in as "sorrento" from tenant "ioi"
    And the STOA Portal is accessible
    When I navigate to the portal webhooks page
    Then no webhooks from tenant "high-five" are visible
