@portal @consumer
Feature: Portal - Consumer Flow

  As an API consumer on the Developer Portal,
  I want to discover, subscribe to, and consume APIs
  So that I can integrate them into my applications.

  Scenario: Consumer browses API catalog and views details
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I access the API catalog
    And I click on the first API in the catalog
    Then the API detail page loads with description and endpoints

  Scenario: Consumer creates an application for API consumption
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to my applications page
    And I create an application named "E2E Consumer App"
    Then the application "E2E Consumer App" appears in the list

  Scenario: Consumer subscribes to an API with an application
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I access the API catalog
    And I click on the first API in the catalog
    And I click the subscribe button
    And I select application "E2E Consumer App" for the subscription
    And I confirm the subscription
    Then the subscription is created with status "active"

  Scenario: Consumer views API key after subscription
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to my applications page
    And I click on the first application
    Then the application detail page loads
    And the API key section is visible

  Scenario: Consumer views usage analytics for subscriptions
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the usage analytics page
    Then the analytics page loads with usage data

  @security
  Scenario: Consumer from IOI cannot see high-five applications
    Given I am logged in as "sorrento" from community "ioi"
    And the STOA Portal is accessible
    When I navigate to my applications page
    Then the applications page loads successfully
    And I do not see applications from tenant "high-five"
