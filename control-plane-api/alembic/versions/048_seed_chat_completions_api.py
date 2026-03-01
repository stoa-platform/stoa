"""Seed Chat Completions API and subscription plans for Portal (CAB-1616).

Inserts:
- 1 api_catalog entry for "IA — Chat Completions (GPT-4o)" (portal_published=True)
- 2 plans: alpha-exploration (1000 tok/min), beta-production (5000 tok/min)

Revision ID: 048_seed_chat_completions
Revises: 047_contract_deprecation
Create Date: 2026-03-01
"""

import sqlalchemy as sa
from alembic import op

revision = "048_seed_chat_completions"
down_revision = "047_contract_deprecation"
branch_labels = None
depends_on = None

# Deterministic UUIDs (uuid5 from DNS namespace + seed string)
API_CATALOG_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
PLAN_ALPHA_ID = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
PLAN_BETA_ID = "c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f"

TENANT_ID = "oasis"
API_ID = "chat-completions-gpt4o"
API_NAME = "IA \u2014 Chat Completions (GPT-4o)"


def upgrade() -> None:
    # 1. Insert API catalog entry
    op.execute(
        sa.text("""
            INSERT INTO api_catalog (id, tenant_id, api_id, api_name, version, status, category, tags,
                                     portal_published, audience, metadata, openapi_spec, target_gateways)
            VALUES (
                :id, :tenant_id, :api_id, :api_name, :version, :status, :category,
                :tags::jsonb, :portal_published, :audience, :metadata::jsonb,
                :openapi_spec::jsonb, :target_gateways::jsonb
            )
            ON CONFLICT (tenant_id, api_id) DO UPDATE SET
                api_name = EXCLUDED.api_name,
                portal_published = EXCLUDED.portal_published,
                status = EXCLUDED.status,
                category = EXCLUDED.category,
                tags = EXCLUDED.tags,
                metadata = EXCLUDED.metadata,
                openapi_spec = EXCLUDED.openapi_spec
        """),
        {
            "id": API_CATALOG_ID,
            "tenant_id": TENANT_ID,
            "api_id": API_ID,
            "api_name": API_NAME,
            "version": "1.0.0",
            "status": "published",
            "category": "ai",
            "tags": '["ia", "llm", "azure-openai", "self-service"]',
            "portal_published": True,
            "audience": "public",
            "metadata": """{
                "description": "API de chat completions compatible OpenAI, routee vers Azure OpenAI (GPT-4o). Supporte le streaming SSE et les quotas par plan.",
                "display_name": "IA \u2014 Chat Completions (GPT-4o)",
                "owner": "Equipe Data & IA",
                "backend_url": "https://stoa-aoai.openai.azure.com"
            }""",
            "openapi_spec": """{
                "openapi": "3.0.3",
                "info": {
                    "title": "Chat Completions API",
                    "version": "1.0.0",
                    "description": "OpenAI-compatible chat completions endpoint routed through STOA Gateway to Azure OpenAI."
                },
                "paths": {
                    "/v1/chat/completions": {
                        "post": {
                            "summary": "Create chat completion",
                            "description": "Generates a chat completion for the given messages. Supports streaming via SSE.",
                            "operationId": "createChatCompletion",
                            "requestBody": {
                                "required": true,
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["model", "messages"],
                                            "properties": {
                                                "model": {"type": "string", "example": "gpt-4o"},
                                                "messages": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "required": ["role", "content"],
                                                        "properties": {
                                                            "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                                            "content": {"type": "string"}
                                                        }
                                                    }
                                                },
                                                "stream": {"type": "boolean", "default": false},
                                                "temperature": {"type": "number", "minimum": 0, "maximum": 2, "default": 1},
                                                "max_tokens": {"type": "integer", "minimum": 1}
                                            }
                                        }
                                    }
                                }
                            },
                            "responses": {
                                "200": {"description": "Chat completion response"},
                                "401": {"description": "Missing or invalid API key"},
                                "429": {"description": "Rate limit exceeded"}
                            },
                            "security": [{"ApiKeyAuth": []}]
                        }
                    }
                },
                "components": {
                    "securitySchemes": {
                        "ApiKeyAuth": {
                            "type": "apiKey",
                            "in": "header",
                            "name": "Authorization",
                            "description": "Bearer token: Authorization: Bearer <STOA_API_KEY>"
                        }
                    }
                }
            }""",
            "target_gateways": "[]",
        },
    )

    # 2. Insert Plan: Alpha — Exploration (1000 tokens/min)
    op.execute(
        sa.text("""
            INSERT INTO plans (id, slug, name, description, tenant_id,
                               rate_limit_per_minute, requires_approval, auto_approve_roles,
                               status, pricing_metadata, created_by)
            VALUES (
                :id, :slug, :name, :description, :tenant_id,
                :rate_limit_per_minute, :requires_approval, :auto_approve_roles::json,
                :status, :pricing_metadata::json, :created_by
            )
            ON CONFLICT (tenant_id, slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                rate_limit_per_minute = EXCLUDED.rate_limit_per_minute
        """),
        {
            "id": PLAN_ALPHA_ID,
            "slug": "alpha-exploration",
            "name": "Projet Alpha \u2014 Exploration",
            "description": "Ideal pour le prototypage et les premiers tests d\u2019integration. 1000 tokens/min, 10 req/min.",
            "tenant_id": TENANT_ID,
            "rate_limit_per_minute": 10,
            "requires_approval": False,
            "auto_approve_roles": "null",
            "status": "active",
            "pricing_metadata": '{"tokens_per_minute": 1000, "requests_per_minute": 10, "namespace": "alpha"}',
            "created_by": "alembic-seed",
        },
    )

    # 3. Insert Plan: Beta — Production (5000 tokens/min)
    op.execute(
        sa.text("""
            INSERT INTO plans (id, slug, name, description, tenant_id,
                               rate_limit_per_minute, requires_approval, auto_approve_roles,
                               status, pricing_metadata, created_by)
            VALUES (
                :id, :slug, :name, :description, :tenant_id,
                :rate_limit_per_minute, :requires_approval, :auto_approve_roles::json,
                :status, :pricing_metadata::json, :created_by
            )
            ON CONFLICT (tenant_id, slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                rate_limit_per_minute = EXCLUDED.rate_limit_per_minute
        """),
        {
            "id": PLAN_BETA_ID,
            "slug": "beta-production",
            "name": "Projet Beta \u2014 Production",
            "description": "Pour les workloads de production avec des quotas eleves. 5000 tokens/min, 50 req/min.",
            "tenant_id": TENANT_ID,
            "rate_limit_per_minute": 50,
            "requires_approval": False,
            "auto_approve_roles": "null",
            "status": "active",
            "pricing_metadata": '{"tokens_per_minute": 5000, "requests_per_minute": 50, "namespace": "beta"}',
            "created_by": "alembic-seed",
        },
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM plans WHERE id IN (:alpha_id, :beta_id)"),
        {"alpha_id": PLAN_ALPHA_ID, "beta_id": PLAN_BETA_ID},
    )
    op.execute(
        sa.text("DELETE FROM api_catalog WHERE id = :id"),
        {"id": API_CATALOG_ID},
    )
