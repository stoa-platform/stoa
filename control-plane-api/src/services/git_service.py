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

    async def get_api_openapi_spec(self, tenant_id: str, api_name: str) -> Optional[dict]:
        """Get OpenAPI specification for an API from GitLab"""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        try:
            # Try openapi.yaml first, then openapi.json
            for filename in ["openapi.yaml", "openapi.yml", "openapi.json"]:
                try:
                    file = self._project.files.get(
                        f"{self._get_api_path(tenant_id, api_name)}/{filename}",
                        ref="main"
                    )
                    content = file.decode()
                    if filename.endswith(".json"):
                        import json
                        return json.loads(content)
                    else:
                        return yaml.safe_load(content)
                except gitlab.exceptions.GitlabGetError:
                    continue

            return None
        except Exception as e:
            logger.error(f"Failed to get OpenAPI spec for {api_name}: {e}")
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

    # ===========================================
    # MCP Server GitOps Operations
    # ===========================================

    def _get_mcp_server_path(self, tenant_id: str, server_name: str) -> str:
        """Get the path for an MCP server definition.

        Platform servers: platform/mcp-servers/{server_name}
        Tenant servers: tenants/{tenant_id}/mcp-servers/{server_name}
        """
        if tenant_id == "_platform":
            return f"platform/mcp-servers/{server_name}"
        return f"{self._get_tenant_path(tenant_id)}/mcp-servers/{server_name}"

    def _normalize_mcp_server_data(self, raw_data: dict, git_path: str) -> dict:
        """
        Normalize MCP server data from GitLab YAML to standard format.
        Supports Kubernetes-style format (apiVersion/kind/spec).
        """
        metadata = raw_data.get("metadata", {})
        spec = raw_data.get("spec", {})
        visibility = spec.get("visibility", {})
        subscription = spec.get("subscription", {})
        backend = spec.get("backend", {})

        # Normalize tools
        tools = []
        for tool in spec.get("tools", []):
            tools.append({
                "name": tool.get("name"),
                "display_name": tool.get("displayName", tool.get("name")),
                "description": tool.get("description", ""),
                "endpoint": tool.get("endpoint", ""),
                "method": tool.get("method", "POST"),
                "enabled": tool.get("enabled", True),
                "requires_approval": tool.get("requiresApproval", False),
                "input_schema": tool.get("inputSchema", {}),
                "timeout": tool.get("timeout", "30s"),
                "rate_limit": tool.get("rateLimit", {}).get("requestsPerMinute", 60),
            })

        return {
            "name": metadata.get("name", ""),
            "tenant_id": metadata.get("tenant", "_platform"),
            "version": metadata.get("version", "1.0.0"),
            "display_name": spec.get("displayName", metadata.get("name", "")),
            "description": spec.get("description", ""),
            "icon": spec.get("icon", ""),
            "category": spec.get("category", "public"),
            "status": spec.get("status", "active"),
            "documentation_url": spec.get("documentationUrl", ""),
            "visibility": {
                "public": visibility.get("public", True),
                "roles": visibility.get("roles", []),
                "exclude_roles": visibility.get("excludeRoles", []),
            },
            "requires_approval": subscription.get("requiresApproval", False),
            "auto_approve_roles": subscription.get("autoApproveRoles", []),
            "default_plan": subscription.get("defaultPlan", "free"),
            "tools": tools,
            "backend": {
                "base_url": backend.get("baseUrl", ""),
                "auth_type": backend.get("auth", {}).get("type", "none"),
                "secret_ref": backend.get("auth", {}).get("secretRef", ""),
                "timeout": backend.get("timeout", "30s"),
                "retries": backend.get("retries", 3),
            },
            "git_path": git_path,
        }

    async def get_mcp_server(self, tenant_id: str, server_name: str) -> Optional[dict]:
        """Get MCP server configuration from GitLab."""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        server_path = self._get_mcp_server_path(tenant_id, server_name)

        try:
            file = self._project.files.get(
                f"{server_path}/server.yaml",
                ref="main"
            )
            raw_data = yaml.safe_load(file.decode())
            return self._normalize_mcp_server_data(raw_data, server_path)
        except gitlab.exceptions.GitlabGetError:
            return None
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse MCP server YAML for {server_name}: {e}")
            return None

    async def list_mcp_servers(self, tenant_id: str = "_platform") -> list[dict]:
        """List all MCP servers for a tenant or platform."""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        # Determine base path
        if tenant_id == "_platform":
            base_path = "platform/mcp-servers"
        else:
            base_path = f"{self._get_tenant_path(tenant_id)}/mcp-servers"

        try:
            tree = self._project.repository_tree(path=base_path, ref="main")

            servers = []
            for item in tree:
                if item["type"] == "tree" and item["name"] != ".gitkeep":
                    server = await self.get_mcp_server(tenant_id, item["name"])
                    if server:
                        servers.append(server)

            return servers

        except gitlab.exceptions.GitlabGetError:
            return []

    async def list_all_mcp_servers(self) -> list[dict]:
        """List all MCP servers across platform and all tenants."""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        all_servers = []

        # Get platform servers
        platform_servers = await self.list_mcp_servers("_platform")
        all_servers.extend(platform_servers)

        # Get tenant servers
        try:
            tenants_tree = self._project.repository_tree(path="tenants", ref="main")
            for tenant_item in tenants_tree:
                if tenant_item["type"] == "tree":
                    tenant_id = tenant_item["name"]
                    tenant_servers = await self.list_mcp_servers(tenant_id)
                    all_servers.extend(tenant_servers)
        except gitlab.exceptions.GitlabGetError:
            pass  # No tenants directory

        return all_servers

    async def create_mcp_server(self, tenant_id: str, server_data: dict) -> str:
        """Create MCP server definition in GitLab."""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        server_name = server_data["name"]
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        # Check if server already exists
        existing = await self.get_mcp_server(tenant_id, server_name)
        if existing:
            raise ValueError(f"MCP server '{server_name}' already exists")

        try:
            # Build YAML content in Kubernetes-style format
            server_yaml = yaml.dump({
                "apiVersion": "stoa.cab-i.com/v1",
                "kind": "MCPServer",
                "metadata": {
                    "name": server_name,
                    "tenant": tenant_id,
                    "version": server_data.get("version", "1.0.0"),
                    "labels": {
                        "managed-by": "gitops",
                    },
                },
                "spec": {
                    "displayName": server_data.get("display_name", server_name),
                    "description": server_data.get("description", ""),
                    "icon": server_data.get("icon", ""),
                    "category": server_data.get("category", "public"),
                    "status": server_data.get("status", "active"),
                    "documentationUrl": server_data.get("documentation_url", ""),
                    "visibility": server_data.get("visibility", {"public": True}),
                    "subscription": {
                        "requiresApproval": server_data.get("requires_approval", False),
                        "autoApproveRoles": server_data.get("auto_approve_roles", []),
                        "defaultPlan": server_data.get("default_plan", "free"),
                    },
                    "tools": server_data.get("tools", []),
                    "backend": server_data.get("backend", {}),
                },
            }, default_flow_style=False, allow_unicode=True)

            self._project.commits.create({
                "branch": "main",
                "commit_message": f"Create MCP server {server_name}",
                "actions": [
                    {
                        "action": "create",
                        "file_path": f"{server_path}/server.yaml",
                        "content": server_yaml,
                    },
                ],
            })

            logger.info(f"Created MCP server {server_name}")
            return server_name

        except Exception as e:
            logger.error(f"Failed to create MCP server: {e}")
            raise

    async def update_mcp_server(self, tenant_id: str, server_name: str, server_data: dict) -> bool:
        """Update MCP server configuration in GitLab."""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        server_path = self._get_mcp_server_path(tenant_id, server_name)

        try:
            file = self._project.files.get(
                f"{server_path}/server.yaml",
                ref="main"
            )
            current = yaml.safe_load(file.decode())

            # Update spec fields
            if "spec" not in current:
                current["spec"] = {}

            for key, value in server_data.items():
                if key in ["display_name"]:
                    current["spec"]["displayName"] = value
                elif key in ["description", "icon", "category", "status"]:
                    current["spec"][key] = value
                elif key == "documentation_url":
                    current["spec"]["documentationUrl"] = value
                elif key == "visibility":
                    current["spec"]["visibility"] = value
                elif key == "tools":
                    current["spec"]["tools"] = value
                elif key == "backend":
                    current["spec"]["backend"] = value

            file.content = yaml.dump(current, default_flow_style=False, allow_unicode=True)
            file.save(branch="main", commit_message=f"Update MCP server {server_name}")

            logger.info(f"Updated MCP server {server_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update MCP server: {e}")
            raise

    async def delete_mcp_server(self, tenant_id: str, server_name: str) -> bool:
        """Delete MCP server from GitLab."""
        if not self._project:
            raise RuntimeError("GitLab not connected")

        server_path = self._get_mcp_server_path(tenant_id, server_name)

        try:
            tree = self._project.repository_tree(path=server_path, ref="main", recursive=True)

            actions = []
            for item in tree:
                if item["type"] == "blob":
                    actions.append({
                        "action": "delete",
                        "file_path": item["path"],
                    })

            if actions:
                self._project.commits.create({
                    "branch": "main",
                    "commit_message": f"Delete MCP server {server_name}",
                    "actions": actions,
                })

            logger.info(f"Deleted MCP server {server_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete MCP server: {e}")
            raise


# Global instance
git_service = GitLabService()
