@portal @contracts
Feature: Portal - Contracts

  As an API consumer on the Developer Portal,
  I want to manage my API contracts
  So that I can subscribe to and consume APIs.

  @smoke @critical
  Scenario: User views Contracts list
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the contracts page
    Then the contracts page loads successfully

  @smoke
  Scenario: User views New Contract form
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the new contract page
    Then the new contract form loads successfully

  Scenario: User views Contract detail
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the contracts page
    And I click on the first contract
    Then the contract detail page loads

  @isolation @security
  Scenario: IOI user cannot see high-five contracts
    Given I am logged in as "sorrento" from community "ioi"
    And the STOA Portal is accessible
    When I navigate to the contracts page
    Then I do not see contracts from "high-five"

  Scenario: User navigates contract list to detail and back
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the contracts page
    And I click on the first contract
    Then the contract detail page loads
    When I click the back button
    Then the contracts page loads successfully

  @smoke
  Scenario: Viewer can access contracts page
    Given I am logged in as "aech" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the contracts page
    Then the contracts page loads successfully
