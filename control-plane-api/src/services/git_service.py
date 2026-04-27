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
import itertools
import logging
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypeVar

import gitlab
import requests.exceptions  # type: ignore[import-untyped]
import yaml
from gitlab.v4.objects import Project

from ..config import settings
from .git_credentials import askpass_env, redact_token
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


_GLT = TypeVar("_GLT")


async def _gl_run(
    fn: Callable[[], _GLT],
    op_name: str,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> _GLT:
    """Run a sync python-gitlab closure under the uniform GitLab semaphore."""
    return await run_sync(fn, semaphore=GITLAB_SEMAPHORE, timeout=timeout, op_name=op_name)


# CP-1 P2 (M.5): transient error classifier for connect() retries. Kept
# at module scope so tests can monkey-patch it and so the policy is
# auditable without walking the retry loop.
_GITLAB_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def _is_transient_gitlab_error(exc: BaseException) -> bool:
    """Return True when ``exc`` is worth retrying at connect-time.

    Retry: network errors, asyncio/stdlib TimeoutError, GitLab HTTP
    errors with status in {429} or 5xx. Fail fast on auth errors (401/403)
    and any other exception class.
    """
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, gitlab.exceptions.GitlabAuthenticationError):
        return False
    if isinstance(exc, gitlab.exceptions.GitlabHttpError):
        status = getattr(exc, "response_code", None)
        return status in _GITLAB_RETRYABLE_STATUSES
    return False


