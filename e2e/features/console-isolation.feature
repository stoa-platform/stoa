@console @isolation @critical
Feature: Console - Tenant isolation

  Background:
    Given the STOA Console is accessible

  @rpo @high-five @critical
  Scenario: High-Five CPI can access the Console API list
    Given I am logged in to Console as "parzival" from team "high-five"
    When I access the API list
    Then I see the Console API management page

  @rpo @ioi @critical
  Scenario: IOI CPI can access the Console API list
    Given I am logged in to Console as "sorrento" from team "ioi"
    When I access the API list
    Then I see the Console API management page

  @admin
  Scenario: Anorak can access APIs and switch tenants
    Given I am logged in to Console as "anorak" platform admin
    When I access the API list
    Then I see the Console API management page
    And the tenant selector has multiple options

  @tenant-selector
  Scenario: Tenant selector is visible on API list
    Given I am logged in to Console as "parzival" from team "high-five"
    When I access the API list
    Then the tenant selector is visible

  @cross-tenant @security
  Scenario: User cannot access another tenant APIs via URL
    Given I am logged in to Console as "parzival" from team "high-five"
    When I try to directly access an API from tenant "ioi"
    Then I receive an access denied error
