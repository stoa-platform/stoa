@portal @smoke
Feature: Portal - API Catalog visibility by community

  Background:
    Given the STOA Portal is accessible

  @rpo @high-five
  Scenario: Parzival sees all public OASIS APIs
    Given I am logged in as "parzival" from community "high-five"
    When I access the API catalog
    Then I see APIs in the catalog

  @rpo @ioi
  Scenario: Sorrento sees all public OASIS APIs
    Given I am logged in as "sorrento" from community "ioi"
    When I access the API catalog
    Then I see APIs in the catalog

  @filtering
  Scenario: Search in the catalog
    Given I am logged in as "art3mis" from community "high-five"
    And I am on the API catalog page
    When I search for "payment"
    Then the results contain "payment"

  @filtering
  Scenario: Filter APIs by category
    Given I am logged in as "art3mis" from community "high-five"
    And I am on the API catalog page
    When I filter by category "Finance"
    Then all displayed APIs have category "Finance"

  @visibility
  Scenario: Public APIs are visible to all users
    Given I am logged in as "aech" from community "high-five"
    When I access the API catalog
    Then I see the same catalog as other users
