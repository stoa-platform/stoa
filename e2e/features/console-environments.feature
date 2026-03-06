@console @environments
Feature: Console - Environment Chrome & Switching

  As a platform operator,
  I want a visible environment chrome bar at the top of every Console page
  So that I always know which environment I am working in and am protected
  from accidental writes to production.

  # -----------------------------------------------------------------------
  # Chrome Bar Visibility
  # -----------------------------------------------------------------------

  @critical @smoke
  Scenario: Environment chrome bar is visible on Console pages
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I look at the Console header
    Then the environment chrome bar is visible with the active environment name

  @critical
  Scenario: Chrome bar shows correct color for each environment
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I look at the Console header
    Then the chrome bar uses green for Development
    And the chrome bar uses amber for Staging
    And the chrome bar uses red for Production

  # -----------------------------------------------------------------------
  # Environment Switching
  # -----------------------------------------------------------------------

  @critical
  Scenario: Environment list shows multiple environments
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I open the environment switcher dropdown
    Then I see at least 2 environments in the list

  Scenario: Switching to Staging updates the chrome bar
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

  # -----------------------------------------------------------------------
  # Read-Only Enforcement
  # -----------------------------------------------------------------------

  @critical
  Scenario: Production environment shows READ ONLY badge in chrome bar
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I switch to the "Production" environment
    Then the chrome bar displays a "READ ONLY" badge

  Scenario: Gateways page has no read-only guards (global scope)
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I switch to the "Production" environment
    And I navigate to the gateways page
    Then the "Register Gateway" button is not disabled