class GitLabService(GitProvider):
    """GitLab implementation of GitProvider — GitOps source of truth."""

    def __init__(self) -> None:
        self._gl: gitlab.Gitlab | None = None
        self._project: Project | None = None

    async def connect(self) -> None:
        """Initialize GitLab connection with transient-error retry (CP-1 P2 M.5).

        3 attempts, 1s then 2s backoff between retries, 15s per-attempt
        timeout. Fails fast on auth errors — retrying a 401 doesn't help.
        """
        gl_cfg = settings.git.gitlab

        def _connect() -> tuple[gitlab.Gitlab, Project, str]:
            client = gitlab.Gitlab(gl_cfg.url, private_token=gl_cfg.token.get_secret_value())
            client.auth()
            project = client.projects.get(gl_cfg.project_id)
            # Materialise the scalar inside the closure so the log
            # line below does not trigger any lazy attribute access
            # on the event loop.
            return client, project, project.name

        max_attempts = 3
        backoffs = [1, 2]  # 3 attempts = 2 sleeps
        last_error: BaseException | None = None
        for attempt in range(max_attempts):
            try:
                self._gl, self._project, project_name = await _gl_run(
                    _connect, "gitlab.connect", timeout=15.0
                )
                logger.info("Connected to GitLab project: %s", project_name)
                return
            except Exception as exc:
                last_error = exc
                if not _is_transient_gitlab_error(exc):
                    logger.error("Failed to connect to GitLab (non-transient): %s", exc)
                    raise
                if attempt + 1 < max_attempts:
                    delay = backoffs[attempt]
                    logger.warning(
                        "GitLab connect attempt %d/%d failed (transient): %s. Retrying in %ds.",
                        attempt + 1, max_attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Failed to connect to GitLab after %d attempts: %s",
                        max_attempts, exc,
                    )
        assert last_error is not None  # max_attempts >= 1, loop always assigns last_error on failure
        raise last_error

    async def disconnect(self) -> None:
        """Close GitLab connection."""
        self._gl = None
        self._project = None

    async def get_head_commit_sha(self, ref: str | None = None) -> str | None:
        """Return the current HEAD commit SHA from GitLab.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        project = self._require_project()

        def _head() -> str | None:
            commits = project.commits.list(ref_name=effective_ref, per_page=1)
            if not commits:
                return None
            return commits[0].id

        return await _gl_run(_head, "gitlab.get_head_commit_sha")

    async def list_tenants(self) -> list[str]:
        """List tenant IDs from the catalog repository."""
        default_ref = settings.git.default_branch
        project = self._require_project()

        def _list() -> list[str]:
            try:
                tree = project.repository_tree(path="tenants", ref=default_ref)
            except gitlab.exceptions.GitlabGetError:
                return []
            return [item["name"] for item in tree if item["type"] == "tree"]

        return await _gl_run(_list, "gitlab.list_tenants")

    # ============================================================
    # GitProvider ABC implementations
    # ============================================================

    async def clone_repo(self, repo_url: str) -> Path:
        """Clone a GitLab repository to a temporary directory.

        CP-1 C.2: the token never appears in argv. It is passed to git
        through GIT_ASKPASS + env vars instead. ``repo_url`` must be a
        plain HTTPS URL (no user/token prefix).
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="stoa-gl-"))
        token = settings.git.gitlab.token.get_secret_value()
        with askpass_env(username="oauth2", password=token) as env:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--depth=1",
                repo_url,
                str(tmp_dir / "repo"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            _, stderr = await proc.communicate()
        if proc.returncode != 0:
            safe_stderr = redact_token(stderr.decode().strip(), token)
            raise RuntimeError(f"git clone failed: {safe_stderr}")
        return tmp_dir / "repo"

    async def get_file_content(self, project_id: str, file_path: str, ref: str | None = None) -> str:
        """Retrieve raw file content from GitLab.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        gl = self._require_gl()

        def _get() -> str:
            project = gl.projects.get(project_id)
            try:
                f = project.files.get(file_path, ref=effective_ref)
                return f.decode().decode("utf-8")
            except gitlab.exceptions.GitlabGetError as exc:
                raise FileNotFoundError(f"{file_path} not found in project {project_id}") from exc

        return await _gl_run(_get, "gitlab.get_file_content")

    async def list_files(self, project_id: str, path: str = "", ref: str | None = None) -> list[str]:
        """List files in a GitLab repository directory.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        gl = self._require_gl()

        def _list() -> list[str]:
            project = gl.projects.get(project_id)
            items = project.repository_tree(path=path, ref=effective_ref, per_page=100, all=True)
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

        default_branch = settings.git.default_branch

        def _commit() -> None:
            project.commits.create(
                {
                    "branch": default_branch,
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
        default_ref = settings.git.default_branch
        project = self._require_project()
        path = f"{self._get_tenant_path(tenant_id)}/tenant.yaml"

        def _get() -> dict | None:
            try:
                file = project.files.get(path, ref=default_ref)
                return yaml.safe_load(file.decode())
            except gitlab.exceptions.GitlabGetError:
                return None

        return await _gl_run(_get, "gitlab.get_tenant")

    async def _ensure_tenant_exists(self, tenant_id: str) -> bool:
        """Check if tenant exists, create structure if not."""
        default_ref = settings.git.default_branch
        project = self._require_project()
        path = f"{self._get_tenant_path(tenant_id)}/tenant.yaml"

        def _exists() -> bool:
            try:
                project.files.get(path, ref=default_ref)
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
        default_ref = settings.git.default_branch
        project = self._require_project()
        path = f"{self._get_api_path(tenant_id, api_name)}/api.yaml"

        def _check() -> bool:
            try:
                project.files.get(path, ref=default_ref)
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

        default_branch = settings.git.default_branch

        def _commit() -> None:
            try:
                project.commits.create(
                    {
                        "branch": default_branch,
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
        default_ref = settings.git.default_branch
        project = self._require_project()
        path = f"{self._get_api_path(tenant_id, api_name)}/api.yaml"

        def _get() -> dict | None:
            try:
                file = project.files.get(path, ref=default_ref)
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
        default_ref = settings.git.default_branch
        project = self._require_project()
        base = self._get_api_path(tenant_id, api_name)

        def _fetch() -> dict | None:
            try:
                for filename in ("openapi.yaml", "openapi.yml", "openapi.json"):
                    try:
                        file = project.files.get(f"{base}/{filename}", ref=default_ref)
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
        default_ref = settings.git.default_branch
        project = self._require_project()
        base = f"{self._get_tenant_path(tenant_id)}/apis"

        def _list_dirs() -> list[str]:
            try:
                tree = project.repository_tree(path=base, ref=default_ref)
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
        default_ref = settings.git.default_branch
        project = self._require_project()
        base = f"{self._get_tenant_path(tenant_id)}/apis"

        def _list_dirs() -> list[str]:
            try:
                tree = project.repository_tree(path=base, ref=default_ref)
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
        default_ref = settings.git.default_branch
        project = self._require_project()

        def _tree() -> list[dict]:
            return list(project.repository_tree(path=path, ref=default_ref, recursive=True, per_page=1000, all=True))

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
        default_branch = settings.git.default_branch
        project = self._require_project()
        path = f"{self._get_api_path(tenant_id, api_name)}/api.yaml"

        def _update() -> None:
            file = project.files.get(path, ref=default_branch)
            current = yaml.safe_load(file.decode())
            current.update(api_data)
            file.content = yaml.dump(current, default_flow_style=False, allow_unicode=True)
            save_kwargs: dict[str, Any] = {
                "branch": default_branch,
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
        default_branch = settings.git.default_branch
        project = self._require_project()
        api_path = self._get_api_path(tenant_id, api_name)

        def _delete() -> None:
            tree = project.repository_tree(path=api_path, ref=default_branch, recursive=True)
            actions = [
                {"action": "delete", "file_path": item["path"]}
                for item in tree
                if item["type"] == "blob"
            ]
            if actions:
                project.commits.create(
                    {
                        "branch": default_branch,
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
        self,
        project_id: str,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Create a new file in GitLab.

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
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
                        "branch": effective_branch,
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
        self,
        project_id: str,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing file in GitLab (uses last_commit_id).

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        gl = self._require_gl()
        fallback = self._project

        def _update() -> dict[str, Any]:
            project = gl.projects.get(project_id) if project_id else fallback
            if project is None:
                raise RuntimeError("GitLab not connected")
            try:
                f = project.files.get(file_path, ref=effective_branch)
                f.content = content
                save_kwargs: dict[str, Any] = {"branch": effective_branch, "commit_message": commit_message}
                last_commit_id = getattr(f, "last_commit_id", None)
                if isinstance(last_commit_id, str) and last_commit_id:
                    save_kwargs["last_commit_id"] = last_commit_id
                f.save(**save_kwargs)
                return {"sha": "", "url": ""}
            except gitlab.exceptions.GitlabGetError as e:
                raise FileNotFoundError(f"{file_path} not found") from e

        return await _gl_run(_update, "gitlab.update_file")

    async def delete_file(
        self,
        project_id: str,
        file_path: str,
        commit_message: str,
        branch: str | None = None,
    ) -> bool:
        """Delete a file from GitLab (uses last_commit_id).

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        gl = self._require_gl()
        fallback = self._project

        def _delete() -> bool:
            project = gl.projects.get(project_id) if project_id else fallback
            if project is None:
                raise RuntimeError("GitLab not connected")
            try:
                f = project.files.get(file_path, ref=effective_branch)
                delete_kwargs: dict[str, Any] = {"branch": effective_branch, "commit_message": commit_message}
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
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Atomic multi-file commit via GitLab commits API.

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        gl = self._require_gl()
        fallback = self._project

        def _commit() -> dict[str, Any]:
            project = gl.projects.get(project_id) if project_id else fallback
            if project is None:
                raise RuntimeError("GitLab not connected")
            project.commits.create(
                {"branch": effective_branch, "commit_message": commit_message, "actions": actions}
            )
            return {"sha": "", "url": ""}

        return await _gl_run(_commit, "gitlab.batch_commit", timeout=BATCH_TIMEOUT_S)

    # Git operations
    async def get_file(self, path: str, ref: str | None = None) -> str | None:
        """Get file content from GitLab.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        project = self._require_project()

        def _get() -> str | None:
            try:
                file = project.files.get(path, ref=effective_ref)
                return file.decode().decode("utf-8")
            except gitlab.exceptions.GitlabGetError:
                return None

        return await _gl_run(_get, "gitlab.get_file")

    async def list_commits(self, path: str | None = None, limit: int = 20) -> list[dict]:
        """List commits for a path.

        CP-1 P2 (L.1): paginate via ``iterator=True`` so requests with
        ``limit`` > 20 no longer silently truncate at the first page.
        """
        project = self._require_project()

        def _list() -> list[dict]:
            iterator = project.commits.list(
                path=path, per_page=min(limit, 100), iterator=True
            )
            return [
                {
                    "sha": c.id,
                    "message": c.message,
                    "author": c.author_name,
                    "date": c.created_at,
                }
                for c in itertools.islice(iterator, limit)
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
        default_ref = settings.git.default_branch
        project = self._require_project()
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        def _get() -> dict | None:
            try:
                file = project.files.get(f"{server_path}/server.yaml", ref=default_ref)
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
        default_ref = settings.git.default_branch
        project = self._require_project()
        base_path = (
            "platform/mcp-servers"
            if tenant_id == "_platform"
            else f"{self._get_tenant_path(tenant_id)}/mcp-servers"
        )

        def _list_names() -> list[str]:
            try:
                tree = project.repository_tree(path=base_path, ref=default_ref)
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
        """List all MCP servers across platform and all tenants.

        CP-1 P2 (M.6): fans out tenant listings via ``asyncio.gather`` so
        100 tenants no longer serialise into 100 round-trips. The provider
        semaphore ``GITLAB_SEMAPHORE`` inside ``_gl_run`` keeps the overall
        concurrency bounded.
        """
        default_ref = settings.git.default_branch
        project = self._require_project()

        def _list_tenant_ids() -> list[str]:
            try:
                tenants_tree = project.repository_tree(path="tenants", ref=default_ref)
            except gitlab.exceptions.GitlabGetError:
                return []
            return [item["name"] for item in tenants_tree if item["type"] == "tree"]

        # Fetch platform + tenant id list in parallel so the tenant
        # enumeration doesn't wait for platform.
        platform_servers_task = asyncio.create_task(self.list_mcp_servers("_platform"))
        tenant_ids = await _gl_run(_list_tenant_ids, "gitlab.list_all_mcp_servers.tenants")

        tenant_results = await asyncio.gather(
            *[self.list_mcp_servers(tid) for tid in tenant_ids]
        )
        platform_servers = await platform_servers_task

        return list(itertools.chain(platform_servers, *tenant_results))

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

        default_branch = settings.git.default_branch

        def _commit() -> None:
            project.commits.create(
                {
                    "branch": default_branch,
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
        default_branch = settings.git.default_branch
        project = self._require_project()
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        def _update() -> None:
            file = project.files.get(f"{server_path}/server.yaml", ref=default_branch)
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
                "branch": default_branch,
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
        default_branch = settings.git.default_branch
        project = self._require_project()
        server_path = self._get_mcp_server_path(tenant_id, server_name)

        def _delete() -> None:
            tree = project.repository_tree(path=server_path, ref=default_branch, recursive=True)
            actions = [
                {"action": "delete", "file_path": item["path"]}
                for item in tree
                if item["type"] == "blob"
            ]
            if actions:
                project.commits.create(
                    {
                        "branch": default_branch,
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

    async def list_tree(self, path: str, ref: str | None = None) -> list[TreeEntry]:
        """List immediate children of ``path`` in the catalog repo.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        project = self._require_project()

        def _list() -> list[TreeEntry]:
            try:
                tree = project.repository_tree(path=path, ref=effective_ref)
            except gitlab.exceptions.GitlabGetError:
                return []
            return [TreeEntry(name=item["name"], type=item["type"], path=item["path"]) for item in tree]

        return await _gl_run(_list, "gitlab.list_tree")

    async def read_file(self, path: str, ref: str | None = None) -> str | None:
        """Return catalog file content or ``None`` if missing.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        return await self.get_file(path, ref=ref)

    async def list_path_commits(self, path: str | None, limit: int = 20) -> list[CommitRef]:
        raw = await self.list_commits(path=path, limit=limit)
        return [CommitRef(sha=c["sha"], message=c["message"], author=c["author"], date=c["date"]) for c in raw]

    async def write_file(
        self, path: str, content: str, commit_message: str, branch: str | None = None
    ) -> Literal["created", "updated"]:
        """CP-1 C.6: create-first, fall through to update on 'already exists'.

        This closes the TOCTOU window from the prior _file_exists pre-check.
        It does not provide full compare-and-swap — two concurrent writers
        both hitting the 'already exists' branch can still lose one another's
        content. update_file passes ``last_commit_id`` for GitLab-side
        optimistic concurrency on that second step.

        CP-1 P2 (M.4): ``branch=None`` resolves to ``settings.git.default_branch``.
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        project_id = ""
        _ = self._require_project()
        try:
            await self.create_file(project_id, path, content, commit_message, branch=effective_branch)
            return "created"
        except ValueError:
            await self.update_file(project_id, path, content, commit_message, branch=effective_branch)
            return "updated"

    async def remove_file(self, path: str, commit_message: str, branch: str | None = None) -> bool:
        """Delete a file from the catalog repo.

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        project = self._require_project()

        def _delete() -> bool:
            project.files.delete(
                file_path=path, commit_message=commit_message, branch=effective_branch
            )
            return True

        return await _gl_run(_delete, "gitlab.remove_file")

    async def list_branches(self) -> list[BranchRef]:
        """List all branches on the catalog repo.

        CP-1 P2 (L.1): ``get_all=True`` so catalogs with >20 branches no
        longer silently truncate at the first page.
        """
        project = self._require_project()

        def _list() -> list[BranchRef]:
            branches = project.branches.list(get_all=True)
            return [
                BranchRef(
                    name=b.name,
                    commit_sha=b.commit["id"] if isinstance(b.commit, dict) else str(b.commit),
                    protected=getattr(b, "protected", False),
                )
                for b in branches
            ]

        return await _gl_run(_list, "gitlab.list_branches")

    async def create_branch(self, name: str, ref: str | None = None) -> BranchRef:
        """Create a branch on the catalog repo.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        project = self._require_project()

        def _create() -> BranchRef:
            b = project.branches.create({"branch": name, "ref": effective_ref})
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
        """List merge requests on the catalog repo.

        CP-1 P2 (L.1): ``get_all=True`` so catalogs with >20 open MRs no
        longer silently truncate at the first page.
        """
        project = self._require_project()

        def _list() -> list[MergeRequestRef]:
            mrs = project.mergerequests.list(state=state, get_all=True)
            return [self._mr_to_ref(mr) for mr in mrs]

        return await _gl_run(_list, "gitlab.list_merge_requests")

    async def create_merge_request(
        self,
        title: str,
        description: str,
        source_branch: str,
        target_branch: str | None = None,
    ) -> MergeRequestRef:
        """Open a merge request.

        ``target_branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_target = (
            target_branch if target_branch is not None else settings.git.default_branch
        )
        project = self._require_project()

        def _create() -> MergeRequestRef:
            mr = project.mergerequests.create(
                {
                    "title": title,
                    "description": description,
                    "source_branch": source_branch,
                    "target_branch": effective_target,
                }
            )
            return self._mr_to_ref(mr)

        return await _gl_run(_create, "gitlab.create_merge_request")

    async def merge_merge_request(self, iid: int) -> MergeRequestRef:
        """Merge an MR by iid.

        CP-1 P2 (M.2): idempotent when the MR is already merged. Short-circuits
        **only** on ``state == "merged"``; closed-unmerged still falls through
        to ``mr.merge()`` so the provider error surfaces correctly. python-gitlab
        mutates the MR instance during ``merge()``, so no re-fetch is needed.
        """
        project = self._require_project()

        def _merge() -> MergeRequestRef:
            mr = project.mergerequests.get(iid)
            if mr.state == "merged":
                return self._mr_to_ref(mr)
            mr.merge()
            return self._mr_to_ref(mr)

        return await _gl_run(_merge, "gitlab.merge_merge_request")


# Provider-aware global instance — must NOT be hardcoded to a single
# provider. The catalog reconciler and GitOps create path consume this
# singleton through GitHub-only adapters, so under GIT_PROVIDER=github
# this must resolve to GitHubService(). Lazy import below avoids the
# import cycle (git_provider lazy-imports back into this module).
from .git_provider import git_provider_factory  # noqa: E402

git_service = git_provider_factory()
