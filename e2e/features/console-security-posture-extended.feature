@console @security
Feature: Console - Security Posture Dashboard (Extended)

  As a tenant admin or platform admin,
  I want to verify all security posture dashboard features
  So that I can ensure comprehensive security monitoring.

  @smoke
  Scenario: Security Dashboard displays token binding status
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully
    And the Security Dashboard displays token binding section

  Scenario: Security Dashboard displays severity breakdown
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully
    And the Security Dashboard displays severity cards

  Scenario: Security Dashboard displays scan history
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully
    And the Security Dashboard may display scan history

  @rbac
  Scenario: Admin sees quick actions on Security Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully
    And the Security Dashboard shows quick actions for admin

  @rbac
  Scenario: Viewer cannot see quick actions on Security Dashboard
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully
    And the Security Dashboard hides quick actions for viewer
