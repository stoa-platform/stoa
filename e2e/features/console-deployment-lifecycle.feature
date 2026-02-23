@console @deployment
Feature: Console - Deployment Lifecycle

  As a devops user,
  I want to view deployment history, filter deployments, and rollback
  So that I can manage the lifecycle of API deployments across environments.

  Background:
    Given the STOA Console is accessible

  @smoke @critical
  Scenario: DevOps views deployment history tab
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the deployments page
    And I click the "Deployment History" tab
    Then the deployment history table is visible
    And the deployment filters are displayed

  Scenario: DevOps filters deployments by environment
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the deployments page
    And I click the "Deployment History" tab
    And I select environment filter "Dev"
    Then the deployment list updates with filtered results

  Scenario: DevOps filters deployments by status
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the deployments page
    And I click the "Deployment History" tab
    And I select status filter "Success"
    Then the deployment list updates with filtered results

  Scenario: DevOps initiates rollback on a successful deployment
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the deployments page
    And I click the "Deployment History" tab
    And I click the rollback button on a successful deployment
    Then the rollback confirmation dialog appears
    And the dialog mentions "Rollback Deployment"

  @security
  Scenario: Viewer cannot see rollback button
    Given I am logged in to Console as "aech" from team "high-five"
    When I navigate to the deployments page
    And I click the "Deployment History" tab
    Then the rollback button is not visible

  Scenario: DevOps expands deployment row to view details
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the deployments page
    And I click the "Deployment History" tab
    And I click on a deployment row to expand it
    Then the deployment detail panel is visible
    And the detail panel shows the deploy progress indicator
    And the detail panel shows a log viewer section

  Scenario: Expanded deployment shows spec hash
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the deployments page
    And I click the "Deployment History" tab
    And I click on a deployment row to expand it
    Then the deployment detail panel is visible
    And the detail panel shows the spec hash
