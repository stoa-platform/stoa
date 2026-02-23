# Demo Scenarios

Industry-vertical demo scenarios for STOA Platform.

## Quick Start

```bash
# List available scenarios
./scripts/demo/setup.sh --list

# Preview what a scenario will create
./scripts/demo/setup.sh --scenario=citadelle --dry-run

# Set up a scenario (requires running CP API + Keycloak)
export ADMIN_PASSWORD=<keycloak-admin-password>
./scripts/demo/setup.sh --scenario=citadelle

# Tear down a scenario
./scripts/demo/teardown.sh --scenario=citadelle
```

## Available Scenarios

| Scenario | Theme | Compliance | Description |
|----------|-------|------------|-------------|
| `citadelle` | Public Sector | RGS, SecNumCloud | French ministry API interoperability |
| `middle-earth-banking` | Financial Services | DORA, NIS2 | Fantasy bank with regulatory posture |

## Scenario Structure

Each scenario lives in its own directory:

```
scripts/demo/scenarios/<name>/
  scenario.yaml     # Manifest: tenant, APIs, personas, plans, compliance
  README.md         # Walkthrough and talking points

tenants/<tenant-id>/
  tenant.yaml       # GitOps tenant definition
  apis/<api-id>/
    api.yaml        # API catalog entry
    openapi.yaml    # OpenAPI 3.0.3 spec
```

The `scenario.yaml` manifest is the entry point. It references the GitOps
tenant directory for API definitions, making scenarios compatible with
STOA's catalog sync feature.

## Creating a New Scenario

1. Copy the schema: `cp scenarios/scenario-schema.yaml scenarios/<name>/scenario.yaml`
2. Create the tenant dir: `mkdir -p tenants/<tenant-id>/apis/<api-id>`
3. Define APIs with `api.yaml` + `openapi.yaml` per API
4. Add compliance disclaimers (see `DISCLAIMER-TEMPLATE.md`)
5. Test: `./scripts/demo/setup.sh --scenario=<name> --dry-run`

## Compliance Rules

All scenarios referencing regulatory frameworks MUST include disclaimers.
See `DISCLAIMER-TEMPLATE.md` for approved templates.

- Use "supports compliance posture" (never "certified" or "compliant")
- No real company names or data
- All personas are fictional
