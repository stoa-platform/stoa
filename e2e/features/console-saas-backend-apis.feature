@console @saas @wip
Feature: Console - Backend APIs Management

  As a tenant admin,
  I want to register and manage backend APIs
  So that I can expose them through the STOA gateway as SaaS tools.

  @smoke @critical
  Scenario: Admin views Backend APIs page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Backend APIs page
    Then the Backend APIs page loads successfully

  Scenario: Admin registers a backend API
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Backend APIs page
    And I register a backend API named "E2E Test API" with URL "https://api.example.com/v1"
    Then the backend API "E2E Test API" appears in the list

  Scenario: Admin toggles backend API status
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Backend APIs page
    And I toggle the status of backend API "E2E Test API"
    Then the backend API "E2E Test API" status changes

  Scenario: Admin deletes a backend API
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Backend APIs page
    And I delete the backend API "E2E Test API"
    And I confirm the deletion
    Then the backend API "E2E Test API" is no longer in the list

  @security
  Scenario: Viewer cannot register backend APIs
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Backend APIs page
    Then the Register API button is not visible or disabled
