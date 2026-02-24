@federation @gateway
Feature: Gateway - Federation Routing

  As a sub-account agent,
  I want my requests routed through the federation master account
  So that policies and quotas apply per my sub-account.

  Background:
    Given the STOA Gateway is accessible

  @smoke
  Scenario: Sub-account can call allowed tools
    Given I have a federation sub-account API key
    And the sub-account is allowed to call "echo-tool"
    When I call the tool "echo-tool" via the gateway
    Then the response status is 200
    And the response includes the tool result

  Scenario: Sub-account is blocked from disallowed tools
    Given I have a federation sub-account API key
    And the sub-account is not allowed to call "restricted-tool"
    When I call the tool "restricted-tool" via the gateway
    Then the response status is 403
    And the response includes "tool not allowed"

  Scenario: Sub-account requests are metered under master account
    Given I have a federation sub-account API key
    When I call the tool "echo-tool" via the gateway
    Then the response status is 200
    And the response header includes "X-Federation-Master-Id"

  Scenario: Revoked sub-account gets 401
    Given I have a revoked federation sub-account API key
    When I call the tool "echo-tool" via the gateway
    Then the response status is 401
    And the response includes "sub-account revoked"

  Scenario: Federation request includes sub-account context
    Given I have a federation sub-account API key
    When I call the tool "echo-tool" via the gateway
    Then the response status is 200
    And the response header includes "X-Sub-Account-Id"
