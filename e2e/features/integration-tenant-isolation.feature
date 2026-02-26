@integration @critical
Feature: Tenant Isolation — Contracts Scoped per Tenant

  Each tenant can only see and manage their own contracts.
  CPI-admin (anorak) can see contracts across all tenants.

  Background:
    Given the CP API and gateway are both reachable

  Scenario: Tenant admin sees only their own contracts
    Given I obtain a CP API token as "parzival"
    And I create contract "e2e-iso-highfive" with version "1.0.0" via CP API
    When I obtain a CP API token as "sorrento"
    And I list all contracts via CP API
    Then the contract list does not contain "e2e-iso-highfive"

  Scenario: CPI-admin sees contracts from all tenants
    Given I obtain a CP API token as "parzival"
    And I create contract "e2e-iso-visible" with version "1.0.0" via CP API
    When I obtain a CP API token as "anorak"
    And I list all contracts via CP API
    Then the contract list contains "e2e-iso-visible"

  Scenario: Tenant admin cannot access another tenant's contract by ID
    Given I obtain a CP API token as "parzival"
    And I create contract "e2e-iso-private" with version "1.0.0" via CP API
    When I obtain a CP API token as "sorrento"
    And I fetch contract "e2e-iso-private" by ID via CP API
    Then the integration response status is 403 or 404

  Scenario: MCP generated tools are scoped to requesting tenant
    Given I obtain a CP API token as "parzival"
    And I create contract "e2e-iso-mcp-hf" with version "1.0.0" via CP API
    And I update contract "e2e-iso-mcp-hf" status to "published" via CP API
    And I enable "mcp" binding for contract "e2e-iso-mcp-hf" via CP API
    And I generate MCP tools for contract "e2e-iso-mcp-hf" via CP API
    When I query MCP generated tools for tenant "ioi" via CP API
    Then the generated tools list does not include contract "e2e-iso-mcp-hf"
