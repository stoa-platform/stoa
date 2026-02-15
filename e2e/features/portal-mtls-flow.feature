@portal @mtls @critical @wip
Feature: Portal - mTLS Certificate Upload & Token Exchange
  # Tests the consumer-facing mTLS flow in the Developer Portal:
  # subscribe to an API, upload a client certificate, verify cert details.
  # Requires: running Portal + API + Keycloak + seed data.

  Background:
    Given I am logged in as "art3mis" from community "high-five"

  @smoke @mtls
  Scenario: Consumer uploads certificate during subscription
    When I access the API catalog
    And I click on the first API in the catalog
    And I click the subscribe button
    And I upload a test certificate file
    And I confirm the subscription
    Then the subscription is created with status "pending"

  @mtls
  Scenario: Consumer views certificate details after subscription
    When I navigate to my subscriptions
    And I click on the first subscription
    Then I can see the certificate fingerprint
    And the certificate status is "active"
