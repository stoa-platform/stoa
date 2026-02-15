@demo @showcase @critical
Feature: Demo Showcase - Ready Player One Live Demo Validation

  As a STOA Platform presenter
  I want the demo flow automatically validated in CI
  So that the Feb 24 demo is guaranteed to work

  # ===========================================================================
  # SCENARIO 1: Full Demo Flow — Portal Browse to Gateway Call
  # ===========================================================================
  @demo-showcase-1
  Scenario: Portal user browses catalog and calls the gateway
    Given I am logged in as "art3mis" from tenant "high-five"
    And the STOA Portal is accessible
    When I access the API catalog
    Then I see APIs in the catalog
    When I click on the first API result
    Then the API detail page is displayed
    When I navigate to my subscriptions
    Then the subscriptions page is displayed
    # Gateway HTTP calls (no browser needed)
    Given the gateway is healthy
    When I make a test API call with my credentials
    Then I receive a successful HTTP 200 response

  # ===========================================================================
  # SCENARIO 2: Multi-Tenant Tool Isolation
  # ===========================================================================
  @demo-showcase-2
  Scenario: Tenants see only their own tools via the gateway
    Given the gateway is healthy
    When I list MCP tools as "parzival" from tenant "high-five"
    Then I receive a valid tool listing
    When I list MCP tools as "sorrento" from tenant "ioi"
    Then I receive a valid tool listing
    And the two tool listings are different

  # ===========================================================================
  # SCENARIO 3: Gateway Health & Discovery
  # ===========================================================================
  @demo-showcase-3
  Scenario: Gateway health and MCP discovery endpoints respond correctly
    Given the gateway is healthy
    When I call the gateway discovery endpoint
    Then the gateway returns its configuration

  # ===========================================================================
  # ARCHIVED: Original aspirational scenarios (shadow mode, semantic cache,
  # HuggingFace, compliance audit) — deferred until backend features are built.
  # See git history for the full original file.
  # ===========================================================================
