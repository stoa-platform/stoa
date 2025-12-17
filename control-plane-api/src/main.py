from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
import jwt
import boto3
import httpx
import logging

from src.config.settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description="Control Plane API for webMethods API Management Platform",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# JWT Validation
async def validate_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Validate JWT token from Cognito"""
    token = credentials.credentials
    try:
        # Decode without verification for now (in prod: verify with Cognito public keys)
        payload = jwt.decode(token, options={"verify_signature": False})

        tenant_id = payload.get("custom:tenant_id")
        role = payload.get("custom:role", "developer")
        groups = payload.get("cognito:groups", [])

        return {
            "user_id": payload.get("sub"),
            "tenant_id": tenant_id,
            "role": role,
            "groups": groups,
            "email": payload.get("email", "unknown"),
            "username": payload.get("cognito:username", "unknown")
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# RBAC Permission Checker
def check_permission(required_role: str):
    """Check if user has required permissions"""
    def permission_checker(user: Dict = Depends(validate_jwt)):
        # CPI and admins can do anything
        if "apim-cpi" in user["groups"] or "apim-admins" in user["groups"]:
            return user

        # Check specific role
        if user["role"] == required_role or f"apim-{required_role}" in user["groups"]:
            return user

        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return permission_checker


# webMethods Client
class WebMethodsClient:
    def __init__(self):
        self.base_url = settings.webmethods_url
        self.auth = (settings.webmethods_username, settings.webmethods_password)

    async def create_api(self, api_data: Dict, tenant_id: str) -> Dict:
        """Create API in webMethods and assign to tenant team"""
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            try:
                # Create API
                response = await client.post(
                    f"{self.base_url}/rest/apigateway/apis",
                    json=api_data,
                    auth=self.auth
                )

                if response.status_code not in [200, 201]:
                    logger.error(f"Failed to create API: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to create API in webMethods: {response.text}"
                    )

                result = response.json()
                api_id = result.get("apiResponse", {}).get("api", {}).get("id")

                if not api_id:
                    raise HTTPException(status_code=500, detail="API ID not found in response")

                # Assign to team (tenant)
                team_response = await client.put(
                    f"{self.base_url}/rest/apigateway/apis/{api_id}/team/{tenant_id}",
                    auth=self.auth
                )

                logger.info(f"API {api_id} created and assigned to tenant {tenant_id}")
                return result

            except httpx.RequestError as e:
                logger.error(f"Request error: {str(e)}")
                raise HTTPException(status_code=503, detail=f"webMethods unavailable: {str(e)}")

    async def list_apis(self, tenant_id: str) -> Dict:
        """List APIs for a specific tenant"""
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/rest/apigateway/apis",
                    params={"teamName": tenant_id},
                    auth=self.auth
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return {"api": []}

            except httpx.RequestError as e:
                logger.error(f"Request error: {str(e)}")
                raise HTTPException(status_code=503, detail=f"webMethods unavailable: {str(e)}")

    async def delete_api(self, api_id: str) -> bool:
        """Delete an API"""
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            try:
                response = await client.delete(
                    f"{self.base_url}/rest/apigateway/apis/{api_id}",
                    auth=self.auth
                )

                return response.status_code in [200, 204]

            except httpx.RequestError as e:
                logger.error(f"Request error: {str(e)}")
                raise HTTPException(status_code=503, detail=f"webMethods unavailable: {str(e)}")


# Initialize clients
wm_client = WebMethodsClient()
dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)


# ============= API Endpoints =============

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "APIM Control Plane API",
        "version": "1.0.0",
        "docs": "/docs"
    }


# ------------- Tenant Management (CPI only) -------------

@app.post("/v1/tenants", status_code=201)
async def create_tenant(
    tenant_data: Dict,
    user: Dict = Depends(check_permission("cpi"))
):
    """Create a new tenant (CPI only)"""
    tenant_id = tenant_data.get("tenant_id")

    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")

    # Create Team in webMethods
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.post(
            f"{wm_client.base_url}/rest/apigateway/teams",
            json={
                "name": f"tenant-{tenant_id}",
                "description": tenant_data.get("description", "")
            },
            auth=wm_client.auth
        )

        if response.status_code not in [200, 201]:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to create tenant: {response.text}"
            )

    # Store in DynamoDB
    table = dynamodb.Table(settings.dynamodb_tenants_table)
    table.put_item(Item={
        "tenant_id": tenant_id,
        "name": tenant_data.get("name", tenant_id),
        "created_by": user["email"],
        "status": "active"
    })

    logger.info(f"Tenant {tenant_id} created by {user['email']}")

    return {
        "tenant_id": tenant_id,
        "status": "created",
        "message": "Tenant created successfully"
    }


@app.get("/v1/tenants")
async def list_tenants(user: Dict = Depends(validate_jwt)):
    """List tenants (CPI sees all, others see only their tenant)"""
    if "apim-cpi" in user["groups"] or "apim-admins" in user["groups"]:
        # Return all tenants
        table = dynamodb.Table(settings.dynamodb_tenants_table)
        response = table.scan()
        return response.get('Items', [])
    else:
        # Return only user's tenant
        return [{"tenant_id": user["tenant_id"]}]


# ------------- APIs Management -------------

@app.post("/v1/tenants/{tenant_id}/apis", status_code=201)
async def create_api(
    tenant_id: str,
    api_data: Dict,
    user: Dict = Depends(check_permission("developer"))
):
    """Create a new API in the tenant"""
    # Verify user has access to this tenant
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    # Create API via webMethods
    result = await wm_client.create_api(api_data, f"tenant-{tenant_id}")

    # Store metadata in DynamoDB
    api_id = result.get("apiResponse", {}).get("api", {}).get("id")
    table = dynamodb.Table(settings.dynamodb_apis_table)
    table.put_item(Item={
        "api_id": api_id,
        "tenant_id": tenant_id,
        "created_by": user["email"],
        "status": "active"
    })

    return result


@app.get("/v1/tenants/{tenant_id}/apis")
async def list_apis(
    tenant_id: str,
    user: Dict = Depends(validate_jwt)
):
    """List all APIs in the tenant"""
    # Verify access
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    apis = await wm_client.list_apis(f"tenant-{tenant_id}")
    return apis


@app.delete("/v1/tenants/{tenant_id}/apis/{api_id}")
async def delete_api(
    tenant_id: str,
    api_id: str,
    user: Dict = Depends(check_permission("developer"))
):
    """Delete an API from the tenant"""
    # Verify ownership
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await wm_client.delete_api(api_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete API")

    return {"message": "API deleted successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
