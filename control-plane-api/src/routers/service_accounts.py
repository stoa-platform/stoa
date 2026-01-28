# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Service Accounts Router for MCP Access.

Allows users to create OAuth2 Service Accounts for MCP tool access.
Each service account inherits the user's RBAC roles and tenant isolation.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from ..auth.dependencies import get_current_user, User
from ..services.keycloak_service import keycloak_service

router = APIRouter(prefix="/v1/service-accounts", tags=["Service Accounts"])


# Schemas
class ServiceAccountCreate(BaseModel):
    """Request to create a new service account"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Name for the service account (e.g., 'claude-desktop', 'cursor-ide')"
    )
    description: Optional[str] = Field(
        None,
        max_length=200,
        description="Optional description"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "claude-desktop",
                "description": "Service account for Claude Desktop MCP access"
            }
        }
    }


class ServiceAccountResponse(BaseModel):
    """Service account information (without secret)"""
    id: str
    client_id: str
    name: str
    description: Optional[str]
    enabled: bool


class ServiceAccountCreated(BaseModel):
    """Response when creating a service account (includes secret ONCE)"""
    id: str
    client_id: str
    client_secret: str = Field(
        ...,
        description="Client secret - shown only once! Store it securely."
    )
    name: str
    message: str = "Service account created. Save the client_secret - it won't be shown again!"

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "abc123",
                "client_id": "sa-acme-john-claude-desktop",
                "client_secret": "very-secret-value",
                "name": "claude-desktop",
                "message": "Service account created. Save the client_secret - it won't be shown again!"
            }
        }
    }


class ServiceAccountSecretRegenerated(BaseModel):
    """Response when regenerating a service account secret"""
    id: str
    client_id: str
    client_secret: str = Field(
        ...,
        description="New client secret - shown only once! Store it securely."
    )
    message: str = "Secret regenerated. Save the new client_secret - it won't be shown again!"


# Endpoints
@router.get(
    "",
    response_model=list[ServiceAccountResponse],
    summary="List my service accounts",
    description="List all service accounts owned by the current user."
)
async def list_service_accounts(
    current_user: User = Depends(get_current_user),
):
    """List all service accounts for the current user."""
    try:
        accounts = await keycloak_service.list_user_service_accounts(current_user.id)
        return accounts
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list service accounts: {str(e)}"
        )


@router.post(
    "",
    response_model=ServiceAccountCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create a service account",
    description="Create a new OAuth2 service account for MCP access. The account inherits your roles."
)
async def create_service_account(
    request: ServiceAccountCreate,
    current_user: User = Depends(get_current_user),
):
    """
    Create a new service account for MCP tool access.

    The service account will inherit:
    - Your RBAC roles (viewer, tenant-admin, etc.)
    - Your tenant isolation

    Use the returned client_id and client_secret in your MCP client configuration.
    """
    try:
        result = await keycloak_service.create_service_account(
            user_id=current_user.id,
            user_email=current_user.email,
            tenant_id=current_user.tenant_id or "default",
            name=request.name,
            description=request.description or "",
        )

        return ServiceAccountCreated(
            id=result["id"],
            client_id=result["client_id"],
            client_secret=result["client_secret"],
            name=result["name"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create service account: {str(e)}"
        )


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a service account",
    description="Delete a service account. Only the owner can delete their accounts."
)
async def delete_service_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a service account owned by the current user."""
    try:
        await keycloak_service.delete_service_account(account_id, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete service account: {str(e)}"
        )


@router.post(
    "/{account_id}/regenerate-secret",
    response_model=ServiceAccountSecretRegenerated,
    summary="Regenerate service account secret",
    description="Generate a new client secret. The old secret will be invalidated immediately."
)
async def regenerate_secret(
    account_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Regenerate the client secret for a service account.

    WARNING: This immediately invalidates the old secret.
    All MCP clients using this account will need to be updated.
    """
    try:
        # First verify ownership
        accounts = await keycloak_service.list_user_service_accounts(current_user.id)
        account = next((a for a in accounts if a["id"] == account_id), None)

        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service account not found or not owned by you"
            )

        new_secret = await keycloak_service.regenerate_client_secret(account_id)

        return ServiceAccountSecretRegenerated(
            id=account_id,
            client_id=account["client_id"],
            client_secret=new_secret,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate secret: {str(e)}"
        )
