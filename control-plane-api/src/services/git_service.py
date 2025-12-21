"""GitLab service for GitOps operations"""
import logging
from typing import Optional
import gitlab
from gitlab.v4.objects import Project

from ..config import settings

logger = logging.getLogger(__name__)

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
            self._project.files.create({
                "file_path": f"{self._get_tenant_path(tenant_id)}/tenant.yaml",
                "branch": "main",
                "content": tenant_yaml,
                "commit_message": f"Create tenant {tenant_id}",
            })

            # Create .gitkeep files for subdirectories
            for subdir in ["apis", "applications"]:
                self._project.files.create({
                    "file_path": f"{self._get_tenant_path(tenant_id)}/{subdir}/.gitkeep",
                    "branch": "main",
                    "content": "",
                    "commit_message": f"Create {subdir} directory for tenant {tenant_id}",
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
            import yaml
            return yaml.safe_load(file.decode())
        except gitlab.exceptions.GitlabGetError:
            return None

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

        try:
            # Create api.yaml
            api_yaml = f"""# API Configuration
id: {api_data.get('id', api_name)}
name: {api_name}
display_name: {api_data.get('display_name', api_name)}
version: {api_data.get('version', '1.0.0')}
description: {api_data.get('description', '')}
backend_url: {api_data.get('backend_url', '')}
status: draft
deployments:
  dev: false
  staging: false
"""
            self._project.files.create({
                "file_path": f"{api_path}/api.yaml",
                "branch": "main",
                "content": api_yaml,
                "commit_message": f"Create API {api_name} for tenant {tenant_id}",
            })

            # Create OpenAPI spec if provided
            if api_data.get("openapi_spec"):
                self._project.files.create({
                    "file_path": f"{api_path}/openapi.yaml",
                    "branch": "main",
                    "content": api_data["openapi_spec"],
                    "commit_message": f"Add OpenAPI spec for {api_name}",
                })

            # Create policies directory
            self._project.files.create({
                "file_path": f"{api_path}/policies/.gitkeep",
                "branch": "main",
                "content": "",
                "commit_message": f"Create policies directory for {api_name}",
            })

            logger.info(f"Created API {api_name} for tenant {tenant_id}")
            return api_data.get("id", api_name)

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
            import yaml
            return yaml.safe_load(file.decode())
        except gitlab.exceptions.GitlabGetError:
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
            import yaml

            file = self._project.files.get(
                f"{self._get_api_path(tenant_id, api_name)}/api.yaml",
                ref="main"
            )
            current = yaml.safe_load(file.decode())
            current.update(api_data)

            file.content = yaml.dump(current, default_flow_style=False)
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
