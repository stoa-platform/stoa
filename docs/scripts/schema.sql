-- STOA Impact Analysis Database Schema
-- Source of truth for inter-component dependency tracking
-- Auto-generates DEPENDENCIES.md and SCENARIOS.md

CREATE TABLE IF NOT EXISTS components (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('service', 'frontend', 'gateway', 'infra', 'external', 'cli')),
    tech_stack TEXT,
    repo_path TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived', 'deprecated')),
    description TEXT
);

CREATE TABLE IF NOT EXISTS contracts (
    id TEXT PRIMARY KEY,
    source_component TEXT NOT NULL REFERENCES components(id),
    target_component TEXT NOT NULL REFERENCES components(id),
    type TEXT NOT NULL CHECK(type IN ('rest-api', 'grpc', 'kafka-event', 'oidc-flow', 'db-read', 'db-write', 'metrics', 'sse', 'websocket', 'admin-api', 'crd-watch')),
    contract_ref TEXT NOT NULL,
    schema_type TEXT CHECK(schema_type IN ('pydantic', 'typescript', 'rust-struct', 'openapi', 'json-rpc', 'avro', 'protobuf', 'none')),
    schema_path TEXT,
    typed INTEGER DEFAULT 0,
    description TEXT
);

CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    actor TEXT NOT NULL,
    priority TEXT DEFAULT 'P1' CHECK(priority IN ('P0', 'P1', 'P2')),
    test_level TEXT DEFAULT 'none' CHECK(test_level IN ('none', 'unit', 'integration', 'e2e')),
    test_in_ci INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scenario_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id TEXT NOT NULL REFERENCES scenarios(id),
    step_order INTEGER NOT NULL,
    component_id TEXT NOT NULL REFERENCES components(id),
    action TEXT NOT NULL,
    contract_id TEXT REFERENCES contracts(id),
    expected_result TEXT
);

CREATE TABLE IF NOT EXISTS risks (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL CHECK(severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    title TEXT NOT NULL,
    description TEXT,
    impacted_components TEXT,
    impacted_contracts TEXT,
    recommendation TEXT,
    status TEXT DEFAULT 'open' CHECK(status IN ('open', 'mitigated', 'accepted', 'resolved')),
    ticket_ref TEXT
);

-- Views
CREATE VIEW IF NOT EXISTS impact_analysis AS
SELECT
    c.id AS contract_id,
    c.contract_ref,
    c.source_component,
    c.target_component,
    c.typed,
    s.id AS scenario_id,
    s.name AS scenario_name,
    s.priority,
    s.test_level,
    s.test_in_ci
FROM contracts c
JOIN scenario_steps ss ON ss.contract_id = c.id
JOIN scenarios s ON s.id = ss.scenario_id
ORDER BY s.priority, s.name;

CREATE VIEW IF NOT EXISTS untyped_contracts AS
SELECT c.id, c.contract_ref, c.source_component, c.target_component, c.type
FROM contracts c
WHERE c.typed = 0
ORDER BY c.type;

CREATE VIEW IF NOT EXISTS untested_scenarios AS
SELECT s.id, s.name, s.priority, s.test_level, s.test_in_ci
FROM scenarios s
WHERE s.test_in_ci = 0
ORDER BY s.priority;

CREATE VIEW IF NOT EXISTS dependency_matrix AS
SELECT
    source_component,
    target_component,
    GROUP_CONCAT(DISTINCT type) AS contract_types,
    COUNT(*) AS contract_count
FROM contracts
GROUP BY source_component, target_component;

CREATE VIEW IF NOT EXISTS component_risk_score AS
SELECT
    comp.id,
    comp.name,
    COUNT(DISTINCT c_out.id) AS outgoing_contracts,
    COUNT(DISTINCT c_in.id) AS incoming_contracts,
    COUNT(DISTINCT ss.scenario_id) AS scenarios_involved,
    COUNT(DISTINCT CASE WHEN c_out.typed = 0 THEN c_out.id END) AS untyped_outgoing
FROM components comp
LEFT JOIN contracts c_out ON c_out.source_component = comp.id
LEFT JOIN contracts c_in ON c_in.target_component = comp.id
LEFT JOIN scenario_steps ss ON ss.component_id = comp.id
GROUP BY comp.id
ORDER BY scenarios_involved DESC;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_contracts_source ON contracts(source_component);
CREATE INDEX IF NOT EXISTS idx_contracts_target ON contracts(target_component);
CREATE INDEX IF NOT EXISTS idx_contracts_ref ON contracts(contract_ref);
CREATE INDEX IF NOT EXISTS idx_steps_scenario ON scenario_steps(scenario_id);
CREATE INDEX IF NOT EXISTS idx_steps_component ON scenario_steps(component_id);
CREATE INDEX IF NOT EXISTS idx_steps_contract ON scenario_steps(contract_id);
CREATE INDEX IF NOT EXISTS idx_risks_severity ON risks(severity);
