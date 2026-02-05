@console @admin
Feature: Console - Admin and Observability

  As a platform admin (anorak),
  I want to access admin pages and observability dashboards
  So that I can manage the platform and monitor its health.

  @critical @smoke
  Scenario: Admin accesses tenants page
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the tenants page
    Then the tenants list loads successfully

  Scenario: Admin accesses prospect management
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the admin prospects page
    Then the prospects page loads successfully

  Scenario: Admin views API monitoring dashboard
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the monitoring page
    Then the monitoring dashboard loads successfully

  Scenario: Admin views gateway observability
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the gateway observability page
    Then the observability dashboard loads with health metrics
