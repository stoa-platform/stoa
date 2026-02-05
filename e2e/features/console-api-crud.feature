@console @api-crud
Feature: Console - API CRUD operations

  As an API Provider using the Console,
  I want to create, edit, and delete APIs
  So that I can manage my organization's API catalog.

  @critical @smoke
  Scenario: Tenant admin creates an API
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I access the API list
    And I create an API named "E2E Test API"
    Then the API "E2E Test API" appears in the list

  Scenario: Tenant admin edits an API display name
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I access the API list
    And I select the API "E2E Test API"
    And I edit the API display name to "E2E Test API Updated"
    Then I see the updated API name "E2E Test API Updated"

  Scenario: Tenant admin deletes an API
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I access the API list
    And I select the API "E2E Test API Updated"
    And I delete the current API
    And I confirm the deletion
    Then the API "E2E Test API Updated" is no longer in the list

  @security
  Scenario: Viewer cannot create APIs
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I access the API list
    Then the Create API button is not visible or disabled
