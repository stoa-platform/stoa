@console @access-requests
Feature: Console - Admin Access Requests

  As a platform admin,
  I want to manage enterprise access requests
  So that I can approve or reject access to the platform.

  @smoke @critical
  Scenario: Platform admin views Access Requests page
    Given I am logged in to Console as "anorak" platform admin
    And the STOA Console is accessible
    When I navigate to the Admin Access Requests page
    Then the Admin Access Requests page loads successfully

  @rbac
  Scenario: Tenant admin views Access Requests page
    Given I am logged in to Console as "parzival" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Admin Access Requests page
    Then the Admin Access Requests page loads successfully

  @rbac
  Scenario: Viewer is denied access to Access Requests page
    Given I am logged in to Console as "aech" from team "high-five"
    And the STOA Console is accessible
    When I navigate to the Admin Access Requests page
    Then I receive an access denied error
