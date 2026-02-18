@skills @console
Feature: Console - Skills Management

  As a tenant admin,
  I want to manage agent skills in the Console
  So that I can configure context injection for AI agent conversations.

  @smoke
  Scenario: Admin sees skills list page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Skills page
    Then the Skills page loads successfully

  Scenario: Admin creates a global skill
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Skills page
    And I create a skill named "E2E Test Skill" with scope "global"
    Then the skill "E2E Test Skill" appears in the list

  Scenario: Admin edits skill priority
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Skills page
    And I edit the skill "E2E Test Skill" priority to "90"
    Then the skill "E2E Test Skill" shows priority "90"

  Scenario: Admin deletes a skill
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Skills page
    And I delete the skill "E2E Test Skill"
    And I confirm the deletion
    Then the skill "E2E Test Skill" is no longer in the list

  @security
  Scenario: Viewer cannot create skills
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Skills page
    Then the Add Skill button is not visible

  Scenario: Resolution preview shows resolved skills
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Skills page
    And I open the Resolution Preview panel
    And I resolve skills for tool "code-review"
    Then the resolution results are displayed
