@integration @chat-settings
Feature: Chat Settings API — CRUD and Source Header Enforcement

  As the STOA platform,
  I want to enforce chat settings via the control plane API
  So that per-app chat enable/disable and budget limits are respected.

  Background:
    Given the CP API and gateway are both reachable

  @smoke @critical
  Scenario: Tenant admin can read chat settings via API
    Given I obtain a chat settings token as "parzival"
    When I GET chat settings for my tenant via CP API
    Then the chat settings response is 200
    And the chat settings response contains console and portal flags

  @smoke
  Scenario: Tenant admin can update chat settings via API
    Given I obtain a chat settings token as "parzival"
    When I PUT chat settings with console enabled and budget 80000 via CP API
    Then the chat settings response is 200
    And the updated chat settings reflect the new values

  Scenario: Tenant admin can disable console chat via API
    Given I obtain a chat settings token as "parzival"
    When I PUT chat settings with console disabled via CP API
    Then the chat settings response is 200
    And the chat settings show console chat disabled

  Scenario: Tenant admin can re-enable console chat via API
    Given I obtain a chat settings token as "parzival"
    When I PUT chat settings with console enabled via CP API
    Then the chat settings response is 200
    And the chat settings show console chat enabled

  @security @regression
  Scenario: Viewer cannot update chat settings via API
    Given I obtain a chat settings token as "aech"
    When I PUT chat settings with console disabled via CP API
    Then the chat settings response is 403

  @security @regression
  Scenario: Unauthenticated request to chat settings is rejected
    Given I have no authentication token
    When I GET chat settings for tenant "high-five" without auth via CP API
    Then the chat settings response is 401

  # CAB-1852/1853: X-Chat-Source header tracking
  @smoke @regression
  Scenario: Chat API accepts requests with X-Chat-Source console header
    Given I obtain a chat settings token as "parzival"
    When I call the chat conversations API with X-Chat-Source "console" via CP API
    Then the chat source request is accepted

  @regression
  Scenario: Chat API accepts requests with X-Chat-Source portal header
    Given I obtain a chat settings token as "parzival"
    When I call the chat conversations API with X-Chat-Source "portal" via CP API
    Then the chat source request is accepted

  Scenario: CPI admin can read chat settings for any tenant
    Given I obtain a chat settings token as "anorak"
    When I GET chat settings for tenant "high-five" via CP API
    Then the chat settings response is 200
    And the chat settings response contains console and portal flags
