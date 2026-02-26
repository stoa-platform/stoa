@integration @critical
Feature: Contract Lifecycle — CP API CRUD + Status Transitions

  Full contract lifecycle through the Control Plane API:
  create (draft) → publish → deprecate, with binding management.

  Background:
    Given the CP API and gateway are both reachable
    And I obtain a CP API token as "parzival"

  Scenario: Create a draft contract via CP API
    When I create contract "e2e-lifecycle-test" with version "1.0.0" via CP API
    Then the integration response status is 201
    And the CP API contract "e2e-lifecycle-test" has status "draft"

  Scenario: Publish a contract via CP API
    Given I create contract "e2e-publish-test" with version "1.0.0" via CP API
    When I update contract "e2e-publish-test" status to "published" via CP API
    Then the integration response status is 200
    And the CP API contract "e2e-publish-test" has status "published"

  Scenario: Enable REST binding on a published contract
    Given I create contract "e2e-binding-test" with version "1.0.0" via CP API
    And I update contract "e2e-binding-test" status to "published" via CP API
    When I enable "rest" binding for contract "e2e-binding-test" via CP API
    Then the integration response status is 200
    And the CP API contract "e2e-binding-test" has binding "rest" enabled

  Scenario: Deprecate a published contract via CP API
    Given I create contract "e2e-deprecate-test" with version "1.0.0" via CP API
    And I update contract "e2e-deprecate-test" status to "published" via CP API
    When I deprecate contract "e2e-deprecate-test" with reason "Replaced by v2" via CP API
    Then the integration response status is 200
    And the CP API contract "e2e-deprecate-test" has status "deprecated"

  Scenario: Delete a contract via CP API
    Given I create contract "e2e-delete-test" with version "1.0.0" via CP API
    When I delete contract "e2e-delete-test" via CP API
    Then the integration response status is 200
    And the CP API contract "e2e-delete-test" no longer exists

  Scenario: List contracts with status filter via CP API
    Given I create contract "e2e-filter-draft" with version "1.0.0" via CP API
    And I create contract "e2e-filter-pub" with version "1.0.0" via CP API
    And I update contract "e2e-filter-pub" status to "published" via CP API
    When I list contracts with status "published" via CP API
    Then the integration response status is 200
    And the contract list contains "e2e-filter-pub"
    And the contract list does not contain "e2e-filter-draft"
