@console @rbac @security
Feature: Console - RBAC enforcement

  As a security-conscious platform,
  I want to enforce role-based access control
  So that unauthorized users cannot access restricted pages.

  @critical
  Scenario: Viewer cannot access admin pages
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate directly to "/tenants"
    Then I receive an access denied error or redirect

  Scenario: Viewer write actions are hidden
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I access the API list
    Then write actions are hidden or disabled

  Scenario: DevOps cannot manage tenants
    Given I am logged in to Console as "art3mis" from team "high-five"
    And the STOA Console is accessible
    When I navigate directly to "/tenants"
    Then I receive an access denied error or redirect

  @critical
  Scenario: Cross-tenant API access is denied
    Given I am logged in to Console as "sorrento" from team "ioi"
    And the STOA Console is accessible
    When I try to directly access an API from tenant "high-five"
    Then I see an access denied or not found message
