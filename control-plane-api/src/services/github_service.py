"""GitHub implementation of GitProvider (CAB-1890 Wave 2, CAB-2011 write methods).

Uses PyGithub for API operations and subprocess git for clone.
project_id format: "org/repo" (e.g. "stoa-platform/stoa-catalog").
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

import yaml
from github import Auth, Github, GithubException, InputGitTreeElement

from ..config import settings
from .git_provider import GitProvider

logger = logging.getLogger(__name__)


class GitHubService(GitProvider):
    """GitHub implementation of GitProvider — GitOps source of truth."""

    def __init__(self) -> None:
        self._gh: Github | None = None

    async def connect(self) -> None:
        """Initialize GitHub connection using GITHUB_TOKEN."""
        try:
            auth = Auth.Token(settings.GITHUB_TOKEN)
            self._gh = Github(auth=auth)
            # Validate credentials by fetching authenticated user
            user = self._gh.get_user().login
            logger.info("Connected to GitHub as %s", user)
        except Exception as e:
            logger.error("Failed to connect to GitHub: %s", e)
            raise

    async def disconnect(self) -> None:
        """Close GitHub connection."""
        if self._gh:
            self._gh.close()
        self._gh = None

    async def clone_repo(self, repo_url: str) -> Path:
        """Clone a GitHub repository to a temporary directory."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="stoa-gh-"))
        token = settings.GITHUB_TOKEN
        # Inject token into HTTPS URL for auth
        authed_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth=1",
            authed_url,
            str(tmp_dir / "repo"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode().strip()}")
        return tmp_dir / "repo"

    def _get_repo(self, project_id: str) -> Any:
        """Get a PyGithub Repository object.

        Args:
            project_id: "org/repo" format (e.g. "stoa-platform/stoa-catalog").
        """
        if not self._gh:
            raise RuntimeError("GitHub not connected")
        return self._gh.get_repo(project_id)

    async def get_file_content(self, project_id: str, file_path: str, ref: str = "main") -> str:
        """Retrieve raw file content from GitHub."""
        repo = self._get_repo(project_id)
        try:
            content_file = repo.get_contents(file_path, ref=ref)
            if isinstance(content_file, list):
                raise FileNotFoundError(f"{file_path} is a directory, not a file, in {project_id}")
            return content_file.decoded_content.decode("utf-8")
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError(f"{file_path} not found in project {project_id}") from exc
            raise

    async def list_files(self, project_id: str, path: str = "", ref: str = "main") -> list[str]:
        """List files in a GitHub repository directory."""
        repo = self._get_repo(project_id)
        try:
            contents = repo.get_contents(path, ref=ref)
            if not isinstance(contents, list):
                contents = [contents]
            return [item.path for item in contents]
        except GithubException as exc:
            if exc.status == 404:
                return []
            raise

    async def create_webhook(
        self,
        project_id: str,
        url: str,
        secret: str,
        events: list[str],
    ) -> dict[str, Any]:
        """Register a webhook on a GitHub repository."""
        repo = self._get_repo(project_id)
        # Map generic event names to GitHub webhook events
        event_map = {
            "push": "push",
            "merge_request": "pull_request",
            "tag": "create",
            "issues": "issues",
        }
        gh_events = [event_map.get(e, e) for e in events]
        hook = repo.create_hook(
            name="web",
            config={"url": url, "secret": secret, "content_type": "json"},
            events=gh_events,
            active=True,
        )
        return {"id": str(hook.id), "url": hook.config["url"]}

    async def delete_webhook(self, project_id: str, hook_id: str) -> bool:
        """Remove a webhook from a GitHub repository."""
        repo = self._get_repo(project_id)
        try:
            hook = repo.get_hook(int(hook_id))
            hook.delete()
            return True
        except GithubException as exc:
            if exc.status == 404:
                return False
            raise

    async def get_repo_info(self, project_id: str) -> dict[str, Any]:
        """Retrieve GitHub repository metadata."""
        repo = self._get_repo(project_id)
        return {
            "name": repo.name,
            "default_branch": repo.default_branch,
            "url": repo.html_url,
            "visibility": "private" if repo.private else "public",
        }

    # ============================================================
    # Write operations (CAB-2011: GitOps source of truth)
    # ============================================================

    async def create_file(
        self, project_id: str, file_path: str, content: str, commit_message: str, branch: str = "main"
    ) -> dict[str, Any]:
        """Create a new file in a GitHub repository."""
        repo = self._get_repo(project_id)
        try:
            result = repo.create_file(file_path, commit_message, content, branch=branch)
            return {"sha": result["commit"].sha, "url": result["commit"].html_url}
        except GithubException as exc:
            if exc.status == 422 and "sha" in str(exc.data).lower():
                raise ValueError(f"File already exists: {file_path}") from exc
            raise

    async def update_file(
        self, project_id: str, file_path: str, content: str, commit_message: str, branch: str = "main"
    ) -> dict[str, Any]:
        """Update an existing file in a GitHub repository."""
        repo = self._get_repo(project_id)
        try:
            existing = repo.get_contents(file_path, ref=branch)
            if isinstance(existing, list):
                raise ValueError(f"{file_path} is a directory, not a file")
            result = repo.update_file(file_path, commit_message, content, existing.sha, branch=branch)
            return {"sha": result["commit"].sha, "url": result["commit"].html_url}
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError(f"{file_path} not found in {project_id}") from exc
            raise

    async def delete_file(self, project_id: str, file_path: str, commit_message: str, branch: str = "main") -> bool:
        """Delete a file from a GitHub repository."""
        repo = self._get_repo(project_id)
        try:
            existing = repo.get_contents(file_path, ref=branch)
            if isinstance(existing, list):
                raise ValueError(f"{file_path} is a directory, not a file")
            repo.delete_file(file_path, commit_message, existing.sha, branch=branch)
            return True
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError(f"{file_path} not found in {project_id}") from exc
            raise

    async def batch_commit(
        self,
        project_id: str,
        actions: list[dict[str, str]],
        commit_message: str,
        branch: str = "main",
    ) -> dict[str, Any]:
        """Atomic multi-file commit via the Git Tree API.

        Equivalent to GitLab's project.commits.create() with an actions array.
        Creates a new tree with all changes and points the branch ref at it.
        """
        repo = self._get_repo(project_id)

        # 1. Get current commit on branch
        ref = repo.get_git_ref(f"heads/{branch}")
        base_sha = ref.object.sha
        base_tree = repo.get_git_tree(base_sha)

        # 2. Build tree elements from actions
        tree_elements: list[InputGitTreeElement] = []
        for action in actions:
            act = action["action"]
            path = action["file_path"]

            if act in ("create", "update"):
                content = action.get("content", "")
                tree_elements.append(InputGitTreeElement(path, "100644", "blob", content=content))
            elif act == "delete":
                # SHA "null" + mode "000000" removes the entry from the tree
                tree_elements.append(InputGitTreeElement(path, "100644", "blob", sha=None))
            else:
                raise ValueError(f"Unknown action: {act}. Must be create, update, or delete.")

        if not tree_elements:
            raise ValueError("No actions provided for batch commit")

        # 3. Create new tree, commit, and update ref
        new_tree = repo.create_git_tree(tree_elements, base_tree=base_tree)
        new_commit = repo.create_git_commit(commit_message, new_tree, [repo.get_git_commit(base_sha)])
        ref.edit(new_commit.sha)

        logger.info("Batch commit %s on %s/%s (%d actions)", new_commit.sha[:8], project_id, branch, len(actions))
        return {"sha": new_commit.sha, "url": new_commit.html_url}

    async def create_pull_request(
        self,
        project_id: str,
        branch: str,
        title: str,
        body: str,
        actions: list[dict[str, str]],
        base: str = "main",
    ) -> dict[str, Any]:
        """Create a branch with changes and open a pull request.

        1. Creates a new branch from base
        2. Commits all actions to that branch via batch_commit
        3. Opens a PR from branch → base
        """
        repo = self._get_repo(project_id)

        # Create branch from base HEAD
        base_ref = repo.get_git_ref(f"heads/{base}")
        repo.create_git_ref(f"refs/heads/{branch}", base_ref.object.sha)

        # Commit changes to the new branch
        await self.batch_commit(project_id, actions, title, branch=branch)

        # Open PR
        pr = repo.create_pull(title=title, body=body, head=branch, base=base)
        logger.info("Created PR #%d on %s: %s", pr.number, project_id, title)
        return {"pr_number": pr.number, "url": pr.html_url}

    # ============================================================
    # High-level catalog operations (CAB-2011)
    # ============================================================

    def _catalog_project_id(self) -> str:
        """Return the catalog repo in org/repo format."""
        return f"{settings.GITHUB_ORG}/{settings.GITHUB_CATALOG_REPO}"

    @staticmethod
    def _get_tenant_path(tenant_id: str) -> str:
        return f"tenants/{tenant_id}"

    @staticmethod
    def _get_api_path(tenant_id: str, api_name: str) -> str:
        return f"tenants/{tenant_id}/apis/{api_name}"

    @staticmethod
    def _get_mcp_server_path(tenant_id: str, server_name: str) -> str:
        if tenant_id == "_platform":
            return f"platform/mcp-servers/{server_name}"
        return f"tenants/{tenant_id}/mcp-servers/{server_name}"

    async def _file_exists(self, project_id: str, file_path: str, ref: str = "main") -> bool:
        """Check if a file exists in the repository."""
        try:
            await self.get_file_content(project_id, file_path, ref=ref)
            return True
        except FileNotFoundError:
            return False

    # --- Tenant operations ---

    async def create_tenant_structure(self, tenant_id: str, tenant_data: dict) -> bool:
        """Create initial tenant directory structure in GitHub.

        Structure:
        tenants/{tenant_id}/
        ├── tenant.yaml
        ├── apis/.gitkeep
        └── applications/.gitkeep
        """
        project_id = self._catalog_project_id()
        tenant_path = self._get_tenant_path(tenant_id)

        tenant_yaml = yaml.dump(
            {
                "id": tenant_id,
                "name": tenant_data.get("name", tenant_id),
                "display_name": tenant_data.get("display_name", tenant_id),
                "created_at": tenant_data.get("created_at", ""),
                "status": "active",
                "settings": {
                    "max_apis": 100,
                    "max_applications": 50,
                    "environments": ["dev", "staging"],
                },
            },
            default_flow_style=False,
            allow_unicode=True,
        )

        await self.batch_commit(
            project_id,
            actions=[
                {"action": "create", "file_path": f"{tenant_path}/tenant.yaml", "content": tenant_yaml},
                {"action": "create", "file_path": f"{tenant_path}/apis/.gitkeep", "content": ""},
                {"action": "create", "file_path": f"{tenant_path}/applications/.gitkeep", "content": ""},
            ],
            commit_message=f"Create tenant {tenant_id}",
        )

        logger.info("Created tenant structure for %s", tenant_id)
        return True

    async def _ensure_tenant_exists(self, tenant_id: str) -> bool:
        """Check if tenant exists, create structure if not."""
        project_id = self._catalog_project_id()
        tenant_path = self._get_tenant_path(tenant_id)
        if await self._file_exists(project_id, f"{tenant_path}/tenant.yaml"):
            return True
        logger.info("Tenant %s doesn't exist, creating structure...", tenant_id)
        await self.create_tenant_structure(tenant_id, {"name": tenant_id, "display_name": tenant_id})
        return True

    # --- API operations ---

    async def create_api(self, tenant_id: str, api_data: dict) -> str:
        """Create API definition in GitHub.

        Creates:
        tenants/{tenant_id}/apis/{api_name}/
        ├── api.yaml
        ├── openapi.yaml (if provided)
        ├── overrides/{env}.yaml (if provided, CAB-2015)
        └── policies/.gitkeep
        """
        project_id = self._catalog_project_id()
        api_name = api_data["name"]
        api_path = self._get_api_path(tenant_id, api_name)

        await self._ensure_tenant_exists(tenant_id)

        if await self._file_exists(project_id, f"{api_path}/api.yaml"):
            raise ValueError(f"API '{api_name}' already exists for tenant '{tenant_id}'")

        api_content = {
            "id": api_data.get("id", api_name),
            "name": api_name,
            "display_name": api_data.get("display_name", api_name),
            "version": api_data.get("version", "1.0.0"),
            "description": api_data.get("description", ""),
            "backend_url": api_data.get("backend_url", ""),
            "tags": api_data.get("tags", []),
            "status": "draft",
            "deployments": {"dev": False, "staging": False},
        }

        api_yaml = yaml.dump(api_content, default_flow_style=False, allow_unicode=True)

        actions = [
            {"action": "create", "file_path": f"{api_path}/api.yaml", "content": api_yaml},
            {"action": "create", "file_path": f"{api_path}/policies/.gitkeep", "content": ""},
        ]

        if api_data.get("openapi_spec"):
            actions.append(
                {"action": "create", "file_path": f"{api_path}/openapi.yaml", "content": api_data["openapi_spec"]}
            )

        # CAB-2015: write per-environment overrides if provided
        overrides: dict[str, dict] = api_data.get("overrides", {})
        for env_name, env_config in overrides.items():
            override_yaml = yaml.dump(env_config, default_flow_style=False, allow_unicode=True)
            actions.append(
                {"action": "create", "file_path": f"{api_path}/overrides/{env_name}.yaml", "content": override_yaml}
            )

        await self.batch_commit(
            project_id,
            actions=actions,
            commit_message=f"Create API {api_name} for tenant {tenant_id}",
        )

        logger.info("Created API %s for tenant %s", api_name, tenant_id)
        return api_data.get("id", api_name)

    async def update_api(self, tenant_id: str, api_name: str, api_data: dict) -> bool:
        """Update API configuration in GitHub."""
        project_id = self._catalog_project_id()
        api_path = self._get_api_path(tenant_id, api_name)
        file_path = f"{api_path}/api.yaml"

        try:
            current_content = await self.get_file_content(project_id, file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"API '{api_name}' not found for tenant '{tenant_id}'")

        # Separate overrides from base api_data
        overrides: dict[str, dict] = api_data.pop("overrides", {})

        current = yaml.safe_load(current_content)
        current.update(api_data)
        updated_yaml = yaml.dump(current, default_flow_style=False, allow_unicode=True)

        # CAB-2015: batch base + override updates in one commit
        if overrides:
            actions = [{"action": "update", "file_path": file_path, "content": updated_yaml}]
            for env_name, env_config in overrides.items():
                override_path = f"{api_path}/overrides/{env_name}.yaml"
                override_yaml = yaml.dump(env_config, default_flow_style=False, allow_unicode=True)
                action = "update" if await self._file_exists(project_id, override_path) else "create"
                actions.append({"action": action, "file_path": override_path, "content": override_yaml})
            await self.batch_commit(project_id, actions=actions, commit_message=f"Update API {api_name}")
        else:
            await self.update_file(project_id, file_path, updated_yaml, f"Update API {api_name}")

        logger.info("Updated API %s for tenant %s", api_name, tenant_id)
        return True

    async def delete_api(self, tenant_id: str, api_name: str) -> bool:
        """Delete API directory from GitHub."""
        project_id = self._catalog_project_id()
        api_path = self._get_api_path(tenant_id, api_name)

        # List all files in the API directory via recursive tree
        repo = self._get_repo(project_id)
        try:
            contents = repo.get_contents(api_path, ref="main")
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError(f"API '{api_name}' not found for tenant '{tenant_id}'") from exc
            raise

        # Flatten directory contents recursively
        files_to_delete: list[str] = []
        stack = contents if isinstance(contents, list) else [contents]
        while stack:
            item = stack.pop()
            if item.type == "dir":
                sub_contents = repo.get_contents(item.path, ref="main")
                stack.extend(sub_contents if isinstance(sub_contents, list) else [sub_contents])
            else:
                files_to_delete.append(item.path)

        if not files_to_delete:
            return True

        actions = [{"action": "delete", "file_path": f} for f in files_to_delete]
        await self.batch_commit(project_id, actions=actions, commit_message=f"Delete API {api_name}")

        logger.info("Deleted API %s for tenant %s", api_name, tenant_id)
        return True

    # --- MCP Server operations ---

    async def create_mcp_server(self, tenant_id: str, server_data: dict) -> str:
        """Create MCP server definition in GitHub."""
        project_id = self._catalog_project_id()
        server_name = server_data["name"]
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        if await self._file_exists(project_id, f"{server_path}/server.yaml"):
            raise ValueError(f"MCP server '{server_name}' already exists")

        server_yaml = yaml.dump(
            {
                "apiVersion": "gostoa.dev/v1",
                "kind": "MCPServer",
                "metadata": {
                    "name": server_name,
                    "tenant": tenant_id,
                    "version": server_data.get("version", "1.0.0"),
                    "labels": {"managed-by": "gitops"},
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
            },
            default_flow_style=False,
            allow_unicode=True,
        )

        await self.batch_commit(
            project_id,
            actions=[{"action": "create", "file_path": f"{server_path}/server.yaml", "content": server_yaml}],
            commit_message=f"Create MCP server {server_name}",
        )

        logger.info("Created MCP server %s", server_name)
        return server_name

    async def update_mcp_server(self, tenant_id: str, server_name: str, server_data: dict) -> bool:
        """Update MCP server configuration in GitHub."""
        project_id = self._catalog_project_id()
        server_path = self._get_mcp_server_path(tenant_id, server_name)
        file_path = f"{server_path}/server.yaml"

        try:
            current_content = await self.get_file_content(project_id, file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"MCP server '{server_name}' not found")

        current = yaml.safe_load(current_content)

        if "spec" not in current:
            current["spec"] = {}

        field_map = {
            "display_name": "displayName",
            "documentation_url": "documentationUrl",
        }
        direct_fields = {"description", "icon", "category", "status", "visibility", "tools", "backend"}

        for key, value in server_data.items():
            if key in field_map:
                current["spec"][field_map[key]] = value
            elif key in direct_fields:
                current["spec"][key] = value

        updated_yaml = yaml.dump(current, default_flow_style=False, allow_unicode=True)
        await self.update_file(project_id, file_path, updated_yaml, f"Update MCP server {server_name}")

        logger.info("Updated MCP server %s", server_name)
        return True

    async def delete_mcp_server(self, tenant_id: str, server_name: str) -> bool:
        """Delete MCP server from GitHub."""
        project_id = self._catalog_project_id()
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        repo = self._get_repo(project_id)
        try:
            contents = repo.get_contents(server_path, ref="main")
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError(f"MCP server '{server_name}' not found") from exc
            raise

        files_to_delete: list[str] = []
        stack = contents if isinstance(contents, list) else [contents]
        while stack:
            item = stack.pop()
            if item.type == "dir":
                sub_contents = repo.get_contents(item.path, ref="main")
                stack.extend(sub_contents if isinstance(sub_contents, list) else [sub_contents])
            else:
                files_to_delete.append(item.path)

        if not files_to_delete:
            return True

        actions = [{"action": "delete", "file_path": f} for f in files_to_delete]
        await self.batch_commit(project_id, actions=actions, commit_message=f"Delete MCP server {server_name}")

        logger.info("Deleted MCP server %s", server_name)
        return True
