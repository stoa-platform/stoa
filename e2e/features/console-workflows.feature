@console @workflow
Feature: Onboarding Workflows (CAB-593)
  As a platform administrator
  I want to configure onboarding workflows per tenant
  So that user/consumer registrations follow the right approval process

  Background:
    Given the user is authenticated as "cpi-admin"
    And the user navigates to "/workflows"

  Scenario: View workflow templates tab
    Then the "Templates" tab should be active
    And the page should display a list of workflow templates

  Scenario: Create an auto-approve workflow template
    When the user clicks "Create Template"
    And fills in the template form:
      | field          | value                 |
      | name           | Fast User Onboarding  |
      | workflow_type  | user_registration     |
      | mode           | auto                  |
    And submits the form
    Then a success notification should appear
    And the template "Fast User Onboarding" should appear in the list

  Scenario: Start a workflow instance
    Given a workflow template "Fast User Onboarding" exists for the tenant
    When the user switches to the "Instances" tab
    And clicks "Start Workflow"
    And fills in the instance form:
      | field         | value              |
      | template      | Fast User Onboarding |
      | subject_id    | new-user-42        |
      | subject_email | user42@example.com |
    And submits the form
    Then a success notification should appear
    And the instance for "new-user-42" should appear with status "completed"

  Scenario: Approve a manual workflow step
    Given a manual workflow template "Enterprise Review" exists
    And a pending workflow instance "pending-instance" exists
    When the user switches to the "Instances" tab
    And clicks "Approve" on "pending-instance"
    Then the instance status should change to "approved"

  Scenario: Viewer cannot create templates
    Given the user is authenticated as "viewer"
    And the user navigates to "/workflows"
    Then the "Create Template" button should not be visible
    And the "Approve" button should not be visible on any instance
