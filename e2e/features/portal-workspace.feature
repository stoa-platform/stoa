@portal @workspace
Feature: Portal - Workspace Tabs

  As an API consumer,
  I want to access all my workspace resources from a single page
  So that I can manage subscriptions, applications, and contracts efficiently.

  @smoke @critical
  Scenario: User accesses workspace
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal workspace
    Then the workspace page loads with tabs

  Scenario: User navigates to subscriptions tab
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal workspace
    And I click on the subscriptions workspace tab
    Then the subscriptions tab content is displayed

  Scenario: User navigates to applications tab
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal workspace
    And I click on the applications workspace tab
    Then the applications tab content is displayed

  Scenario: User navigates to contracts tab
    Given I am logged in as "parzival" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the portal workspace
    And I click on the contracts workspace tab
    Then the contracts tab content is displayed
