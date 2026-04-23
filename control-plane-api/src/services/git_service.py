"""GitLab service for GitOps operations.

CP-1 (C.1/C.4/C.5): every synchronous python-gitlab call is routed
through :func:`.git_executor.run_sync` so the asyncio loop stays
non-blocking and the applicative concurrency cap (``GITLAB_SEMAPHORE``)
is enforced uniformly across all methods (not only the two callers that
historically used ``_fetch_with_protection``).

CP-1 (C.6): write paths drop the ``_file_exists`` pre-check. ``write_file``
calls ``create_file`` first and falls through to ``update_file`` on the
"already exists" error. GitLab's optimistic-concurrency ``last_commit_id``
is threaded through ``update_file`` / ``delete_file`` / ``batch_commit``
when in scope. Note that this closes the TOCTOU *existence-check* window;
it does not provide full compare-and-swap against concurrent writers to
the same file — full CAS would require the caller to round-trip a
version token.
"""

import asyncio
import logging
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import gitlab
import yaml
from gitlab.v4.objects import Project

from ..config import settings
from .git_executor import (
    BATCH_TIMEOUT_S,
    DEFAULT_TIMEOUT_S,
    GITLAB_SEMAPHORE,
    run_sync,
)
from .git_provider import BranchRef, CommitRef, GitProvider, MergeRequestRef, TreeEntry

logger = logging.getLogger(__name__)

# ============================================================
# CAB-688 legacy retry wrapper — kept as a thin composition over
# ``run_sync`` because the site-specific 429 backoff is more
# aggressive than python-gitlab's default ``max_retries`` for the
# two "parallel fetch" callers that historically used it.
# ============================================================
GITLAB_TIMEOUT = 5.0
GITLAB_MAX_RETRIES = 3


class GitLabRateLimitError(Exception):
    """GitLab 429 rate limit exceeded."""


