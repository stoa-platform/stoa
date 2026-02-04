@portal @ttftc @rpo @freelance
Feature: Alex Freelance — Time to First Tool Call (TTFTC)
  As a freelance developer discovering STOA for the first time,
  I want to go from Portal landing to browsing API details,
  So that the platform proves it delivers value quickly.

  Background:
    Given the STOA Portal is accessible

  @smoke @critical
  Scenario: Alex onboarding journey — discover APIs
    # Step 1 — Land on Portal
    Given I start the TTFTC timer
    When I navigate to the Portal homepage
    Then I see the Portal landing page
    And I record step timing "01-landing"

    # Step 2 — Login via Keycloak
    When I click the login button
    And I authenticate as "alex" via Keycloak
    Then I am redirected to the Portal dashboard
    And I record step timing "02-login"

    # Step 3 — Browse the API catalog
    When I access the API catalog
    Then I see APIs in the catalog
    And I take a screenshot "alex/03-catalog"
    And I record step timing "03-catalog-browse"

    # Step 4 — Search for an API
    When I search for an available API
    And I take a screenshot "alex/04-search-results"
    And I record step timing "04-search"

    # Step 5 — View API details
    When I click on the first API in results
    Then I see the API detail page
    And I take a screenshot "alex/05-api-detail"
    And I record step timing "05-api-detail"
    And I stop the TTFTC timer
    And the TTFTC is under 120 seconds
