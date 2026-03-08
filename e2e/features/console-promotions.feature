@console @promotions
Feature: Console - Promotion Flow

  As a devops user,
  I want to promote APIs across environments (dev → staging → production)
  So that I can manage the lifecycle of API deployments with audit trails
  and approval gates.

  Background:
    Given the STOA Console is accessible

  # -----------------------------------------------------------------------
  # Page Visibility & Navigation
  # -----------------------------------------------------------------------

  @smoke @critical
  Scenario: DevOps sees the Promotions page
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    Then the promotions page loads successfully
    And the page title shows "Promotions"

  @critical
  Scenario: Promotions page shows filter controls
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    Then I see the tenant selector
    And I see the status filter dropdown
    And I see the API filter dropdown

  # -----------------------------------------------------------------------
  # Create Promotion Dialog
  # -----------------------------------------------------------------------

  @critical
  Scenario: DevOps can open the create promotion dialog
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    And I click the "New Promotion" button
    Then the create promotion dialog is visible
    And the dialog shows an API selector
    And the dialog shows the promotion path selectors
    And the dialog shows a message field

  Scenario: Create promotion dialog validates chain dev to staging
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    And I click the "New Promotion" button
    Then the default promotion path is "Dev" to "Staging"
    And no chain validation error is shown

  Scenario: Create promotion dialog can be closed
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    And I click the "New Promotion" button
    Then the create promotion dialog is visible
    When I close the promotion dialog
    Then the create promotion dialog is not visible

  # -----------------------------------------------------------------------
  # Promotion Pipeline Indicator
  # -----------------------------------------------------------------------

  Scenario: Promotion pipeline shows environment chain
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    And promotions exist for the selected tenant
    Then the promotion pipeline indicator is visible
    And the pipeline shows "DEV", "STAGING", and "PRODUCTION" labels

  # -----------------------------------------------------------------------
  # Promotion Table
  # -----------------------------------------------------------------------

  Scenario: Promotion table shows column headers
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    And promotions exist for the selected tenant
    Then the promotions table shows headers "API / Message", "Path", "Status", "Requested By", "Approved By", "Actions"

  Scenario: Promotion row can be expanded for diff
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    And promotions exist for the selected tenant
    And I click on a promotion row to expand it
    Then the expanded promotion section is visible

  # -----------------------------------------------------------------------
  # Status Filters
  # -----------------------------------------------------------------------

  Scenario: Filter promotions by status
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    And I select promotion status filter "Pending"
    Then the promotions list updates with filtered results

  # -----------------------------------------------------------------------
  # RBAC — 4-Eyes Principle
  # -----------------------------------------------------------------------

  @security @critical
  Scenario: Viewer cannot see the New Promotion button
    Given I am logged in to Console as "aech" from team "high-five"
    When I navigate to the promotions page
    Then the "New Promotion" button is not visible

  @security
  Scenario: Viewer can still see the promotions list
    Given I am logged in to Console as "aech" from team "high-five"
    When I navigate to the promotions page
    Then the promotions page loads successfully

  # -----------------------------------------------------------------------
  # Empty State
  # -----------------------------------------------------------------------

  Scenario: Empty state is shown when no promotions exist
    Given I am logged in to Console as "parzival" from team "high-five"
    When I navigate to the promotions page
    And no promotions exist for the selected tenant
    Then the empty state message is displayed