async def _fetch_with_protection(
    coro_factory: Callable[[], Any],
    name: str,
    timeout: float = GITLAB_TIMEOUT,
    max_retries: int = GITLAB_MAX_RETRIES,
) -> Any:
    """Execute a coroutine with bounded retry on 429 / timeout.

    ``coro_factory`` must return an awaitable (typically a GitLabService
    method call). The method itself is expected to go through ``run_sync``
    internally, so the applicative semaphore and offload are already
    applied; this wrapper only adds per-site retry on 429 and timeout.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with asyncio.timeout(timeout):
                return await coro_factory()
        except TimeoutError:
            logger.warning("GitLab call '%s' timed out (attempt %d/%d)", name, attempt + 1, max_retries)
            last_error = TimeoutError(f"{name} timed out")
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                wait_time = 2**attempt
                logger.warning("GitLab rate limit hit for '%s', waiting %ds (attempt %d)", name, wait_time, attempt + 1)
                await asyncio.sleep(wait_time)
                last_error = GitLabRateLimitError(str(e))
            else:
                logger.error("GitLab call '%s' failed: %s", name, e)
                last_error = e
                break
    raise last_error or Exception(f"Failed after {max_retries} attempts: {name}")


def _normalize_api_data(raw_data: dict) -> dict:
    """Normalize API data from GitLab YAML to standard format.

    Supports both simple format and Kubernetes-style format (apiVersion/kind/spec).
    """
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
            },
        }

    return raw_data


async def _gl_run(fn: Callable[..., Any], op_name: str, timeout: float = DEFAULT_TIMEOUT_S) -> Any:
    """Run a sync python-gitlab closure under the uniform GitLab semaphore."""
    return await run_sync(fn, semaphore=GITLAB_SEMAPHORE, timeout=timeout, op_name=op_name)


class GitLabService(GitProvider):
    """GitLab implementation of GitProvider — GitOps source of truth."""

    def __init__(self) -> None:
        self._gl: gitlab.Gitlab | None = None
        self._project: Project | None = None

    async def connect(self) -> None:
        """Initialize GitLab connection."""
        try:
            gl_cfg = settings.git.gitlab

            def _connect() -> tuple[gitlab.Gitlab, Project]:
                client = gitlab.Gitlab(gl_cfg.url, private_token=gl_cfg.token.get_secret_value())
                client.auth()
                project = client.projects.get(gl_cfg.project_id)
                return client, project

            self._gl, self._project = await _gl_run(_connect, "gitlab.connect", timeout=15.0)
            logger.info("Connected to GitLab project: %s", self._project.name)
        except Exception as e:
            logger.error("Failed to connect to GitLab: %s", e)
            raise

    async def disconnect(self) -> None:
        """Close GitLab connection."""
        self._gl = None
        self._project = None

    async def get_head_commit_sha(self, ref: str = "main") -> str | None:
        """Return the current HEAD commit SHA from GitLab."""
        project = self._require_project()

        def _head() -> str | None:
            commits = project.commits.list(ref_name=ref, per_page=1)
            if not commits:
                return None
            return commits[0].id

        return await _gl_run(_head, "gitlab.get_head_commit_sha")

    async def list_tenants(self) -> list[str]:
        """List tenant IDs from the catalog repository."""
        project = self._require_project()

        def _list() -> list[str]:
            try:
                tree = project.repository_tree(path="tenants", ref="main")
            except gitlab.exceptions.GitlabGetError:
                return []
            return [item["name"] for item in tree if item["type"] == "tree"]

        return await _gl_run(_list, "gitlab.list_tenants")

    # ============================================================
    # GitProvider ABC implementations
    # ============================================================

    async def clone_repo(self, repo_url: str) -> Path:
        """Clone a GitLab repository to a temporary directory.

        NOTE: token-in-URL here is the C.2 leak — patched by the
        subsequent commit (GIT_ASKPASS helper).
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="stoa-gl-"))
        token = settings.git.gitlab.token.get_secret_value()
        authed_url = repo_url.replace("https://", f"https://oauth2:{token}@")
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

    async def get_file_content(self, project_id: str, file_path: str, ref: str = "main") -> str:
        """Retrieve raw file content from GitLab."""
        gl = self._require_gl()

        def _get() -> str:
            project = gl.projects.get(project_id)
            try:
                f = project.files.get(file_path, ref=ref)
                return f.decode().decode("utf-8")
            except gitlab.exceptions.GitlabGetError as exc:
                raise FileNotFoundError(f"{file_path} not found in project {project_id}") from exc

        return await _gl_run(_get, "gitlab.get_file_content")

    async def list_files(self, project_id: str, path: str = "", ref: str = "main") -> list[str]:
        """List files in a GitLab repository directory."""
        gl = self._require_gl()

        def _list() -> list[str]:
            project = gl.projects.get(project_id)
            items = project.repository_tree(path=path, ref=ref, per_page=100, all=True)
            return [item["path"] for item in items]

        return await _gl_run(_list, "gitlab.list_files")

    async def create_webhook(
        self,
        project_id: str,
        url: str,
        secret: str,
        events: list[str],
    ) -> dict[str, Any]:
        """Register a webhook on a GitLab project."""
        gl = self._require_gl()

        def _create() -> dict[str, Any]:
            project = gl.projects.get(project_id)
            hook_data: dict[str, Any] = {"url": url, "token": secret}
            event_map = {
                "push": "push_events",
                "merge_request": "merge_requests_events",
                "tag": "tag_push_events",
                "issues": "issues_events",
            }
            for event in events:
                gl_key = event_map.get(event, f"{event}_events")
                hook_data[gl_key] = True
            hook = project.hooks.create(hook_data)
            return {"id": str(hook.id), "url": hook.url}

        return await _gl_run(_create, "gitlab.create_webhook")

    async def delete_webhook(self, project_id: str, hook_id: str) -> bool:
        """Remove a webhook from a GitLab project."""
        gl = self._require_gl()

        def _delete() -> bool:
            project = gl.projects.get(project_id)
            try:
                hook = project.hooks.get(int(hook_id))
                hook.delete()
                return True
            except gitlab.exceptions.GitlabGetError:
                return False

        return await _gl_run(_delete, "gitlab.delete_webhook")

    async def get_repo_info(self, project_id: str) -> dict[str, Any]:
        """Retrieve GitLab project metadata."""
        gl = self._require_gl()

        def _info() -> dict[str, Any]:
            project = gl.projects.get(project_id)
            return {
                "name": project.name,
                "default_branch": project.default_branch,
                "url": project.web_url,
                "visibility": project.visibility,
            }

        return await _gl_run(_info, "gitlab.get_repo_info")

    # ============================================================
    # Legacy methods (used by existing callers)
    # ============================================================

    def _get_tenant_path(self, tenant_id: str) -> str:
        return f"tenants/{tenant_id}"

    def _get_api_path(self, tenant_id: str, api_name: str) -> str:
        return f"{self._get_tenant_path(tenant_id)}/apis/{api_name}"

    def _require_project(self) -> Project:
        if not self._project:
            raise RuntimeError("GitLab not connected")
        return self._project

    def _require_gl(self) -> gitlab.Gitlab:
        if not self._gl:
            raise RuntimeError("GitLab not connected")
        return self._gl

    async def create_tenant_structure(self, tenant_id: str, tenant_data: dict) -> bool:
        """Create initial tenant directory structure in GitLab."""
        project = self._require_project()
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
        tenant_path = self._get_tenant_path(tenant_id)
        actions = [
            {"action": "create", "file_path": f"{tenant_path}/tenant.yaml", "content": tenant_yaml},
            {"action": "create", "file_path": f"{tenant_path}/apis/.gitkeep", "content": ""},
            {"action": "create", "file_path": f"{tenant_path}/applications/.gitkeep", "content": ""},
        ]

        def _commit() -> None:
            project.commits.create(
                {
                    "branch": "main",
                    "commit_message": f"Create tenant {tenant_id}",
                    "actions": actions,
                }
            )

        try:
            await _gl_run(_commit, "gitlab.create_tenant_structure", timeout=BATCH_TIMEOUT_S)
            logger.info("Created tenant structure for %s", tenant_id)
            return True
        except Exception as e:
            logger.error("Failed to create tenant structure: %s", e)
            raise

    async def get_tenant(self, tenant_id: str) -> dict | None:
        """Get tenant configuration from GitLab."""
        project = self._require_project()
        path = f"{self._get_tenant_path(tenant_id)}/tenant.yaml"

        def _get() -> dict | None:
            try:
                file = project.files.get(path, ref="main")
                return yaml.safe_load(file.decode())
            except gitlab.exceptions.GitlabGetError:
                return None

        return await _gl_run(_get, "gitlab.get_tenant")

    async def _ensure_tenant_exists(self, tenant_id: str) -> bool:
        """Check if tenant exists, create structure if not."""
        project = self._require_project()
        path = f"{self._get_tenant_path(tenant_id)}/tenant.yaml"

        def _exists() -> bool:
            try:
                project.files.get(path, ref="main")
                return True
            except gitlab.exceptions.GitlabGetError:
                return False

        if await _gl_run(_exists, "gitlab._ensure_tenant_exists"):
            return True
        logger.info("Tenant %s doesn't exist, creating structure...", tenant_id)
        await self.create_tenant_structure(
            tenant_id,
            {"name": tenant_id, "display_name": tenant_id},
        )
        return True

    async def _api_exists(self, tenant_id: str, api_name: str) -> bool:
        """Check if API already exists."""
        project = self._require_project()
        path = f"{self._get_api_path(tenant_id, api_name)}/api.yaml"

        def _check() -> bool:
            try:
                project.files.get(path, ref="main")
                return True
            except gitlab.exceptions.GitlabGetError:
                return False

        return await _gl_run(_check, "gitlab._api_exists")

    async def create_api(self, tenant_id: str, api_data: dict) -> str:
        """Create API definition in GitLab.

        C.6: this retains its pre-check because the failure mode is
        ``ValueError`` — the pre-check exists to return a specific error
        shape to callers, not to race-guard a write. The TOCTOU fix for
        writes lives in :meth:`write_file`.
        """
        project = self._require_project()
        api_name = api_data["name"]
        api_path = self._get_api_path(tenant_id, api_name)

        await self._ensure_tenant_exists(tenant_id)

        if await self._api_exists(tenant_id, api_name):
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

        actions: list[dict[str, Any]] = [
            {"action": "create", "file_path": f"{api_path}/api.yaml", "content": api_yaml},
            {"action": "create", "file_path": f"{api_path}/policies/.gitkeep", "content": ""},
        ]

        if api_data.get("openapi_spec"):
            actions.append(
                {
                    "action": "create",
                    "file_path": f"{api_path}/openapi.yaml",
                    "content": api_data["openapi_spec"],
                }
            )

        def _commit() -> None:
            try:
                project.commits.create(
                    {
                        "branch": "main",
                        "commit_message": f"Create API {api_name} for tenant {tenant_id}",
                        "actions": actions,
                    }
                )
            except gitlab.exceptions.GitlabCreateError as e:
                if "already exists" in str(e).lower():
                    raise ValueError(f"API '{api_name}' already exists for tenant '{tenant_id}'") from e
                raise

        try:
            await _gl_run(_commit, "gitlab.create_api", timeout=BATCH_TIMEOUT_S)
            logger.info("Created API %s for tenant %s", api_name, tenant_id)
            return api_data.get("id", api_name)
        except ValueError:
            raise
        except Exception as e:
            logger.error("Failed to create API: %s", e)
            raise

    async def get_api(self, tenant_id: str, api_name: str) -> dict | None:
        """Get API configuration from GitLab."""
        project = self._require_project()
        path = f"{self._get_api_path(tenant_id, api_name)}/api.yaml"

        def _get() -> dict | None:
            try:
                file = project.files.get(path, ref="main")
                raw_data = yaml.safe_load(file.decode())
                return _normalize_api_data(raw_data)
            except gitlab.exceptions.GitlabGetError:
                return None
            except yaml.YAMLError as e:
                logger.error("Failed to parse API YAML for %s: %s", api_name, e)
                return None

        return await _gl_run(_get, "gitlab.get_api")

    async def get_api_openapi_spec(self, tenant_id: str, api_name: str) -> dict | None:
        """Get OpenAPI specification for an API from GitLab."""
        project = self._require_project()
        base = self._get_api_path(tenant_id, api_name)

        def _fetch() -> dict | None:
            try:
                for filename in ("openapi.yaml", "openapi.yml", "openapi.json"):
                    try:
                        file = project.files.get(f"{base}/{filename}", ref="main")
                        content = file.decode()
                        if filename.endswith(".json"):
                            import json

                            return json.loads(content)
                        return yaml.safe_load(content)
                    except gitlab.exceptions.GitlabGetError:
                        continue
                return None
            except Exception as e:
                logger.error("Failed to get OpenAPI spec for %s: %s", api_name, e)
                return None

        return await _gl_run(_fetch, "gitlab.get_api_openapi_spec")

    async def list_apis(self, tenant_id: str) -> list[dict]:
        """List all APIs for a tenant."""
        project = self._require_project()
        base = f"{self._get_tenant_path(tenant_id)}/apis"

        def _list_dirs() -> list[str]:
            try:
                tree = project.repository_tree(path=base, ref="main")
            except gitlab.exceptions.GitlabGetError:
                return []
            return [item["name"] for item in tree if item["type"] == "tree" and item["name"] != ".gitkeep"]

        api_dirs = await _gl_run(_list_dirs, "gitlab.list_apis.dirs")
        apis: list[dict] = []
        for api_name in api_dirs:
            api = await self.get_api(tenant_id, api_name)
            if api:
                apis.append(api)
        return apis

    # ============================================================
    # CAB-688: Parallel fetch methods
    # ============================================================

    async def list_apis_parallel(self, tenant_id: str) -> list[dict]:
        """List APIs for a tenant with parallel fetching (CAB-688)."""
        project = self._require_project()
        base = f"{self._get_tenant_path(tenant_id)}/apis"

        def _list_dirs() -> list[str]:
            try:
                tree = project.repository_tree(path=base, ref="main")
            except gitlab.exceptions.GitlabGetError:
                return []
            return [item["name"] for item in tree if item["type"] == "tree" and item["name"] != ".gitkeep"]

        api_dirs = await _gl_run(_list_dirs, "gitlab.list_apis_parallel.dirs")

        async def fetch_api(api_id: str) -> dict | None:
            try:
                return await _fetch_with_protection(
                    lambda aid=api_id: self.get_api(tenant_id, aid),
                    f"api:{tenant_id}/{api_id}",
                )
            except Exception as e:
                logger.warning("Failed to fetch API %s/%s: %s", tenant_id, api_id, e)
                return None

        results = await asyncio.gather(*[fetch_api(aid) for aid in api_dirs])
        return [api for api in results if api is not None]

    async def get_all_openapi_specs_parallel(self, tenant_id: str, api_ids: list[str]) -> dict[str, dict | None]:
        """Fetch OpenAPI specs for multiple APIs in parallel (CAB-688)."""

        async def fetch_spec(api_id: str) -> tuple[str, dict | None]:
            try:
                spec = await _fetch_with_protection(
                    lambda aid=api_id: self.get_api_openapi_spec(tenant_id, aid),
                    f"openapi:{tenant_id}/{api_id}",
                )
                return (api_id, spec)
            except Exception as e:
                logger.warning("Failed to fetch OpenAPI spec %s/%s: %s", tenant_id, api_id, e)
                return (api_id, None)

        results = await asyncio.gather(*[fetch_spec(aid) for aid in api_ids])
        return dict(results)

    async def get_full_tree_recursive(self, path: str = "tenants") -> list[dict]:
        """Get full repository tree in ONE call (CAB-688 obligation #5)."""
        project = self._require_project()

        def _tree() -> list[dict]:
            return list(project.repository_tree(path=path, ref="main", recursive=True, per_page=1000, all=True))

        return await _gl_run(_tree, "gitlab.get_full_tree_recursive", timeout=BATCH_TIMEOUT_S)

    def parse_tree_to_tenant_apis(self, tree: list[dict]) -> dict[str, list[str]]:
        """Parse recursive tree into {tenant_id: [api_ids]} structure."""
        tenant_apis: dict[str, list[str]] = {}
        pattern = re.compile(r"^tenants/([^/]+)/apis/([^/]+)/api\.yaml$")

        for item in tree:
            if item["type"] == "blob":
                match = pattern.match(item["path"])
                if match:
                    tenant_id, api_id = match.groups()
                    tenant_apis.setdefault(tenant_id, []).append(api_id)

        return tenant_apis

    async def update_api(self, tenant_id: str, api_name: str, api_data: dict) -> bool:
        """Update API configuration in GitLab.

        Uses ``last_commit_id`` for optimistic concurrency (GitLab server
        rejects the save with 400 if another writer moved the pointer).
        """
        project = self._require_project()
        path = f"{self._get_api_path(tenant_id, api_name)}/api.yaml"

        def _update() -> None:
            file = project.files.get(path, ref="main")
            current = yaml.safe_load(file.decode())
            current.update(api_data)
            file.content = yaml.dump(current, default_flow_style=False, allow_unicode=True)
            save_kwargs: dict[str, Any] = {
                "branch": "main",
                "commit_message": f"Update API {api_name}",
            }
            last_commit_id = getattr(file, "last_commit_id", None)
            if isinstance(last_commit_id, str) and last_commit_id:
                save_kwargs["last_commit_id"] = last_commit_id
            file.save(**save_kwargs)

        try:
            await _gl_run(_update, "gitlab.update_api")
            logger.info("Updated API %s for tenant %s", api_name, tenant_id)
            return True
        except Exception as e:
            logger.error("Failed to update API: %s", e)
            raise

    async def delete_api(self, tenant_id: str, api_name: str) -> bool:
        """Delete API from GitLab."""
        project = self._require_project()
        api_path = self._get_api_path(tenant_id, api_name)

        def _delete() -> None:
            tree = project.repository_tree(path=api_path, ref="main", recursive=True)
            actions = [
                {"action": "delete", "file_path": item["path"]}
                for item in tree
                if item["type"] == "blob"
            ]
            if actions:
                project.commits.create(
                    {
                        "branch": "main",
                        "commit_message": f"Delete API {api_name}",
                        "actions": actions,
                    }
                )

        try:
            await _gl_run(_delete, "gitlab.delete_api", timeout=BATCH_TIMEOUT_S)
            logger.info("Deleted API %s for tenant %s", api_name, tenant_id)
            return True
        except Exception as e:
            logger.error("Failed to delete API: %s", e)
            raise

    # ============================================================
    # GitProvider ABC write methods (CAB-2011)
    # ============================================================

    async def create_file(
        self, project_id: str, file_path: str, content: str, commit_message: str, branch: str = "main"
    ) -> dict[str, Any]:
        """Create a new file in GitLab."""
        gl = self._require_gl()
        fallback = self._project

        def _create() -> dict[str, Any]:
            project = gl.projects.get(project_id) if project_id else fallback
            if project is None:
                raise RuntimeError("GitLab not connected")
            try:
                project.files.create(
                    {
                        "file_path": file_path,
                        "branch": branch,
                        "content": content,
                        "commit_message": commit_message,
                    }
                )
                return {"sha": "", "url": ""}
            except gitlab.exceptions.GitlabCreateError as e:
                if "already exists" in str(e).lower():
                    raise ValueError(f"File already exists: {file_path}") from e
                raise

        return await _gl_run(_create, "gitlab.create_file")

    async def update_file(
        self, project_id: str, file_path: str, content: str, commit_message: str, branch: str = "main"
    ) -> dict[str, Any]:
        """Update an existing file in GitLab (uses last_commit_id)."""
        gl = self._require_gl()
        fallback = self._project

        def _update() -> dict[str, Any]:
            project = gl.projects.get(project_id) if project_id else fallback
            if project is None:
                raise RuntimeError("GitLab not connected")
            try:
                f = project.files.get(file_path, ref=branch)
                f.content = content
                save_kwargs: dict[str, Any] = {"branch": branch, "commit_message": commit_message}
                last_commit_id = getattr(f, "last_commit_id", None)
                if isinstance(last_commit_id, str) and last_commit_id:
                    save_kwargs["last_commit_id"] = last_commit_id
                f.save(**save_kwargs)
                return {"sha": "", "url": ""}
            except gitlab.exceptions.GitlabGetError as e:
                raise FileNotFoundError(f"{file_path} not found") from e

        return await _gl_run(_update, "gitlab.update_file")

    async def delete_file(self, project_id: str, file_path: str, commit_message: str, branch: str = "main") -> bool:
        """Delete a file from GitLab (uses last_commit_id)."""
        gl = self._require_gl()
        fallback = self._project

        def _delete() -> bool:
            project = gl.projects.get(project_id) if project_id else fallback
            if project is None:
                raise RuntimeError("GitLab not connected")
            try:
                f = project.files.get(file_path, ref=branch)
                delete_kwargs: dict[str, Any] = {"branch": branch, "commit_message": commit_message}
                last_commit_id = getattr(f, "last_commit_id", None)
                if isinstance(last_commit_id, str) and last_commit_id:
                    delete_kwargs["last_commit_id"] = last_commit_id
                f.delete(**delete_kwargs)
                return True
            except gitlab.exceptions.GitlabGetError as e:
                raise FileNotFoundError(f"{file_path} not found") from e

        return await _gl_run(_delete, "gitlab.delete_file")

    async def batch_commit(
        self,
        project_id: str,
        actions: list[dict[str, str]],
        commit_message: str,
        branch: str = "main",
    ) -> dict[str, Any]:
        """Atomic multi-file commit via GitLab commits API."""
        gl = self._require_gl()
        fallback = self._project

        def _commit() -> dict[str, Any]:
            project = gl.projects.get(project_id) if project_id else fallback
            if project is None:
                raise RuntimeError("GitLab not connected")
            project.commits.create({"branch": branch, "commit_message": commit_message, "actions": actions})
            return {"sha": "", "url": ""}

        return await _gl_run(_commit, "gitlab.batch_commit", timeout=BATCH_TIMEOUT_S)

    # Git operations
    async def get_file(self, path: str, ref: str = "main") -> str | None:
        """Get file content from GitLab."""
        project = self._require_project()

        def _get() -> str | None:
            try:
                file = project.files.get(path, ref=ref)
                return file.decode().decode("utf-8")
            except gitlab.exceptions.GitlabGetError:
                return None

        return await _gl_run(_get, "gitlab.get_file")

    async def list_commits(self, path: str | None = None, limit: int = 20) -> list[dict]:
        """List commits for a path."""
        project = self._require_project()

        def _list() -> list[dict]:
            commits = project.commits.list(path=path, per_page=limit)
            return [
                {
                    "sha": c.id,
                    "message": c.message,
                    "author": c.author_name,
                    "date": c.created_at,
                }
                for c in commits
            ]

        return await _gl_run(_list, "gitlab.list_commits")

    # ===========================================
    # MCP Server GitOps Operations
    # ===========================================

    def _get_mcp_server_path(self, tenant_id: str, server_name: str) -> str:
        """Get the path for an MCP server definition."""
        if tenant_id == "_platform":
            return f"platform/mcp-servers/{server_name}"
        return f"{self._get_tenant_path(tenant_id)}/mcp-servers/{server_name}"

    def _normalize_mcp_server_data(self, raw_data: dict, git_path: str) -> dict:
        metadata = raw_data.get("metadata", {})
        spec = raw_data.get("spec", {})
        visibility = spec.get("visibility", {})
        subscription = spec.get("subscription", {})
        backend = spec.get("backend", {})

        tools = []
        for tool in spec.get("tools", []):
            tools.append(
                {
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
                }
            )

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

    async def get_mcp_server(self, tenant_id: str, server_name: str) -> dict | None:
        """Get MCP server configuration from GitLab."""
        project = self._require_project()
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        def _get() -> dict | None:
            try:
                file = project.files.get(f"{server_path}/server.yaml", ref="main")
                raw_data = yaml.safe_load(file.decode())
                return self._normalize_mcp_server_data(raw_data, server_path)
            except gitlab.exceptions.GitlabGetError:
                return None
            except yaml.YAMLError as e:
                logger.error("Failed to parse MCP server YAML for %s: %s", server_name, e)
                return None

        return await _gl_run(_get, "gitlab.get_mcp_server")

    async def list_mcp_servers(self, tenant_id: str = "_platform") -> list[dict]:
        """List all MCP servers for a tenant or platform."""
        project = self._require_project()
        base_path = (
            "platform/mcp-servers"
            if tenant_id == "_platform"
            else f"{self._get_tenant_path(tenant_id)}/mcp-servers"
        )

        def _list_names() -> list[str]:
            try:
                tree = project.repository_tree(path=base_path, ref="main")
            except gitlab.exceptions.GitlabGetError:
                return []
            return [item["name"] for item in tree if item["type"] == "tree" and item["name"] != ".gitkeep"]

        names = await _gl_run(_list_names, "gitlab.list_mcp_servers.names")
        servers: list[dict] = []
        for name in names:
            server = await self.get_mcp_server(tenant_id, name)
            if server:
                servers.append(server)
        return servers

    async def list_all_mcp_servers(self) -> list[dict]:
        """List all MCP servers across platform and all tenants."""
        project = self._require_project()
        all_servers: list[dict] = []

        platform_servers = await self.list_mcp_servers("_platform")
        all_servers.extend(platform_servers)

        def _list_tenant_ids() -> list[str]:
            try:
                tenants_tree = project.repository_tree(path="tenants", ref="main")
            except gitlab.exceptions.GitlabGetError:
                return []
            return [item["name"] for item in tenants_tree if item["type"] == "tree"]

        tenant_ids = await _gl_run(_list_tenant_ids, "gitlab.list_all_mcp_servers.tenants")
        for tenant_id in tenant_ids:
            tenant_servers = await self.list_mcp_servers(tenant_id)
            all_servers.extend(tenant_servers)
        return all_servers

    async def create_mcp_server(self, tenant_id: str, server_data: dict) -> str:
        """Create MCP server definition in GitLab."""
        project = self._require_project()
        server_name = server_data["name"]
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        existing = await self.get_mcp_server(tenant_id, server_name)
        if existing:
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

        def _commit() -> None:
            project.commits.create(
                {
                    "branch": "main",
                    "commit_message": f"Create MCP server {server_name}",
                    "actions": [
                        {
                            "action": "create",
                            "file_path": f"{server_path}/server.yaml",
                            "content": server_yaml,
                        },
                    ],
                }
            )

        try:
            await _gl_run(_commit, "gitlab.create_mcp_server", timeout=BATCH_TIMEOUT_S)
            logger.info("Created MCP server %s", server_name)
            return server_name
        except Exception as e:
            logger.error("Failed to create MCP server: %s", e)
            raise

    async def update_mcp_server(self, tenant_id: str, server_name: str, server_data: dict) -> bool:
        """Update MCP server configuration in GitLab."""
        project = self._require_project()
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        def _update() -> None:
            file = project.files.get(f"{server_path}/server.yaml", ref="main")
            current = yaml.safe_load(file.decode())

            if "spec" not in current:
                current["spec"] = {}

            for key, value in server_data.items():
                if key == "display_name":
                    current["spec"]["displayName"] = value
                elif key in ("description", "icon", "category", "status"):
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
            save_kwargs: dict[str, Any] = {
                "branch": "main",
                "commit_message": f"Update MCP server {server_name}",
            }
            last_commit_id = getattr(file, "last_commit_id", None)
            if isinstance(last_commit_id, str) and last_commit_id:
                save_kwargs["last_commit_id"] = last_commit_id
            file.save(**save_kwargs)

        try:
            await _gl_run(_update, "gitlab.update_mcp_server")
            logger.info("Updated MCP server %s", server_name)
            return True
        except Exception as e:
            logger.error("Failed to update MCP server: %s", e)
            raise

    async def delete_mcp_server(self, tenant_id: str, server_name: str) -> bool:
        """Delete MCP server from GitLab."""
        project = self._require_project()
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        def _delete() -> None:
            tree = project.repository_tree(path=server_path, ref="main", recursive=True)
            actions = [
                {"action": "delete", "file_path": item["path"]}
                for item in tree
                if item["type"] == "blob"
            ]
            if actions:
                project.commits.create(
                    {
                        "branch": "main",
                        "commit_message": f"Delete MCP server {server_name}",
                        "actions": actions,
                    }
                )

        try:
            await _gl_run(_delete, "gitlab.delete_mcp_server", timeout=BATCH_TIMEOUT_S)
            logger.info("Deleted MCP server %s", server_name)
            return True
        except Exception as e:
            logger.error("Failed to delete MCP server: %s", e)
            raise

    # ============================================================
    # CAB-1889 CP-1: provider-agnostic surface (GitProvider ABC).
    # ============================================================

    async def list_tree(self, path: str, ref: str = "main") -> list[TreeEntry]:
        project = self._require_project()

        def _list() -> list[TreeEntry]:
            try:
                tree = project.repository_tree(path=path, ref=ref)
            except gitlab.exceptions.GitlabGetError:
                return []
            return [TreeEntry(name=item["name"], type=item["type"], path=item["path"]) for item in tree]

        return await _gl_run(_list, "gitlab.list_tree")

    async def read_file(self, path: str, ref: str = "main") -> str | None:
        return await self.get_file(path, ref=ref)

    async def list_path_commits(self, path: str | None, limit: int = 20) -> list[CommitRef]:
        raw = await self.list_commits(path=path, limit=limit)
        return [CommitRef(sha=c["sha"], message=c["message"], author=c["author"], date=c["date"]) for c in raw]

    async def write_file(
        self, path: str, content: str, commit_message: str, branch: str = "main"
    ) -> Literal["created", "updated"]:
        """CP-1 C.6: create-first, fall through to update on 'already exists'.

        This closes the TOCTOU window from the prior _file_exists pre-check.
        It does not provide full compare-and-swap — two concurrent writers
        both hitting the 'already exists' branch can still lose one another's
        content. update_file passes ``last_commit_id`` for GitLab-side
        optimistic concurrency on that second step.
        """
        project_id = ""
        _ = self._require_project()
        try:
            await self.create_file(project_id, path, content, commit_message, branch=branch)
            return "created"
        except ValueError:
            await self.update_file(project_id, path, content, commit_message, branch=branch)
            return "updated"

    async def remove_file(self, path: str, commit_message: str, branch: str = "main") -> bool:
        project = self._require_project()

        def _delete() -> bool:
            project.files.delete(file_path=path, commit_message=commit_message, branch=branch)
            return True

        return await _gl_run(_delete, "gitlab.remove_file")

    async def list_branches(self) -> list[BranchRef]:
        project = self._require_project()

        def _list() -> list[BranchRef]:
            branches = project.branches.list()
            return [
                BranchRef(
                    name=b.name,
                    commit_sha=b.commit["id"] if isinstance(b.commit, dict) else str(b.commit),
                    protected=getattr(b, "protected", False),
                )
                for b in branches
            ]

        return await _gl_run(_list, "gitlab.list_branches")

    async def create_branch(self, name: str, ref: str = "main") -> BranchRef:
        project = self._require_project()

        def _create() -> BranchRef:
            b = project.branches.create({"branch": name, "ref": ref})
            return BranchRef(
                name=b.name,
                commit_sha=b.commit["id"] if isinstance(b.commit, dict) else str(b.commit),
                protected=getattr(b, "protected", False),
            )

        return await _gl_run(_create, "gitlab.create_branch")

    @staticmethod
    def _mr_to_ref(mr: Any) -> MergeRequestRef:
        author = mr.author.get("name", "") if isinstance(mr.author, dict) else str(mr.author)
        return MergeRequestRef(
            id=mr.id,
            iid=mr.iid,
            title=mr.title,
            description=mr.description or "",
            state=mr.state,
            source_branch=mr.source_branch,
            target_branch=mr.target_branch,
            web_url=mr.web_url,
            created_at=mr.created_at,
            author=author,
        )

    async def list_merge_requests(self, state: str = "opened") -> list[MergeRequestRef]:
        project = self._require_project()

        def _list() -> list[MergeRequestRef]:
            mrs = project.mergerequests.list(state=state)
            return [self._mr_to_ref(mr) for mr in mrs]

        return await _gl_run(_list, "gitlab.list_merge_requests")

    async def create_merge_request(
        self,
        title: str,
        description: str,
        source_branch: str,
        target_branch: str = "main",
    ) -> MergeRequestRef:
        project = self._require_project()

        def _create() -> MergeRequestRef:
            mr = project.mergerequests.create(
                {
                    "title": title,
                    "description": description,
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                }
            )
            return self._mr_to_ref(mr)

        return await _gl_run(_create, "gitlab.create_merge_request")

    async def merge_merge_request(self, iid: int) -> MergeRequestRef:
        project = self._require_project()

        def _merge() -> MergeRequestRef:
            mr = project.mergerequests.get(iid)
            mr.merge()
            return self._mr_to_ref(mr)

        return await _gl_run(_merge, "gitlab.merge_merge_request")


# Global instance
git_service = GitLabService()
