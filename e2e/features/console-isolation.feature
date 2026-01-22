@console @isolation @critical
Feature: Console - Tenant isolation

  Background:
    Given the STOA Console is accessible

  @rpo @high-five @critical
  Scenario: High-Five CPI sees only their tenant APIs
    Given I am logged in to Console as "parzival" from team "high-five"
    When I access the API list
    Then I see only APIs from tenant "high-five"
    And I do not see APIs from tenant "ioi"

  @rpo @ioi @critical
  Scenario: IOI CPI sees only their tenant APIs
    Given I am logged in to Console as "sorrento" from team "ioi"
    When I access the API list
    Then I see only APIs from tenant "ioi"
    And I do not see APIs from tenant "high-five"

  @admin
  Scenario: Anorak can see APIs from all tenants
    Given I am logged in to Console as "anorak" platform admin
    When I access the API list
    And I select tenant "high-five"
    Then I see APIs from tenant "high-five"
    When I select tenant "ioi"
    Then I see APIs from tenant "ioi"

  @tenant-selector
  Scenario: Tenant selector shows only authorized tenants
    Given I am logged in to Console as "art3mis" from team "high-five"
    When I open the tenant selector
    Then I see only tenant "high-five" in the list
    And I do not see tenant "ioi" in the list

  @cross-tenant @security
  Scenario: User cannot access another tenant APIs via URL
    Given I am logged in to Console as "parzival" from team "high-five"
    When I try to directly access an API from tenant "ioi"
    Then I receive an access denied error
