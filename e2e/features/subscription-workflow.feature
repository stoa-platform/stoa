@portal @subscriptions @rpo
Feature: Portal - API subscription workflow

  Background:
    Given the STOA Portal is accessible
    And there are published APIs in the catalog

  @subscribe @smoke
  Scenario: Art3mis views their subscriptions
    Given I am logged in as "art3mis" from community "high-five"
    When I navigate to the subscriptions page
    Then I see the list of my subscriptions
    And each subscription shows its status

  @subscribe
  Scenario: Subscribe to an API from the catalog
    Given I am logged in as "art3mis" from community "high-five"
    And I am viewing an API in the catalog
    When I click on "Subscribe"
    And I confirm the subscription
    Then the subscription is created with status "active"
    And I can see my new API key

  @api-key
  Scenario: Manage API keys for a subscription
    Given I am logged in as "parzival" from community "high-five"
    And I have an active subscription
    When I navigate to my subscriptions
    And I click on "View Details" for a subscription
    Then I can see the API key information
    And I can reveal the complete API key

  @revoke
  Scenario: Revoke a subscription
    Given I am logged in as "art3mis" from community "high-five"
    And I have an active subscription
    When I navigate to my subscriptions
    And I click on "Revoke" for a subscription
    And I confirm the revocation
    Then the subscription changes to status "revoked"

  @isolation @security
  Scenario: User does not see other users subscriptions
    Given I am logged in as "sorrento" from community "ioi"
    When I navigate to the subscriptions page
    Then I see only my own subscriptions
    And I do not see subscriptions from "high-five"
