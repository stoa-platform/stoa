@portal @ttftc @rpo @freelance
Feature: Alex Freelance — Time to First Tool Call (TTFTC)
  As a freelance developer discovering STOA for the first time,
  I want to go from Portal landing to my first API call,
  So that the platform proves it delivers value in under 10 minutes.

  Background:
    Given the STOA Portal is accessible

  @smoke @critical
  Scenario: Alex full onboarding journey — TTFTC benchmark
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
    When I search for "copper"
    Then the results contain "copper"
    And I take a screenshot "alex/04-search-results"
    And I record step timing "04-search"

    # Step 5 — View API details
    When I click on the first API in results
    Then I see the API detail page
    And I take a screenshot "alex/05-api-detail"
    And I record step timing "05-api-detail"

    # Step 6 — Subscribe to the API
    When I click on "Subscribe"
    And I confirm the subscription
    Then the subscription is created with status "active"
    And I take a screenshot "alex/06-subscribed"
    And I record step timing "06-subscribe"

    # Step 7 — Retrieve API key
    When I navigate to my subscriptions
    And I click on "View Key" for a subscription
    Then I can see the API key information
    And I take a screenshot "alex/07-api-key"
    And I record step timing "07-api-key"

    # Step 8 — Invoke the API (first tool call)
    When I invoke the subscribed API with my key
    Then I receive a successful API response
    And I take a screenshot "alex/08-first-call"
    And I record step timing "08-first-tool-call"
    And I stop the TTFTC timer
    And the TTFTC is under 600 seconds
