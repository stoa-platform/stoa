@console @security
Feature: Console - Security Posture Dashboard

  As a tenant admin or platform admin,
  I want to access the Security Posture Dashboard
  So that I can monitor security compliance, vulnerabilities, and audit status.

  @smoke @critical
  Scenario: Tenant admin views Security Posture Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully

  @smoke
  Scenario: Platform admin views Security Posture Dashboard
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully

  @rbac
  Scenario: Viewer can access Security Posture Dashboard
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully

  Scenario: Security Posture Dashboard displays compliance metrics
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Security Posture Dashboard page
    Then the Security Posture Dashboard page loads successfully
    And the Security Posture Dashboard displays security metrics
