@console @rbac @admin
Feature: Console - Admin RBAC enforcement

  As a security-conscious platform,
  I want to enforce granular role-based access control
  So that each persona can only perform actions matching their role.

  Scenario: CPI admin can access all admin sections
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the tenants page
    Then the tenants list loads successfully
    When I navigate to the admin prospects page
    Then the prospects page loads successfully
    When I navigate to the monitoring page
    Then the monitoring dashboard loads successfully

  Scenario: Tenant admin can manage own tenant APIs but not admin pages
    Given I am logged in to Console as "sorrento" from team "ioi"
    And the STOA Console is accessible
    When I access the API list
    Then I see the Console API management page
    When I navigate directly to "/tenants"
    Then I receive an access denied error or redirect

  Scenario: Tenant admin from IOI cannot see high-five resources
    Given I am logged in to Console as "sorrento" from team "ioi"
    And the STOA Console is accessible
    When I access the API list
    Then I do not see APIs belonging to tenant "high-five"

  Scenario: Viewer can browse but not modify resources
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I access the API list
    Then I see the Console API management page
    And write actions are hidden or disabled
    When I navigate to the gateways page
    Then the gateway list page loads successfully
    And the create gateway button is not visible or disabled

  @security
  Scenario: Direct URL access to admin endpoints is blocked for non-admins
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate directly to "/admin/prospects"
    Then I receive an access denied error or redirect
    When I navigate directly to "/monitoring"
    Then I receive an access denied error or redirect
