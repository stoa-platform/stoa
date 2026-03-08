@console @fapi @applications
Feature: Console - Applications Multi-Env Display + FAPI Key Management

  As a tenant admin on the Console,
  I want to see all applications across environments with env tabs
  And create FAPI applications with PEM upload or JWKS URL
  So that I can manage financial-grade applications securely.

  # -----------------------------------------------------------------------
  # Multi-Environment Display (CAB-1748 Phase 1)
  # -----------------------------------------------------------------------

  @smoke
  Scenario: Console applications page shows environment tabs
    Given I am logged in as "parzival" on the Console
    When I navigate to the console applications page
    Then I see environment tabs "All Environments", "Development", "Staging", "Production"

  Scenario: Switching env tab filters applications client-side
    Given I am logged in as "parzival" on the Console
    When I navigate to the console applications page
    And I click the "Development" environment tab
    Then only applications from "development" environment are displayed
    And the URL contains "env=development"

  Scenario: All Environments tab shows every application
    Given I am logged in as "parzival" on the Console
    When I navigate to the console applications page
    And I click the "All Environments" environment tab
    Then applications from all environments are displayed

  # -----------------------------------------------------------------------
  # FAPI Key Management (CAB-1748 Phase 2)
  # -----------------------------------------------------------------------

  @critical
  Scenario: FAPI Baseline profile shows key management section
    Given I am logged in as "parzival" on the Console
    When I navigate to the console applications page
    And I open the create application form
    And I select the "FAPI Baseline" security profile
    Then the FAPI key management section is visible
    And I see the "Upload PEM / JWK" and "JWKS URL" mode buttons

  Scenario: FAPI key mode toggle switches between PEM upload and JWKS URL
    Given I am logged in as "parzival" on the Console
    When I navigate to the console applications page
    And I open the create application form
    And I select the "FAPI Baseline" security profile
    Then the PEM upload textarea is visible by default
    When I click the "JWKS URL" mode button
    Then the JWKS URL input is visible
    And the PEM upload textarea is not visible
    When I click the "Upload PEM / JWK" mode button
    Then the PEM upload textarea is visible
    And the JWKS URL input is not visible

  Scenario: FAPI Advanced profile also shows key management
    Given I am logged in as "parzival" on the Console
    When I navigate to the console applications page
    And I open the create application form
    And I select the "FAPI Advanced" security profile
    Then the FAPI key management section is visible

  Scenario: Non-FAPI profiles do not show key management
    Given I am logged in as "parzival" on the Console
    When I navigate to the console applications page
    And I open the create application form
    And I select the "OAuth2 Public" security profile
    Then the FAPI key management section is not visible

  # -----------------------------------------------------------------------
  # RBAC (CAB-1748 Security)
  # -----------------------------------------------------------------------

  @security
  Scenario: Viewer cannot create applications
    Given I am logged in as "aech" on the Console
    When I navigate to the console applications page
    Then the "Create Application" button is not visible or disabled
