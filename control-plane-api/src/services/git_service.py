"""GitLab service for GitOps operations"""
import logging
from typing import Optional
import yaml
import gitlab
from gitlab.v4.objects import Project

from ..config import settings

logger = logging.getLogger(__name__)


def _normalize_api_data(raw_data: dict) -> dict:
    """
    Normalize API data from GitLab YAML to standard format.
    Supports both simple format and Kubernetes-style format (apiVersion/kind/spec).
    """
    # If it's Kubernetes-style format
    if "apiVersion" in raw_data and "kind" in raw_data:
        metadata = raw_data.get("metadata", {})
        spec = raw_data.get("spec", {})
        backend = spec.get("backend", {})
        deployments = spec.get("deployments", {})

        return {
            "id": metadata.get("name", ""),
            "name": metadata.get("name", ""),
            "display_name": spec.get("displayName", metadata.get("name", "")),
            "version": metadata.get("version", "1.0.0"),
            "description": spec.get("description", ""),
            "backend_url": backend.get("url", ""),
            "status": spec.get("status", "draft"),
            "deployments": {
                "dev": deployments.get("dev", False),
                "staging": deployments.get("staging", False),
            }
        }

    # Simple format - return as-is
    return raw_data

class GitLabService:
    """Service for GitLab operations - GitOps source of truth"""

    def __init__(self):
        self._gl: Optional[gitlab.Gitlab] = None
        self._project: Optional[Project] = None

    async def connect(self):
        """Initialize GitLab connection"""
        try:
            self._gl = gitlab.Gitlab(
                settings.GITLAB_URL,
                private_token=settings.GITLAB_TOKEN
            )
            self._gl.auth()

            # Get the main APIM project
            self._project = self._gl.projects.get(settings.GITLAB_PROJECT_ID)

            logger.info(f"Connected to GitLab project: {self._project.name}")
        except Exception as e:
            logger.error(f"Failed to connect to GitLab: {e}")
            raise

    async def disconnect(self):
        """Close GitLab connection"""
        self._gl = None
        self._project = None

    def _get_tenant_path(self, tenant_id: str) -> str:
        """Get the base path for a tenant in the repo"""
        return f"tenants/{tenant_id}"

    def _get_api_path(self, tenant_id: str, api_name: str) -> str:
        """Get the path for an API definition"""
        return f"{self._get_tenant_path(tenant_id)}/apis/{api_name}"

    # Tenant operations
    async def create_tenant_structure(self, tenant_id: str, tenant_data: dict) -> bool:
        """
        Create initial tenant directory structure in GitLab.

        Structure:
        tenants/{tenant_id}/
        ├── tenant.yaml
        ├── apis/
        └── applications/
        """
        if not self._project:
            raise RuntimeError("GitLab not connected")

        try:
            # Create tenant.yaml
            tenant_yaml = f"""# Tenant Configuration
id: {tenant_id}
name: {tenant_data.get('name', tenant_id)}
display_name: {tenant_data.get('display_name', tenant_id)}
created_at: {tenant_data.get('created_at', '')}
status: active
settings:
  max_apis: 100
  max_applications: 50
  environments:
    - dev
    - staging
"""
            # Use commits API for atomic operation (single commit with all files)
            # This prevents race conditions when creating multiple files
            tenant_path = self._get_tenant_path(tenant_id)
            actions = [
                {
                    "action": "create",
                    "file_path": f"{tenant_path}/tenant.yaml",
                    "content": tenant_yaml,
                },
                {
                    "action": "create",
                    "file_path": f"{tenant_path}/apis/.gitkeep",
                    "content": "",
                },
                {
                    "action": "create",
                    "file_path": f"{tenant_path}/applications/.gitkeep",
                    "content": "",
                }
            ]

            self._project.commits.create({
                "branch": "main",
                "commit_message": f"Create tenant {tenant_id}",
                "actions": actions,
            })

            logger.info(f"Created tenant structure for {tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create tenant structure: {e}")
            raise

    async def get_tenant(self, tenant_id: str) -> Optional[dict]:
        """Get tenant configuration from GitLab"""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        try:
            file = self._project.files.get(
                f"{self._get_tenant_path(tenant_id)}/tenant.yaml",
                ref="main"
            )
            return yaml.safe_load(file.decode())
        except gitlab.exceptions.GitlabGetError:
            return None

    async def _ensure_tenant_exists(self, tenant_id: str) -> bool:
        """Check if tenant exists, create structure if not"""
        try:
            self._project.files.get(
                f"{self._get_tenant_path(tenant_id)}/tenant.yaml",
                ref="main"
            )
            return True
        except gitlab.exceptions.GitlabGetError:
            # Tenant doesn't exist, create minimal structure
            logger.info(f"Tenant {tenant_id} doesn't exist, creating structure...")
            await self.create_tenant_structure(tenant_id, {
                "name": tenant_id,
                "display_name": tenant_id,
            })
            return True

    async def _api_exists(self, tenant_id: str, api_name: str) -> bool:
        """Check if API already exists"""
        try:
            self._project.files.get(
                f"{self._get_api_path(tenant_id, api_name)}/api.yaml",
                ref="main"
            )
            return True
        except gitlab.exceptions.GitlabGetError:
            return False

    # API operations
    async def create_api(self, tenant_id: str, api_data: dict) -> str:
        """
        Create API definition in GitLab.

        Creates:
        tenants/{tenant_id}/apis/{api_name}/
        ├── api.yaml          # API metadata
        ├── openapi.yaml      # OpenAPI specification
        └── policies/         # Gateway policies
        """
        if not self._project:
            raise RuntimeError("GitLab not connected")

        api_name = api_data["name"]
        api_path = self._get_api_path(tenant_id, api_name)

        # Ensure tenant exists
        await self._ensure_tenant_exists(tenant_id)

        # Check if API already exists
        if await self._api_exists(tenant_id, api_name):
            raise ValueError(f"API '{api_name}' already exists for tenant '{tenant_id}'")

        try:
            # Create api.yaml with proper YAML escaping for description
            api_content = {
                "id": api_data.get("id", api_name),
                "name": api_name,
                "display_name": api_data.get("display_name", api_name),
                "version": api_data.get("version", "1.0.0"),
                "description": api_data.get("description", ""),
                "backend_url": api_data.get("backend_url", ""),
                "status": "draft",
                "deployments": {
                    "dev": False,
                    "staging": False,
                }
            }

            api_yaml = yaml.dump(api_content, default_flow_style=False, allow_unicode=True)

            # Use commits API to create all files in a single atomic commit
            # This prevents race conditions when creating multiple files
            actions = [
                {
                    "action": "create",
                    "file_path": f"{api_path}/api.yaml",
                    "content": api_yaml,
                },
                {
                    "action": "create",
                    "file_path": f"{api_path}/policies/.gitkeep",
                    "content": "",
                }
            ]

            # Add OpenAPI spec if provided
            if api_data.get("openapi_spec"):
                actions.append({
                    "action": "create",
                    "file_path": f"{api_path}/openapi.yaml",
                    "content": api_data["openapi_spec"],
                })

            # Single atomic commit with all files
            self._project.commits.create({
                "branch": "main",
                "commit_message": f"Create API {api_name} for tenant {tenant_id}",
                "actions": actions,
            })

            logger.info(f"Created API {api_name} for tenant {tenant_id}")
            return api_data.get("id", api_name)

        except gitlab.exceptions.GitlabCreateError as e:
            if "already exists" in str(e).lower():
                raise ValueError(f"API '{api_name}' already exists for tenant '{tenant_id}'")
            logger.error(f"Failed to create API: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to create API: {e}")
            raise

    async def get_api(self, tenant_id: str, api_name: str) -> Optional[dict]:
        """Get API configuration from GitLab"""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        try:
            file = self._project.files.get(
                f"{self._get_api_path(tenant_id, api_name)}/api.yaml",
                ref="main"
            )
            raw_data = yaml.safe_load(file.decode())
            return _normalize_api_data(raw_data)
        except gitlab.exceptions.GitlabGetError:
            return None
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse API YAML for {api_name}: {e}")
            return None

    async def list_apis(self, tenant_id: str) -> list[dict]:
        """List all APIs for a tenant"""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        try:
            tree = self._project.repository_tree(
                path=f"{self._get_tenant_path(tenant_id)}/apis",
                ref="main"
            )

            apis = []
            for item in tree:
                if item["type"] == "tree" and item["name"] != ".gitkeep":
                    api = await self.get_api(tenant_id, item["name"])
                    if api:
                        apis.append(api)

            return apis

        except gitlab.exceptions.GitlabGetError:
            return []

    async def update_api(self, tenant_id: str, api_name: str, api_data: dict) -> bool:
        """Update API configuration in GitLab"""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        try:
            file = self._project.files.get(
                f"{self._get_api_path(tenant_id, api_name)}/api.yaml",
                ref="main"
            )
            current = yaml.safe_load(file.decode())
            current.update(api_data)

            file.content = yaml.dump(current, default_flow_style=False, allow_unicode=True)
            file.save(branch="main", commit_message=f"Update API {api_name}")

            logger.info(f"Updated API {api_name} for tenant {tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update API: {e}")
            raise

    async def delete_api(self, tenant_id: str, api_name: str) -> bool:
        """Delete API from GitLab"""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        try:
            # Delete entire API directory by deleting files
            api_path = self._get_api_path(tenant_id, api_name)
            tree = self._project.repository_tree(path=api_path, ref="main", recursive=True)

            for item in tree:
                if item["type"] == "blob":
                    self._project.files.delete(
                        file_path=item["path"],
                        commit_message=f"Delete API {api_name}",
                        branch="main"
                    )

            logger.info(f"Deleted API {api_name} for tenant {tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete API: {e}")
            raise

    # Git operations
    async def get_file(self, path: str, ref: str = "main") -> Optional[str]:
        """Get file content from GitLab"""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        try:
            file = self._project.files.get(path, ref=ref)
            return file.decode().decode("utf-8")
        except gitlab.exceptions.GitlabGetError:
            return None

    async def list_commits(self, path: Optional[str] = None, limit: int = 20) -> list[dict]:
        """List commits for a path"""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        commits = self._project.commits.list(path=path, per_page=limit)
        return [
            {
                "sha": c.id,
                "message": c.message,
                "author": c.author_name,
                "date": c.created_at,
            }
            for c in commits
        ]

# Global instance
git_service = GitLabService()
