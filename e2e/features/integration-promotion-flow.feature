@integration @critical
Feature: Promotion Flow — API-Level Functional Tests (CAB-1706)

  Functional integration tests for the GitOps promotion pipeline:
  promote dev→staging, rollback a completed promotion, and verify
  portal env badges via the portal API.

  Background:
    Given the CP API and gateway are both reachable
    And I obtain a CP API token as "parzival"

  @smoke
  Scenario: Promote an API from dev to staging
    When I list tenant APIs via CP API
    And I create a promotion from "dev" to "staging" with message "E2E promote test"
    Then the promotion response status is 201
    And the promotion status is "pending"
    And the promotion source is "dev" and target is "staging"
    When I approve the pending promotion
    Then the promotion response status is 200
    And the promotion status is "promoting"
    When I mark the promotion as completed
    Then the promotion response status is 200
    And the promotion status is "promoted"

  Scenario: Rollback a completed promotion
    When I list tenant APIs via CP API
    And I create a promotion from "dev" to "staging" with message "E2E rollback setup"
    And I approve the pending promotion
    And I mark the promotion as completed
    Then the promotion status is "promoted"
    When I rollback the promotion with message "E2E rollback test"
    Then the promotion response status is 201
    And the rollback promotion source is "staging" and target is "dev"
    And the rollback promotion status is "pending"

  Scenario: Portal API returns environment deployment badges
    When I fetch portal APIs list
    Then the portal response status is 200
    And the portal APIs response contains a deployments field
