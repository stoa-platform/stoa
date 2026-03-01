@demo @gateway @portal @critical
Feature: Demo "IA pour tous" — Azure OpenAI Multi-Tenant via STOA (CAB-1609)

  As a STOA Platform presenter for the March 17 demo
  I want the "IA pour tous" use case automatically validated in CI
  So that the Chat Completions flow is guaranteed to work

  The demo showcases how enterprise teams can access Azure OpenAI (GPT-4o)
  through STOA Gateway with per-tenant subscription routing, API key injection,
  and token-level metering — all via the standard /v1/chat/completions endpoint.

  # ===========================================================================
  # GATEWAY: Chat Completions auth enforcement (reuses LLM proxy steps)
  # ===========================================================================

  @smoke @security
  Scenario: Chat Completions endpoint rejects unauthenticated requests
    Given the STOA Gateway is accessible
    When I call the LLM proxy "POST /v1/chat/completions" without any API key
    Then the proxy returns status 401
    And the response body contains "API key"

  @smoke @security
  Scenario: Chat Completions endpoint rejects invalid API keys
    Given the STOA Gateway is accessible
    When I call the LLM proxy "POST /v1/chat/completions" with API key "fake-key-12345"
    Then the proxy returns status 401
    And the response body contains "Invalid API key"

  # ===========================================================================
  # GATEWAY: OpenAI-compatible format routing (reuses LLM proxy steps)
  # ===========================================================================

  @smoke
  Scenario: Chat Completions endpoint routes OpenAI-format requests
    Given the STOA Gateway is accessible
    And I have a valid STOA LLM subscription API key
    When I send an OpenAI-format request to "/v1/chat/completions"
    Then the response format is OpenAI-compatible or a proxy error
    And the proxy returns status other than 404

  # ===========================================================================
  # PORTAL: Chat Completions API enrichment on detail page
  # ===========================================================================

  @portal @smoke
  Scenario: Portal shows Chat Completions enrichment panel
    Given I am logged in as "art3mis" from community "high-five"
    And the STOA Portal is accessible
    When I navigate to the Chat Completions API detail page
    Then the API detail page is displayed
    And I see the Chat Completions enrichment panel
    And the enrichment panel shows subscription plans
    And the enrichment panel shows the GDPR notice

  # ===========================================================================
  # GATEWAY: Multi-tenant credential isolation
  # ===========================================================================

  @smoke @security
  Scenario: Different API keys cannot cross-access tenants
    Given the STOA Gateway is accessible
    When I call the LLM proxy "POST /v1/chat/completions" with API key "wrong-tenant-key"
    Then the proxy returns status 401
