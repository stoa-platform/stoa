@wip @observability
Feature: Observability Data Pipeline
  As a platform administrator
  I want to verify that the observability stack is functioning end-to-end
  So that I can ensure gateway logs, metrics, and traces are available.

  Background:
    Given I am logged in to Console as "anorak" platform admin

  @smoke
  Scenario: Gateway logs reach OpenSearch
    Given the STOA Console is accessible
    When I navigate to the gateway observability page
    Then the observability dashboard loads with health metrics
    And I can see gateway log entries from the last hour

  @critical
  Scenario: Tenant-scoped log filtering works
    Given the STOA Console is accessible
    And I have selected tenant "oasis"
    When I view the tenant observability dashboard
    Then I only see log entries for tenant "oasis"
    And no entries from other tenants are visible

  @critical
  Scenario: Grafana dashboards load with data
    Given Grafana is accessible
    When I open the "Gateway Unified" dashboard
    Then all panels render without "No data" errors
    And the request rate panel shows non-zero values

  Scenario: Trace correlation links work
    Given Grafana is accessible
    And there are recent gateway traces
    When I click a trace_id link in Loki logs
    Then Tempo opens with the corresponding trace
    And the trace shows the full request span

  Scenario: ISM policies are active
    Given OpenSearch is accessible
    When I check ISM policy status for "stoa-gw-*" indices
    Then all indices have an active ISM policy
    And no indices are in "failed" ISM state
