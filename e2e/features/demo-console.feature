@demo @console @critical
Feature: Demo - Console Admin Path

  As an API owner (Parzival, tenant-admin of HIGH-FIVE)
  I want to manage applications, subscriptions, and monitor API usage
  So that I can control access to my APIs

  @demo-console
  Scenario: Admin navigates console and monitors APIs
    # 7. Login Console OIDC → dashboard admin
    Given I am logged in to Console as "parzival" from team "high-five"
    When I access the Console dashboard
    Then I see the Console admin dashboard

    # 8. List applications → subscription management page
    When I navigate to subscription management
    Then I see the subscription requests list

    # 9. Verify application management is ready
    Then the application management controls are visible

    # 10. View API monitoring → metrics visible
    When I navigate to the analytics dashboard
    Then I see the API monitoring page
