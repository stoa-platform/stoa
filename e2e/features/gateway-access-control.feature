@gateway @runtime @security
Feature: Gateway - Runtime access control

  @rpo @authorized @smoke
  Scenario: Authorized API call with active subscription
    Given I have an active subscription to "copper-key-api"
    And I have my valid API Key
    When I call "GET /api/v1/copper-key/quest"
    Then I receive a 200 response

  @rpo @unauthorized @negative
  Scenario: API call without subscription
    Given I do not have a subscription to "surveillance-api"
    When I call "GET /api/v1/surveillance/track" without API key
    Then I receive a 401 error

  @rpo @invalid-key @negative
  Scenario: API call with invalid API key
    Given I have an invalid API key
    When I call "GET /api/v1/copper-key/quest"
    Then I receive a 401 error
    And the error message contains "Invalid API key"

  @rpo @isolation @critical
  Scenario: IOI cannot access restricted High-Five APIs
    Given I am "sorrento" with an IOI subscription
    When I call "GET /api/v1/halliday-journal/entries"
    Then I receive a 403 error
    And the error message contains "Access denied"

  @rate-limiting
  Scenario: Rate limiting applied to API calls
    Given I have an active subscription with rate limit
    When I make many API calls rapidly
    Then some calls receive a 429 error
    And the error message contains "Rate limit exceeded"

  @token-expiry
  Scenario: Expired token rejected
    Given I have an expired access token
    When I call "GET /api/v1/catalog/apis"
    Then I receive a 401 error
    And the error message contains "Token expired"
