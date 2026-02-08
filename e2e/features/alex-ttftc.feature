@portal @ttftc @rpo @freelance
Feature: Alex Freelance — Time to First Tool Call (TTFTC)
  As a freelance developer discovering STOA for the first time,
  I want to go from Portal landing to making my first API call,
  So that the platform proves it delivers value quickly.

  Background:
    Given the STOA Portal is accessible

  @smoke @critical
  Scenario: Alex onboarding journey — full TTFTC
    # Step 1 — Land on Portal (unauthenticated)
    Given I start the TTFTC timer
    When I navigate to the Portal homepage
    Then the Portal loads successfully
    And I record TTFTC step "01-landing" with screenshot

    # Step 2 — Browse catalogue (unauthenticated or redirected)
    When I attempt to browse the API catalog
    Then I see catalog content or a login prompt
    And I record TTFTC step "02-catalog-browse" with screenshot

    # Step 3 — Login as Alex via Keycloak
    When I login as "alex" using auth fixtures
    Then I am on an authenticated page
    And I record TTFTC step "03-login" with screenshot

    # Step 4 — Browse catalogue (authenticated)
    When I navigate to the API catalog as authenticated user
    Then I see APIs or MCP tools in the catalog
    And I record TTFTC step "04-catalog-authenticated" with screenshot

    # Step 5 — Select an API or MCP tool
    When I click on the first available catalog item
    Then I see the item detail page
    And I record TTFTC step "05-item-detail" with screenshot

    # Step 6 — Subscribe or request credentials
    When I attempt to subscribe to the current item
    Then the subscribe action completes or is documented as friction
    And I record TTFTC step "06-subscribe" with screenshot

    # Step 7 — First tool call (TTFTC endpoint)
    When I attempt my first API or tool call
    Then the call response is recorded
    And I record TTFTC step "07-first-call" with screenshot
    And I stop the TTFTC timer
    And I generate the TTFTC friction report
    And the TTFTC is under 600 seconds
