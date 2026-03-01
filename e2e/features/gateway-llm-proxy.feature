@gateway @llm @ai
Feature: Gateway - LLM Proxy (CAB-1601)

  The STOA Gateway acts as a transparent LLM proxy, routing requests to
  upstream providers (Anthropic, Mistral, Azure OpenAI) while injecting
  tenant API keys, extracting token usage for metering, and enforcing
  access control via STOA subscription API keys.

  Endpoints:
    POST /v1/messages              — Anthropic format
    POST /v1/messages/count_tokens — Anthropic token counting
    POST /v1/chat/completions      — OpenAI-compatible format (Mistral, Azure)

  Background:
    Given the STOA Gateway is accessible

  # -----------------------------------------------------------------------
  # Authentication — these tests work without upstream LLM configuration
  # -----------------------------------------------------------------------

  @smoke @security
  Scenario: LLM proxy rejects request without API key
    When I call the LLM proxy "POST /v1/messages" without any API key
    Then the proxy returns status 401
    And the response body contains "Missing API key"

  @security
  Scenario: LLM proxy rejects request with invalid API key
    When I call the LLM proxy "POST /v1/messages" with API key "invalid-key-xyz"
    Then the proxy returns status 401
    And the response body contains "Invalid API key"

  @security
  Scenario: LLM proxy rejects chat completions without API key
    When I call the LLM proxy "POST /v1/chat/completions" without any API key
    Then the proxy returns status 401
    And the response body contains "Missing API key"

  @security
  Scenario: LLM proxy accepts x-api-key header
    When I call the LLM proxy "POST /v1/messages" with x-api-key header "invalid-key-xyz"
    Then the proxy returns status 401
    And the response body contains "Invalid API key"

  @security
  Scenario: LLM proxy accepts Authorization Bearer header
    When I call the LLM proxy "POST /v1/messages" with Bearer token "invalid-key-xyz"
    Then the proxy returns status 401
    And the response body contains "Invalid API key"

  # -----------------------------------------------------------------------
  # Format detection — verifies the gateway distinguishes API formats
  # -----------------------------------------------------------------------

  @smoke
  Scenario: LLM proxy detects Anthropic format from /v1/messages path
    Given I have a valid STOA LLM subscription API key
    When I send an Anthropic-format request to "/v1/messages"
    Then the response format is Anthropic or a proxy error
    And the proxy returns status other than 404

  @smoke
  Scenario: LLM proxy detects OpenAI format from /v1/chat/completions path
    Given I have a valid STOA LLM subscription API key
    When I send an OpenAI-format request to "/v1/chat/completions"
    Then the response format is OpenAI-compatible or a proxy error
    And the proxy returns status other than 404

  # -----------------------------------------------------------------------
  # Token counting endpoint
  # -----------------------------------------------------------------------

  Scenario: LLM proxy exposes token counting endpoint
    Given I have a valid STOA LLM subscription API key
    When I send a token count request to "/v1/messages/count_tokens"
    Then the proxy returns status other than 404

  # -----------------------------------------------------------------------
  # Error handling — oversized payload
  # -----------------------------------------------------------------------

  @security
  Scenario: LLM proxy rejects oversized request body
    Given I have a valid STOA LLM subscription API key
    When I send a request with a 11MB body to "/v1/messages"
    Then the proxy returns status 400
