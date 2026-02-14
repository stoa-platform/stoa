@portal @consumer @critical
Feature: Consumer Onboarding — Full E2E Flow

  The complete consumer journey: register → subscribe to API with plan →
  get approved → view credentials. Tests the CAB-1121 pipeline end-to-end.

  Background:
    Given the STOA Portal is accessible

  @smoke
  Scenario: Consumer registers on the portal
    Given I am logged in as "art3mis" from community "high-five"
    When I navigate to the consumer registration page
    And I fill in the registration form with external ID "e2e-consumer-001"
    And I submit the consumer registration
    Then the consumer registration is successful
    And I see the consumer credentials modal

  @smoke
  Scenario: Consumer subscribes to an API with a plan
    Given I am logged in as "art3mis" from community "high-five"
    When I access the API catalog
    And I click on the first API in the catalog
    And I click the subscribe button
    And I select a plan from the available plans
    And I confirm the subscription
    Then the subscription is created with status "pending"

  Scenario: Tenant admin approves a pending subscription
    Given I am logged in as "parzival" from community "high-five"
    When I navigate to the approval queue
    Then I see pending subscription requests
    When I approve a pending subscription
    Then the subscription is approved successfully

  Scenario: Consumer views application credentials
    Given I am logged in as "art3mis" from community "high-five"
    When I navigate to my applications page
    And I click on the first application
    Then I can see the application credentials
    And the client ID is visible

  @e2e @critical
  Scenario: Full consumer pipeline — register, subscribe, get token, call gateway
    Given I am logged in as "art3mis" from community "high-five"
    When I navigate to the consumer registration page
    And I fill in the registration form with external ID "e2e-pipeline-001"
    And I submit the consumer registration
    Then the consumer registration is successful
    And I save the consumer credentials from the modal
    When I access the API catalog
    And I click on the first API in the catalog
    And I click the subscribe button
    And I select a plan from the available plans
    And I confirm the subscription
    Then the subscription is created with status "pending"
    Given I am logged in as "parzival" from community "high-five"
    When I navigate to the approval queue
    And I approve a pending subscription
    Then the subscription is approved successfully
    When I exchange my consumer credentials for an access token
    Then I receive a valid consumer access token
    When I call the gateway with my consumer token
    Then the gateway accepts my consumer token

  @security
  Scenario: Consumer from IOI cannot see high-five applications
    Given I am logged in as "sorrento" from community "ioi"
    When I navigate to my applications page
    Then I do not see applications from tenant "high-five"

  @security
  Scenario: Consumer from IOI cannot access high-five subscriptions
    Given I am logged in as "sorrento" from community "ioi"
    When I navigate to the subscriptions page
    Then I see only my own subscriptions
    And I do not see subscriptions from "high-five"
