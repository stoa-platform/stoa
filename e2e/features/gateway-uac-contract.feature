@gateway @uac @wip
Feature: UAC Contract Deployment Pipeline

  As a tenant admin,
  I want to deploy a UAC contract to the gateway
  So that REST routes and MCP tools are automatically generated from the contract spec.

  Background:
    Given the STOA Gateway is accessible

  @smoke @critical
  Scenario: Deploy a UAC contract and verify REST route generation
    Given I have a valid UAC contract spec for tenant "high-five"
    When I deploy the contract to the gateway via POST /admin/contracts
    Then the gateway responds with 200 or 201
    And the contract appears in GET /admin/contracts
    And REST routes are generated for the contract endpoints
    When I delete the contract via DELETE /admin/contracts/:key
    Then the contract is no longer in GET /admin/contracts
