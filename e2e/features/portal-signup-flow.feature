@portal @signup @wip
Feature: Portal - Self-Service Signup Flow (CAB-1550)

  As a new developer,
  I want to sign up for STOA Platform via the portal,
  So that I can create my first API and start building.

  The signup flow is public (no auth required). It creates a trial tenant,
  provisions resources, and redirects to login. After login, the user
  creates their first API.

  Background:
    Given the STOA Portal is accessible

  @smoke @e2e
  Scenario: Full signup flow — register, wait for provisioning, login, create first API
    Given I am on the signup page
    When I fill in the signup form with:
      | field        | value                     |
      | name         | e2e-signup-test            |
      | display_name | E2E Signup Test Org        |
      | owner_email  | e2e-signup@example.com     |
      | company      | E2E Testing Inc            |
    And I submit the signup form
    Then the signup is accepted with status "provisioning"
    And I can poll the provisioning status until ready
    When I log in with the provisioned tenant credentials
    And I navigate to the API creation page
    And I create an API named "My First API" with endpoint "https://api.example.com"
    Then the API is visible in the catalog

  @smoke
  Scenario: Duplicate email is rejected
    Given I am on the signup page
    When I fill in the signup form with:
      | field        | value                     |
      | name         | e2e-duplicate-test         |
      | display_name | E2E Duplicate Test Org     |
      | owner_email  | e2e-signup@example.com     |
      | company      | E2E Testing Inc            |
    And I submit the signup form
    Then the signup is rejected with a duplicate error

  @smoke
  Scenario: Signup form validates required fields
    Given I am on the signup page
    When I submit the signup form without filling required fields
    Then I see validation errors for required fields

  @smoke
  Scenario: Signup via API — trial plan assigned by default
    When I call the self-service signup API with:
      | field        | value                     |
      | name         | e2e-api-signup             |
      | display_name | E2E API Signup Org         |
      | owner_email  | e2e-api-signup@example.com |
    Then the API responds with status 202
    And the response contains a poll_url
    And the plan is "trial"
