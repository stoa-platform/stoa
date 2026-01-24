"""AWX service for Ansible automation"""
import logging
from typing import Optional
import httpx

from ..config import settings

logger = logging.getLogger(__name__)

class AWXService:
    """Service for AWX/Ansible Tower operations"""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url: str = ""

    async def connect(self):
        """Initialize AWX connection"""
        self._base_url = settings.AWX_URL.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/v2",
            headers={
                "Authorization": f"Bearer {settings.AWX_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        logger.info(f"Connected to AWX at {self._base_url}")

    async def disconnect(self):
        """Close AWX connection"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated request to AWX"""
        if not self._client:
            raise RuntimeError("AWX not connected")

        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    # Job Template operations
    async def get_job_templates(self) -> list[dict]:
        """List available job templates"""
        result = await self._request("GET", "/job_templates/")
        return result.get("results", [])

    async def get_job_template(self, template_id: int) -> dict:
        """Get job template by ID"""
        return await self._request("GET", f"/job_templates/{template_id}/")

    async def get_job_template_by_name(self, name: str) -> Optional[dict]:
        """Get job template by name"""
        result = await self._request("GET", "/job_templates/", params={"name": name})
        templates = result.get("results", [])
        return templates[0] if templates else None

    # Job operations
    async def launch_job(
        self,
        template_id: int,
        extra_vars: Optional[dict] = None,
        limit: Optional[str] = None
    ) -> dict:
        """
        Launch a job from a template.

        Args:
            template_id: Job template ID
            extra_vars: Extra variables to pass to the playbook
            limit: Limit execution to specific hosts

        Returns:
            Job details including job ID
        """
        payload = {}
        if extra_vars:
            payload["extra_vars"] = extra_vars
        if limit:
            payload["limit"] = limit

        return await self._request(
            "POST",
            f"/job_templates/{template_id}/launch/",
            json=payload
        )

    async def get_job(self, job_id: int) -> dict:
        """Get job status and details"""
        return await self._request("GET", f"/jobs/{job_id}/")

    async def get_job_stdout(self, job_id: int) -> str:
        """Get job output/logs"""
        if not self._client:
            raise RuntimeError("AWX not connected")

        response = await self._client.get(
            f"/jobs/{job_id}/stdout/",
            params={"format": "txt"}
        )
        response.raise_for_status()
        return response.text

    async def cancel_job(self, job_id: int) -> bool:
        """Cancel a running job"""
        try:
            await self._request("POST", f"/jobs/{job_id}/cancel/")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False

    # Deployment-specific operations
    async def deploy_api(
        self,
        tenant_id: str,
        api_id: str,
        api_name: str,
        environment: str,
        version: str,
        backend_url: str,
        openapi_spec: str = ""
    ) -> dict:
        """
        Launch API deployment job.

        This calls the deploy-api job template with the necessary variables.
        """
        template = await self.get_job_template_by_name("Deploy API")
        if not template:
            raise ValueError("Job template 'Deploy API' not found")

        extra_vars = {
            "tenant_id": tenant_id,
            "api_id": api_id,
            "api_name": api_name,
            "environment": environment,
            "version": version,
            "backend_url": backend_url,
            "openapi_spec": openapi_spec,
        }

        # Limit to specific environment host
        limit = f"webmethods_{environment}"

        job = await self.launch_job(template["id"], extra_vars, limit)
        logger.info(f"Launched deployment job {job['id']} for API {api_name}")
        return job

    async def rollback_api(
        self,
        tenant_id: str,
        api_id: str,
        environment: str,
        target_version: str
    ) -> dict:
        """Launch API rollback job"""
        template = await self.get_job_template_by_name("Rollback API")
        if not template:
            raise ValueError("Job template 'Rollback API' not found")

        extra_vars = {
            "tenant_id": tenant_id,
            "api_id": api_id,
            "environment": environment,
            "target_version": target_version,
        }

        job = await self.launch_job(template["id"], extra_vars)
        logger.info(f"Launched rollback job {job['id']} for API {api_id}")
        return job

    async def provision_tenant(
        self,
        tenant_id: str,
        tenant_name: str,
        users: list[dict],
        environments: list[str] = None
    ) -> dict:
        """
        Launch tenant provisioning job.

        Creates Keycloak groups, users, and K8s namespaces for a new tenant.

        Args:
            tenant_id: Unique tenant identifier
            tenant_name: Display name of the tenant
            users: List of users to create with roles
            environments: List of environments (default: ['dev', 'staging'])
        """
        template = await self.get_job_template_by_name("Provision Tenant")
        if not template:
            raise ValueError("Job template 'Provision Tenant' not found")

        extra_vars = {
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "users": users,
            "environments": environments or ["dev", "staging"]
        }

        job = await self.launch_job(template["id"], extra_vars)
        logger.info(f"Launched provisioning job {job['id']} for tenant {tenant_id}")
        return job

    async def register_api_gateway(
        self,
        tenant_id: str,
        api_name: str,
        api_version: str,
        openapi_url: str,
        backend_url: str,
        oidc_enabled: bool = True,
        rate_limit: int = 100
    ) -> dict:
        """
        Register API in webMethods Gateway.

        Imports API from OpenAPI spec, configures OIDC and rate limiting policies,
        and activates the API.

        Args:
            tenant_id: Tenant identifier
            api_name: API name
            api_version: API version
            openapi_url: URL to OpenAPI specification
            backend_url: Backend service URL
            oidc_enabled: Enable OIDC authentication
            rate_limit: Rate limit requests per minute
        """
        template = await self.get_job_template_by_name("Register API Gateway")
        if not template:
            raise ValueError("Job template 'Register API Gateway' not found")

        extra_vars = {
            "tenant_id": tenant_id,
            "api_name": api_name,
            "api_version": api_version,
            "openapi_url": openapi_url,
            "backend_url": backend_url,
            "oidc_enabled": oidc_enabled,
            "rate_limit": rate_limit
        }

        job = await self.launch_job(template["id"], extra_vars)
        logger.info(f"Launched API registration job {job['id']} for {api_name}")
        return job

    # Inventory operations
    async def get_inventories(self) -> list[dict]:
        """List inventories"""
        result = await self._request("GET", "/inventories/")
        return result.get("results", [])

    async def get_hosts(self, inventory_id: int) -> list[dict]:
        """List hosts in an inventory"""
        result = await self._request("GET", f"/inventories/{inventory_id}/hosts/")
        return result.get("results", [])

# Global instance
awx_service = AWXService()
