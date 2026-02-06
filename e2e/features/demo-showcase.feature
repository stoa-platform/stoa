@demo @showcase @critical
Feature: Demo Showcase - Ready Player One Demo Scenarios

  As a STOA Platform presenter
  I want to demonstrate all key features through Ready Player One themed tenants
  So that enterprise clients can see the full platform capabilities

  Background:
    Given the Ready Player One demo tenants are configured
      | tenant     | description           | tier       |
      | high-five  | Fintech startup       | starter    |
      | ioi        | Enterprise legacy     | enterprise |
      | oasis      | AI-first company      | enterprise |

  # ===========================================================================
  # SCENARIO 1: Legacy-to-MCP Bridge (IOI Tenant)
  # ===========================================================================
  @demo-1 @shadow-mode @legacy
  Scenario: Legacy API discovered via Shadow Mode and exposed as MCP tool
    # Setup: Legacy API is running with no documentation
    Given tenant "ioi" has an undocumented legacy ERP API
    And the STOA gateway is in shadow mode for "ioi"

    # Shadow capture
    When traffic flows through the legacy ERP API
    Then the gateway captures request/response patterns
    And a UAC draft is automatically generated

    # Human review
    When the admin reviews the UAC draft
    Then the API schema is correctly inferred
    And PII fields are detected and marked for masking

    # Promote to MCP
    When the admin promotes the UAC to production
    Then the legacy API is exposed as MCP tool "ioi:erp-inventory"
    And Claude can invoke the tool via MCP protocol

  # ===========================================================================
  # SCENARIO 2: Fintech Agent (HIGH-FIVE Tenant)
  # ===========================================================================
  @demo-2 @fintech @semantic-cache
  Scenario: Fintech agent uses crypto and payment APIs with semantic caching
    Given I am logged in as "parzival" from tenant "high-five"
    And the following MCP tools are available:
      | tool                    | api        |
      | high-five:crypto-prices | CoinGecko  |
      | high-five:payment-charge| Stripe     |
      | high-five:send-alert    | Webhook    |

    # First crypto query - cache MISS
    When I invoke tool "high-five:crypto-prices" with:
      | ids           | bitcoin,ethereum |
      | vs_currencies | usd              |
    Then the response contains current prices
    And the semantic cache records a MISS
    And the response latency is recorded

    # Same query - cache HIT (semantic matching)
    When I invoke tool "high-five:crypto-prices" with:
      | ids           | bitcoin,ethereum |
      | vs_currencies | usd              |
    Then the response is served from cache
    And the semantic cache records a HIT
    And the latency is significantly lower

    # Similar query - cache HIT (semantic similarity)
    When I invoke tool "high-five:crypto-prices" with:
      | ids           | ethereum,bitcoin |
      | vs_currencies | usd              |
    Then the response is served from cache
    And the queries are matched by semantic similarity

    # Payment operation - audit trail
    When I invoke tool "high-five:payment-charge" with:
      | amount      | 1000     |
      | currency    | usd      |
      | description | Test payment |
    Then the payment is processed successfully
    And an audit log entry is created
    And the audit log contains tenant and user information

    # Send alert
    When I invoke tool "high-five:send-alert" with:
      | message  | BTC price alert: crossed $70k |
      | severity | info                           |
    Then the alert is sent successfully

  # ===========================================================================
  # SCENARIO 3: Multi-Tenant Isolation
  # ===========================================================================
  @demo-3 @isolation @security
  Scenario: Tenants are strictly isolated with different policies
    # Setup different rate limits
    Given tenant "high-five" has rate limit of 1000 requests per minute
    And tenant "ioi" has rate limit of 100 requests per minute

    # HIGH-FIVE operates normally
    When "parzival" from "high-five" makes 50 API requests
    Then all requests succeed
    And no rate limit is triggered

    # IOI hits rate limit faster
    When "sorrento" from "ioi" makes 150 API requests
    Then the first 100 requests succeed
    And the remaining requests are rate limited
    And the rate limit response includes retry-after header

    # Cross-tenant access denied
    When "parzival" from "high-five" attempts to access "ioi" tools
    Then the access is denied with 403 Forbidden
    And the denial is logged in the audit trail

    # Each tenant only sees their own tools
    When "parzival" lists available MCP tools
    Then only "high-five" tools are visible
    And "ioi" tools are not listed
    And "oasis" tools are not listed

  # ===========================================================================
  # SCENARIO 4: DevOps Workflow (OASIS Tenant)
  # ===========================================================================
  @demo-4 @devops @github
  Scenario: AI agent automates DevOps workflow via MCP tools
    Given I am logged in as "anorak" from tenant "oasis"
    And the following MCP tools are available:
      | tool                     | api    |
      | oasis:github-list-issues | GitHub |
      | oasis:github-create-issue| GitHub |
      | oasis:github-create-pr   | GitHub |
      | oasis:slack-notify       | Slack  |

    # List issues
    When I invoke tool "oasis:github-list-issues" with:
      | owner | stoa-platform |
      | repo  | stoa          |
      | state | open          |
    Then I receive a list of open issues
    And the response includes issue titles and labels

    # Create fix issue
    When I invoke tool "oasis:github-create-issue" with:
      | owner | stoa-platform      |
      | repo  | stoa               |
      | title | Fix: Demo bug      |
      | body  | Automated fix      |
    Then the issue is created successfully
    And I receive the issue number

    # Create PR
    When I invoke tool "oasis:github-create-pr" with:
      | owner | stoa-platform      |
      | repo  | stoa               |
      | title | Fix demo bug       |
      | head  | fix/demo-bug       |
      | base  | main               |
    Then the PR is created successfully

    # Notify team
    When I invoke tool "oasis:slack-notify" with:
      | message | PR created for demo fix |
      | channel | #devops                 |
    Then the Slack notification is sent

    # Verify audit trail
    When I check the audit trail for "oasis"
    Then all 4 tool invocations are logged
    And each entry includes timestamp and user

  # ===========================================================================
  # SCENARIO 5: AI Pipeline Bridge (OASIS Tenant)
  # ===========================================================================
  @demo-5 @ai @ml @huggingface
  Scenario: AI agent uses ML inference APIs with token tracking
    Given I am logged in as "anorak" from tenant "oasis"
    And the following AI tools are available:
      | tool                       | model                    |
      | oasis:sentiment-analysis   | distilbert-sst2          |
      | oasis:text-classification  | bart-large-mnli          |
      | oasis:summarize-text       | bart-large-cnn           |

    # Sentiment analysis
    When I invoke tool "oasis:sentiment-analysis" with:
      | inputs | I absolutely love this product! It's amazing! |
    Then the sentiment is classified as "positive"
    And the confidence score is above 0.9
    And token usage is tracked

    # Zero-shot classification
    When I invoke tool "oasis:text-classification" with:
      | inputs         | The server is down and users cannot login |
      | candidate_labels | ["bug", "feature request", "question"] |
    Then the text is classified as "bug"
    And token usage is tracked

    # Summarization
    When I invoke tool "oasis:summarize-text" with:
      | inputs | [long text to summarize] |
    Then a concise summary is returned
    And the summary length is within configured limits
    And token usage is tracked

    # Check token budget
    When I check the token budget for "oasis"
    Then total tokens used is reported
    And remaining daily budget is shown
    And cost estimate is provided

  # ===========================================================================
  # SCENARIO 6: Compliance & Audit Trail (IOI Tenant)
  # ===========================================================================
  @demo-6 @compliance @audit @rssi
  Scenario: Enterprise compliance features for RSSI demonstration
    Given I am logged in as "sorrento" from tenant "ioi"
    And the IOI tenant has compliance features enabled:
      | feature        | enabled |
      | GDPR           | true    |
      | SOX            | true    |
      | PII Masking    | true    |
      | Audit Logging  | true    |

    # PII Masking demo
    When I invoke tool "ioi:crm-customers" to list customers
    Then email addresses are masked as "***@***.***"
    And the original PII is not visible in logs

    # Full audit trail
    When I request the audit trail export
    Then I receive a complete audit log containing:
      | field       | present |
      | timestamp   | true    |
      | user_id     | true    |
      | tenant_id   | true    |
      | action      | true    |
      | resource    | true    |
      | ip_address  | true    |

    # Tenant isolation proof
    When I attempt to query another tenant's data
    Then the query fails with 403 Forbidden
    And the failed attempt is logged in audit trail
    And no cross-tenant data is exposed

    # Policy enforcement
    When I attempt an operation that violates OPA policy
    Then the operation is blocked
    And the policy violation reason is returned
    And the violation is logged

    # Compliance report
    When I generate a compliance report
    Then the report includes:
      | section             | included |
      | Data residency      | true     |
      | Access patterns     | true     |
      | Policy violations   | true     |
      | PII access log      | true     |
