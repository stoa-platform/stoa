"""Staging profile — reduced realistic dataset."""

from scripts.seeder.models import StepDefinition

STEPS: list[StepDefinition] = [
    StepDefinition(name="tenants", deps=[]),
    StepDefinition(name="gateway", deps=["tenants"]),
    StepDefinition(name="apis", deps=["tenants"]),
    StepDefinition(name="plans", deps=["tenants"]),
    StepDefinition(name="consumers", deps=["tenants", "plans"]),
    StepDefinition(name="mcp_servers", deps=["tenants"]),
    StepDefinition(name="security_posture", deps=["tenants"]),
]
