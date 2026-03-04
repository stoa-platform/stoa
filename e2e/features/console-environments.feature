@console @environments
Feature: Console - Environment Switcher

  As a platform operator,
  I want to view and switch between environments in the Console header
  So that I can manage multiple backends from a single UI.

  @critical @smoke
  Scenario: Environment switcher is visible in Console header
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I look at the Console header
    Then the environment switcher is visible with a colored dot and label

  @critical
  Scenario: Environment list shows multiple environments
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the environment switcher dropdown
    Then I see at least 2 environments in the list

  Scenario: Switching to Staging updates the header indicator
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the environment switcher dropdown
    And I select "Staging" from the environment list
    Then the environment indicator shows "Staging"

  Scenario: Active environment persists after page reload
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the environment switcher dropdown
    And I select "Staging" from the environment list
    And I reload the page
    Then the environment indicator shows "Staging"

  Scenario: Production environment shows read-only indicator
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the environment switcher dropdown
    Then the "Production" environment shows a read-only badge
