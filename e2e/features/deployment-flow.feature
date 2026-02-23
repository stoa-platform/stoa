@deployment @wip
Feature: Deployment Flow Integration

  As a devops user,
  I want to create deployments via the API, view live logs, and rollback
  So that I can manage the full deployment lifecycle end-to-end.

  Background:
    Given the Control Plane API is accessible

  @smoke
  Scenario: Create deployment and verify status in history
    Given I am authenticated as "parzival" via API
    When I create a deployment for API "petstore" to environment "dev"
    Then the deployment is created with status "pending"
    And the deployment appears in the deployment list

  Scenario: View deployment logs via API
    Given I am authenticated as "parzival" via API
    And a deployment exists for API "petstore" in environment "dev"
    When I fetch the deployment logs
    Then the response contains a logs array
    And each log entry has a level and message

  Scenario: Rollback to a previous version
    Given I am authenticated as "parzival" via API
    And a successful deployment exists for API "petstore" in environment "dev"
    When I trigger a rollback on the deployment
    Then a new deployment is created with status "pending"
    And the new deployment references the original deployment

  Scenario: Failed deployment shows error status
    Given I am authenticated as "parzival" via API
    And a deployment exists for API "petstore" in environment "dev"
    When I update the deployment status to "failed" with error "gateway timeout"
    Then the deployment status is "failed"
    And the deployment error message contains "gateway timeout"

  Scenario: SSE event stream connects and receives heartbeat
    Given I am authenticated as "parzival" via API
    When I connect to the SSE event stream for tenant "high-five"
    Then the SSE connection is established
    And I receive at least one SSE event within 10 seconds

  Scenario: SSE stream delivers deploy events after deployment creation
    Given I am authenticated as "parzival" via API
    And I am connected to the SSE deploy event stream for tenant "high-five"
    When I create a deployment for API "petstore" to environment "dev"
    Then I receive a deploy event via SSE within 15 seconds
