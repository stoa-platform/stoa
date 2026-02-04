@demo @portal @critical
Feature: Demo - Portal Consumer Path

  As an API consumer (Art3mis from HIGH-FIVE)
  I want to discover, test, and subscribe to an API
  So that I can integrate it into my application

  @demo-portal
  Scenario: Consumer discovers and tests an API
    # 1. Login OIDC → dashboard
    Given I am logged in as "art3mis" from community "high-five"
    When I access the API catalog
    Then I see APIs in the catalog

    # 2. Search → results
    When I search for an API by name from the catalog
    Then the search results are not empty

    # 3. Click API → detail + spec
    When I click on the first API result
    Then the API detail page is displayed
    And I see the API specification section

    # 4. Try API → testing interface
    When I click the try this API button
    Then I see the API testing interface

    # 5. Navigate subscriptions → subscriptions page visible
    When I navigate to my subscriptions
    Then the subscriptions page is displayed

    # 6. Test call → HTTP 200
    When I make a test API call with my credentials
    Then I receive a successful HTTP 200 response
