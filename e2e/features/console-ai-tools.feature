@console @ai-tools
Feature: Console - AI Tools and Applications

  As a tenant admin or platform admin,
  I want to access AI Tool management pages
  So that I can manage tool catalog, subscriptions, usage, and applications.

  @smoke @critical
  Scenario: Tenant admin views AI Tool Catalog
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the AI Tool Catalog page
    Then the AI Tool Catalog page loads successfully

  @smoke
  Scenario: Tenant admin views AI Tool subscriptions
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the AI Tool subscriptions page
    Then the AI Tool subscriptions page loads successfully

  @smoke
  Scenario: Tenant admin views AI Usage Dashboard
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the AI Usage Dashboard page
    Then the AI Usage Dashboard page loads successfully

  Scenario: Admin searches AI Tool Catalog
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the AI Tool Catalog page
    And I search for a tool in the catalog
    Then the tool search results are displayed

  @smoke
  Scenario: Tenant admin views Applications page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Applications page
    Then the Applications page loads successfully
