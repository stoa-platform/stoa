@console @audit
Feature: Console - Audit Log

  As a platform administrator,
  I want to view and filter audit events
  So that I can monitor platform activity and maintain compliance.

  @smoke @critical
  Scenario: Admin views audit log
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the audit log page
    Then the audit log page loads successfully

  Scenario: Admin can filter audit events
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the audit log page
    And I filter audit events by type
    Then the filtered audit results are displayed

  Scenario: Admin can export audit data
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the audit log page
    And I attempt to export audit data
    Then the export action is available or triggered

  Scenario: Tenant admin views audit log
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the audit log page
    Then the audit log page loads successfully

  Scenario: Viewer can view audit log
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the audit log page
    Then the audit log page loads successfully
