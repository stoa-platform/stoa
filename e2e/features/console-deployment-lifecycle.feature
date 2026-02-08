@console @deployment @wip
Feature: Console - Deployment Lifecycle

  As a devops user,
  I want to deploy APIs to gateways and manage their lifecycle
  So that they are available to consumers.

  @wip
  Scenario: DevOps creates a new deployment
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateway deployments page
    And I click the create deployment button
    And I select an API to deploy
    And I select the target environment "development"
    And I submit the deployment form
    Then the deployment is created with status "pending" or "synced"

  @wip
  Scenario: DevOps views deployment list with status badges
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateway deployments page
    Then the deployments dashboard loads with sync status cards
    And the deployment list contains entries or an empty state

  @wip
  Scenario: DevOps views deployment detail with sync status
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateway deployments page
    And I click on the first deployment
    Then the deployment detail page loads
    And the deployment sync status is visible

  @wip
  Scenario: DevOps promotes deployment to staging
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateway deployments page
    And I click on the first deployment
    And I click the promote button
    And I confirm the promotion to "staging"
    Then the deployment target environment shows "staging"

  @wip @security
  Scenario: Viewer cannot create or promote deployments
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the gateway deployments page
    Then the create deployment button is not visible or disabled
    And the promote action is not available
