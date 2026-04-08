"""Prod profile — bootstrap only (admin tenant + gateway)."""

from scripts.seeder.models import StepDefinition

STEPS: list[StepDefinition] = [
    StepDefinition(name="tenants", deps=[]),
    StepDefinition(name="gateway", deps=["tenants"]),
]
