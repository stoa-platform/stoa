@console @consumers
Feature: Console - Consumer Management

  As a platform operator,
  I want to manage API consumers and their access
  So that I can control who can access published APIs.

  @smoke @critical
  Scenario: Admin views consumers list
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the consumers page
    Then the consumers list page loads successfully

  Scenario: Tenant admin views consumers
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the consumers page
    Then the consumers list page loads successfully

  Scenario: Admin navigates to consumer detail
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the consumers page
    And I click on the first consumer
    Then the consumer detail page loads

  Scenario: Viewer cannot create consumers
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the consumers page
    Then consumer write actions are hidden or disabled

  @isolation @security
  Scenario: IOI admin cannot see high-five consumers
    Given I am logged in to Console as "sorrento" from team "ioi"
    And the STOA Console is accessible
    When I navigate to the consumers page
    Then no consumers from tenant "high-five" are visible
