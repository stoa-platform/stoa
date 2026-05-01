"""GitHub implementation of GitProvider (CAB-1890 Wave 2, CAB-2011 write methods).

CP-1 (C.1/C.5): PyGithub is synchronous; every SDK call is routed through
:func:`.git_executor.run_sync` so the asyncio loop stays non-blocking.
Read calls acquire ``GITHUB_READ_SEMAPHORE`` (cap 10). Write calls on the
Repository Contents endpoints acquire ``GITHUB_CONTENTS_WRITE_SEMAPHORE``
(cap 1 — serial, per GitHub docs "Running this endpoint with parallel
requests is bound to cause errors"). Non-Contents writes (pull requests,
branches, webhooks) acquire ``GITHUB_META_WRITE_SEMAPHORE`` (cap 5).

CP-1 (C.6): ``write_file`` drops the ``_file_exists`` pre-check. It calls
``create_file`` first and falls through to ``update_file`` on the 422
"already exists" error.

Implementation rule (see git_executor.py): the ENTIRE SDK interaction —
including iteration over PyGithub ``PaginatedList`` objects and
``.decoded_content`` access on lazy ``ContentFile`` — must happen inside
the closure passed to ``run_sync``. Returning a lazy object and iterating
it after ``await`` would re-introduce the blocking sync-in-async pattern.
"""

import asyncio
import itertools
import json
import logging
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypeVar

import requests.exceptions  # type: ignore[import-untyped]
import yaml
from github import Auth, BadCredentialsException, Github, GithubException, InputGitTreeElement

from ..config import settings
from ..schemas.uac import UacContractSpec
from .git_credentials import askpass_env, redact_token
from .git_executor import (
    BATCH_TIMEOUT_S,
    DEFAULT_TIMEOUT_S,
    GITHUB_CONTENTS_WRITE_SEMAPHORE,
    GITHUB_META_WRITE_SEMAPHORE,
    GITHUB_READ_SEMAPHORE,
    run_sync,
)
from .git_provider import BranchRef, CommitRef, GitProvider, MergeRequestRef, TreeEntry
from .uac_transformer import transform_openapi_to_uac

logger = logging.getLogger(__name__)

_GHT = TypeVar("_GHT")


async def _gh_read(
    fn: Callable[[], _GHT],
    op_name: str,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> _GHT:
    """Run a sync PyGithub read closure under the read semaphore."""
    return await run_sync(fn, semaphore=GITHUB_READ_SEMAPHORE, timeout=timeout, op_name=op_name)


async def _gh_contents_write(
    fn: Callable[[], _GHT],
    op_name: str,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> _GHT:
    """Run a sync PyGithub Contents-API write under the serial (1) semaphore."""
    return await run_sync(fn, semaphore=GITHUB_CONTENTS_WRITE_SEMAPHORE, timeout=timeout, op_name=op_name)


async def _gh_meta_write(
    fn: Callable[[], _GHT],
    op_name: str,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> _GHT:
    """Run a sync PyGithub non-Contents write under the meta-write semaphore (5)."""
    return await run_sync(fn, semaphore=GITHUB_META_WRITE_SEMAPHORE, timeout=timeout, op_name=op_name)


# CP-1 P2 (M.5): transient error classifier for connect() retries. Kept
# at module scope so tests can monkey-patch it and so the retry policy
# is auditable without walking the retry loop.
_GITHUB_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_GITHUB_NON_RETRYABLE_STATUSES = frozenset({401, 403, 404})


def _is_transient_github_error(exc: BaseException) -> bool:
    """Return True when ``exc`` is worth retrying at connect-time.

    Retry: network errors, asyncio/stdlib TimeoutError, GitHub HTTP errors
    with status in {429} or 5xx. Fail fast on ``BadCredentialsException``
    and any ``GithubException`` with status 401/403/404, plus any other
    exception class.
    """
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, BadCredentialsException):
        return False
    if isinstance(exc, GithubException):
        status = getattr(exc, "status", None)
        if status in _GITHUB_NON_RETRYABLE_STATUSES:
            return False
        return status in _GITHUB_RETRYABLE_STATUSES
    return False


def _normalize_api_data(raw_data: dict) -> dict:
    """Normalize API data from GitHub YAML to the catalog sync format."""
    from src.services.catalog_api_definition import normalize_api_definition

    return normalize_api_definition(raw_data)


def _normalize_mcp_server_data(raw_data: dict, git_path: str) -> dict:
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


def _uac_name(raw: str) -> str:
    """Normalize an API identifier to UAC kebab-case."""
    value = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not value:
        return "api"
    return f"{value}-api" if len(value) < 2 else value


def _coerce_openapi_spec(raw: Any) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw) if raw.lstrip().startswith("{") else yaml.safe_load(raw)
        except (json.JSONDecodeError, yaml.YAMLError):
            return None
        return loaded if isinstance(loaded, dict) else None
    return None


def _openapi_file_content(raw: Any) -> str | None:
    spec = _coerce_openapi_spec(raw)
    if spec is not None:
        return yaml.dump(spec, default_flow_style=False, allow_unicode=True)
    return raw if isinstance(raw, str) and raw.strip() else None


def _uac_json_content(tenant_id: str, api_name: str, api_data: dict) -> str:
    """Build the canonical Git UAC JSON artifact for an API catalog entry."""
    contract_name = _uac_name(api_data.get("id") or api_name)
    openapi_spec = _coerce_openapi_spec(api_data.get("openapi_spec"))
    if openapi_spec:
        try:
            contract = transform_openapi_to_uac(
                openapi_spec,
                tenant_id=tenant_id,
                backend_base_url=api_data.get("backend_url") or None,
            )
            contract = contract.model_copy(
                update={
                    "name": contract_name,
                    "display_name": api_data.get("display_name") or api_name,
                    "version": api_data.get("version", contract.version),
                }
            )
        except ValueError:
            contract = UacContractSpec(
                name=contract_name,
                tenant_id=tenant_id,
                version=api_data.get("version", "1.0.0"),
                display_name=api_data.get("display_name") or api_name,
                description=api_data.get("description") or None,
            )
    else:
        contract = UacContractSpec(
            name=contract_name,
            tenant_id=tenant_id,
            version=api_data.get("version", "1.0.0"),
            display_name=api_data.get("display_name") or api_name,
            description=api_data.get("description") or None,
        )
        contract.refresh_policies()
    if not contract.required_policies:
        contract.refresh_policies()
    return json.dumps(contract.model_dump(mode="json", exclude_none=True), indent=2, sort_keys=True) + "\n"


class GitHubService(GitProvider):
    """GitHub implementation of GitProvider — GitOps source of truth."""

    def __init__(self) -> None:
        self._gh: Github | None = None

    async def connect(self) -> None:
        """Initialize GitHub connection with transient-error retry (CP-1 P2 M.5).

        3 attempts, 1s then 2s backoff between retries, 15s per-attempt
        timeout. Fails fast on credential/404 errors — retrying a 401
        or a missing repo doesn't help.
        """
        auth = Auth.Token(settings.git.github.token.get_secret_value())

        def _connect() -> tuple[Github, str]:
            client = Github(auth=auth)
            login = client.get_user().login
            return client, login

        max_attempts = 3
        backoffs = [1, 2]  # 3 attempts = 2 sleeps
        last_error: BaseException | None = None
        for attempt in range(max_attempts):
            try:
                self._gh, user = await _gh_read(_connect, "github.connect", timeout=15.0)
                logger.info("Connected to GitHub as %s", user)
                return
            except Exception as exc:
                last_error = exc
                if not _is_transient_github_error(exc):
                    logger.error("Failed to connect to GitHub (non-transient): %s", exc)
                    raise
                if attempt + 1 < max_attempts:
                    delay = backoffs[attempt]
                    logger.warning(
                        "GitHub connect attempt %d/%d failed (transient): %s. Retrying in %ds.",
                        attempt + 1,
                        max_attempts,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Failed to connect to GitHub after %d attempts: %s",
                        max_attempts,
                        exc,
                    )
        assert last_error is not None  # loop always assigns on failure
        raise last_error

    async def disconnect(self) -> None:
        """Close GitHub connection."""
        if self._gh:
            self._gh.close()
        self._gh = None

    def is_connected(self) -> bool:
        """Return True when the PyGithub client is initialized."""
        return self._gh is not None

    async def clone_repo(self, repo_url: str) -> Path:
        """Clone a GitHub repository to a temporary directory.

        CP-1 C.2: the token never appears in argv. It is passed to git
        through GIT_ASKPASS + env vars instead. ``repo_url`` must be a
        plain HTTPS URL (no user/token prefix).
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="stoa-gh-"))
        token = settings.git.github.token.get_secret_value()
        with askpass_env(username="x-access-token", password=token) as env:
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

    def _require_gh(self) -> Github:
        if not self._gh:
            raise RuntimeError("GitHub not connected")
        return self._gh

    def _get_repo(self, project_id: str) -> Any:
        """Return a PyGithub Repository object.

        Used by tests and legacy code; call-sites that need to run inside
        ``run_sync`` must fetch the repo inside the closure to avoid
        reintroducing C.1 via lazy object accesses.
        """
        return self._require_gh().get_repo(project_id)

    async def get_file_content(self, project_id: str, file_path: str, ref: str | None = None) -> str:
        """Retrieve raw file content from GitHub.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        gh = self._require_gh()

        def _get() -> str:
            repo = gh.get_repo(project_id)
            try:
                content_file = repo.get_contents(file_path, ref=effective_ref)
                if isinstance(content_file, list):
                    raise FileNotFoundError(f"{file_path} is a directory, not a file, in {project_id}")
                return content_file.decoded_content.decode("utf-8")
            except GithubException as exc:
                if exc.status == 404:
                    raise FileNotFoundError(f"{file_path} not found in project {project_id}") from exc
                raise

        return await _gh_read(_get, "github.get_file_content")

    async def list_files(self, project_id: str, path: str = "", ref: str | None = None) -> list[str]:
        """List files in a GitHub repository directory.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        gh = self._require_gh()

        def _list() -> list[str]:
            repo = gh.get_repo(project_id)
            try:
                contents = repo.get_contents(path, ref=effective_ref)
            except GithubException as exc:
                if exc.status == 404:
                    return []
                raise
            if not isinstance(contents, list):
                contents = [contents]
            return [item.path for item in contents]

        return await _gh_read(_list, "github.list_files")

    async def create_webhook(
        self,
        project_id: str,
        url: str,
        secret: str,
        events: list[str],
    ) -> dict[str, Any]:
        """Register a webhook on a GitHub repository (non-Contents write)."""
        gh = self._require_gh()

        def _create() -> dict[str, Any]:
            repo = gh.get_repo(project_id)
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

        return await _gh_meta_write(_create, "github.create_webhook")

    async def delete_webhook(self, project_id: str, hook_id: str) -> bool:
        """Remove a webhook from a GitHub repository (non-Contents write)."""
        gh = self._require_gh()

        def _delete() -> bool:
            repo = gh.get_repo(project_id)
            try:
                hook = repo.get_hook(int(hook_id))
                hook.delete()
                return True
            except GithubException as exc:
                if exc.status == 404:
                    return False
                raise

        return await _gh_meta_write(_delete, "github.delete_webhook")

    async def get_repo_info(self, project_id: str) -> dict[str, Any]:
        """Retrieve GitHub repository metadata."""
        gh = self._require_gh()

        def _info() -> dict[str, Any]:
            repo = gh.get_repo(project_id)
            return {
                "name": repo.name,
                "default_branch": repo.default_branch,
                "url": repo.html_url,
                "visibility": "private" if repo.private else "public",
            }

        return await _gh_read(_info, "github.get_repo_info")

    async def get_head_commit_sha(self, ref: str | None = None) -> str | None:
        """Return the HEAD commit SHA for the catalog branch.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _head() -> str | None:
            repo = gh.get_repo(project_id)
            try:
                branch = repo.get_branch(effective_ref)
            except GithubException as exc:
                if exc.status == 404:
                    return None
                raise
            return branch.commit.sha

        return await _gh_read(_head, "github.get_head_commit_sha")

    async def get_tenant(self, tenant_id: str) -> dict | None:
        """Return tenant metadata from tenant.yaml if present."""
        project_id = self._catalog_project_id()
        file_path = f"{self._get_tenant_path(tenant_id)}/tenant.yaml"
        try:
            content = await self.get_file_content(project_id, file_path)
        except FileNotFoundError:
            return None

        try:
            return yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            logger.error("Failed to parse tenant YAML for %s: %s", tenant_id, exc)
            return None

    async def list_tenants(self) -> list[str]:
        """List tenants from the catalog repository."""
        default_ref = settings.git.default_branch
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _list() -> list[str]:
            repo = gh.get_repo(project_id)
            try:
                contents = repo.get_contents("tenants", ref=default_ref)
            except GithubException as exc:
                if exc.status == 404:
                    return []
                raise
            if not isinstance(contents, list):
                contents = [contents]
            return [item.name for item in contents if item.type == "dir"]

        return await _gh_read(_list, "github.list_tenants")

    async def get_api(self, tenant_id: str, api_name: str) -> dict | None:
        """Return normalized API metadata from api.yaml."""
        project_id = self._catalog_project_id()
        file_path = f"{self._get_api_path(tenant_id, api_name)}/api.yaml"
        try:
            content = await self.get_file_content(project_id, file_path)
        except FileNotFoundError:
            return None

        try:
            raw_data = yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            logger.error("Failed to parse API YAML for %s/%s: %s", tenant_id, api_name, exc)
            return None

        return _normalize_api_data(raw_data)

    async def list_apis(self, tenant_id: str) -> list[dict]:
        """List APIs for a tenant from GitHub."""
        default_ref = settings.git.default_branch
        gh = self._require_gh()
        project_id = self._catalog_project_id()
        base_path = f"{self._get_tenant_path(tenant_id)}/apis"

        def _list_names() -> list[str]:
            repo = gh.get_repo(project_id)
            try:
                contents = repo.get_contents(base_path, ref=default_ref)
            except GithubException as exc:
                if exc.status == 404:
                    return []
                raise
            if not isinstance(contents, list):
                contents = [contents]
            return [item.name for item in contents if item.type == "dir" and item.name != ".gitkeep"]

        names = await _gh_read(_list_names, "github.list_apis.names")
        apis: list[dict] = []
        for name in names:
            api = await self.get_api(tenant_id, name)
            if api:
                apis.append(api)
        return apis

    async def list_apis_parallel(self, tenant_id: str) -> list[dict]:
        """List tenant APIs with concurrent GitHub fetches."""
        default_ref = settings.git.default_branch
        gh = self._require_gh()
        project_id = self._catalog_project_id()
        base_path = f"{self._get_tenant_path(tenant_id)}/apis"

        def _list_names() -> list[str]:
            repo = gh.get_repo(project_id)
            try:
                contents = repo.get_contents(base_path, ref=default_ref)
            except GithubException as exc:
                if exc.status == 404:
                    return []
                raise
            if not isinstance(contents, list):
                contents = [contents]
            return [item.name for item in contents if item.type == "dir" and item.name != ".gitkeep"]

        api_names = await _gh_read(_list_names, "github.list_apis_parallel.names")
        results = await asyncio.gather(*[self.get_api(tenant_id, name) for name in api_names])
        return [api for api in results if api is not None]

    async def get_api_openapi_spec(self, tenant_id: str, api_name: str) -> dict | None:
        """Return the parsed OpenAPI spec for a tenant API."""
        project_id = self._catalog_project_id()
        base_path = self._get_api_path(tenant_id, api_name)

        for filename in ("openapi.yaml", "openapi.yml", "openapi.json"):
            try:
                content = await self.get_file_content(project_id, f"{base_path}/{filename}")
            except FileNotFoundError:
                continue

            try:
                if filename.endswith(".json"):
                    return json.loads(content)
                return yaml.safe_load(content)
            except (json.JSONDecodeError, yaml.YAMLError) as exc:
                logger.error("Failed to parse OpenAPI spec for %s/%s (%s): %s", tenant_id, api_name, filename, exc)
                return None

        return None

    async def get_all_openapi_specs_parallel(self, tenant_id: str, api_ids: list[str]) -> dict[str, dict | None]:
        """Fetch OpenAPI specs for multiple APIs concurrently."""

        async def fetch_spec(api_id: str) -> tuple[str, dict | None]:
            return (api_id, await self.get_api_openapi_spec(tenant_id, api_id))

        results = await asyncio.gather(*[fetch_spec(api_id) for api_id in api_ids])
        return dict(results)

    async def get_full_tree_recursive(self, path: str = "tenants") -> list[dict]:
        """Return the recursive Git tree in the GitLab-compatible shape."""
        default_ref = settings.git.default_branch
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _tree() -> list[dict]:
            repo = gh.get_repo(project_id)
            branch = repo.get_branch(default_ref)
            tree = repo.get_git_tree(branch.commit.sha, recursive=True).tree
            prefix = f"{path}/"
            items: list[dict] = []
            for item in tree:
                if item.path != path and not item.path.startswith(prefix):
                    continue
                items.append(
                    {
                        "id": item.sha,
                        "name": Path(item.path).name,
                        "type": "tree" if item.type == "tree" else "blob",
                        "path": item.path,
                    }
                )
            return items

        return await _gh_read(_tree, "github.get_full_tree_recursive", timeout=BATCH_TIMEOUT_S)

    def parse_tree_to_tenant_apis(self, tree: list[dict]) -> dict[str, list[str]]:
        """Parse a recursive tree into {tenant_id: [api_ids]}."""
        tenant_apis: dict[str, list[str]] = {}
        pattern = re.compile(r"^tenants/([^/]+)/apis/([^/]+)/api\.yaml$")

        for item in tree:
            if item["type"] != "blob":
                continue
            match = pattern.match(item["path"])
            if not match:
                continue
            tenant_id, api_id = match.groups()
            tenant_apis.setdefault(tenant_id, []).append(api_id)

        return tenant_apis

    async def get_mcp_server(self, tenant_id: str, server_name: str) -> dict | None:
        """Return normalized MCP server metadata from server.yaml."""
        project_id = self._catalog_project_id()
        server_path = self._get_mcp_server_path(tenant_id, server_name)
        try:
            content = await self.get_file_content(project_id, f"{server_path}/server.yaml")
        except FileNotFoundError:
            return None

        try:
            raw_data = yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            logger.error("Failed to parse MCP server YAML for %s/%s: %s", tenant_id, server_name, exc)
            return None

        return _normalize_mcp_server_data(raw_data, server_path)

    async def list_mcp_servers(self, tenant_id: str = "_platform") -> list[dict]:
        """List MCP servers for a tenant or platform scope."""
        gh = self._require_gh()
        project_id = self._catalog_project_id()
        base_path = (
            "platform/mcp-servers" if tenant_id == "_platform" else f"{self._get_tenant_path(tenant_id)}/mcp-servers"
        )

        default_ref = settings.git.default_branch

        def _list_names() -> list[str]:
            repo = gh.get_repo(project_id)
            try:
                contents = repo.get_contents(base_path, ref=default_ref)
            except GithubException as exc:
                if exc.status == 404:
                    return []
                raise
            if not isinstance(contents, list):
                contents = [contents]
            return [item.name for item in contents if item.type == "dir" and item.name != ".gitkeep"]

        names = await _gh_read(_list_names, "github.list_mcp_servers.names")
        results = await asyncio.gather(*[self.get_mcp_server(tenant_id, name) for name in names])
        return [server for server in results if server is not None]

    async def list_all_mcp_servers(self) -> list[dict]:
        """List all MCP servers across platform and tenant scopes.

        CP-1 P2 (M.6): fans out tenant listings via ``asyncio.gather`` so
        100 tenants no longer serialise into 100 round-trips. The provider
        semaphore ``GITHUB_READ_SEMAPHORE`` inside ``_gh_read`` keeps the
        overall concurrency bounded.
        """
        platform_servers_task = asyncio.create_task(self.list_mcp_servers("_platform"))
        tenant_ids = await self.list_tenants()
        tenant_results = await asyncio.gather(*[self.list_mcp_servers(tid) for tid in tenant_ids])
        platform_servers = await platform_servers_task
        return list(itertools.chain(platform_servers, *tenant_results))

    # ============================================================
    # Write operations (CAB-2011: GitOps source of truth)
    # ============================================================

    async def create_file(
        self,
        project_id: str,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Create a new file in a GitHub repository (Contents API — serial).

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        gh = self._require_gh()

        def _create() -> dict[str, Any]:
            repo = gh.get_repo(project_id)
            try:
                result = repo.create_file(file_path, commit_message, content, branch=effective_branch)
                return {"sha": result["commit"].sha, "url": result["commit"].html_url}
            except GithubException as exc:
                if exc.status == 422 and "sha" in str(exc.data).lower():
                    raise ValueError(f"File already exists: {file_path}") from exc
                raise

        return await _gh_contents_write(_create, "github.create_file")

    async def update_file(
        self,
        project_id: str,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing file in a GitHub repository (Contents API — serial).

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        gh = self._require_gh()

        def _update() -> dict[str, Any]:
            repo = gh.get_repo(project_id)
            try:
                existing = repo.get_contents(file_path, ref=effective_branch)
                if isinstance(existing, list):
                    raise ValueError(f"{file_path} is a directory, not a file")
                result = repo.update_file(file_path, commit_message, content, existing.sha, branch=effective_branch)
                return {"sha": result["commit"].sha, "url": result["commit"].html_url}
            except GithubException as exc:
                if exc.status == 404:
                    raise FileNotFoundError(f"{file_path} not found in {project_id}") from exc
                raise

        return await _gh_contents_write(_update, "github.update_file")

    async def delete_file(
        self,
        project_id: str,
        file_path: str,
        commit_message: str,
        branch: str | None = None,
    ) -> bool:
        """Delete a file from a GitHub repository (Contents API — serial).

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        gh = self._require_gh()

        def _delete() -> bool:
            repo = gh.get_repo(project_id)
            try:
                existing = repo.get_contents(file_path, ref=effective_branch)
                if isinstance(existing, list):
                    raise ValueError(f"{file_path} is a directory, not a file")
                repo.delete_file(file_path, commit_message, existing.sha, branch=effective_branch)
                return True
            except GithubException as exc:
                if exc.status == 404:
                    raise FileNotFoundError(f"{file_path} not found in {project_id}") from exc
                raise

        return await _gh_contents_write(_delete, "github.delete_file")

    async def batch_commit(
        self,
        project_id: str,
        actions: list[dict[str, str]],
        commit_message: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Atomic multi-file commit via the Git Tree API.

        Uses the Git Data tree path (not strictly Contents), but held under
        the Contents-write semaphore to keep a single write lane and
        preserve the "no parallel mutations" invariant.

        ``branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        gh = self._require_gh()

        def _commit() -> dict[str, Any]:
            repo = gh.get_repo(project_id)
            ref = repo.get_git_ref(f"heads/{effective_branch}")
            base_sha = ref.object.sha
            base_tree = repo.get_git_tree(base_sha)

            tree_elements: list[InputGitTreeElement] = []
            for action in actions:
                act = action["action"]
                path = action["file_path"]
                if act in ("create", "update"):
                    content_value = action.get("content", "")
                    tree_elements.append(InputGitTreeElement(path, "100644", "blob", content=content_value))
                elif act == "delete":
                    tree_elements.append(InputGitTreeElement(path, "100644", "blob", sha=None))
                else:
                    raise ValueError(f"Unknown action: {act}. Must be create, update, or delete.")

            if not tree_elements:
                raise ValueError("No actions provided for batch commit")

            new_tree = repo.create_git_tree(tree_elements, base_tree=base_tree)
            new_commit = repo.create_git_commit(commit_message, new_tree, [repo.get_git_commit(base_sha)])
            ref.edit(new_commit.sha)
            logger.info(
                "Batch commit %s on %s/%s (%d actions)",
                new_commit.sha[:8],
                project_id,
                effective_branch,
                len(actions),
            )
            return {"sha": new_commit.sha, "url": new_commit.html_url}

        return await _gh_contents_write(_commit, "github.batch_commit", timeout=BATCH_TIMEOUT_S)

    async def create_pull_request(
        self,
        project_id: str,
        branch: str,
        title: str,
        body: str,
        actions: list[dict[str, str]],
        base: str | None = None,
    ) -> dict[str, Any]:
        """Create a branch with changes and open a pull request.

        ``base=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_base = base if base is not None else settings.git.default_branch
        gh = self._require_gh()

        def _create_branch() -> None:
            repo = gh.get_repo(project_id)
            base_ref = repo.get_git_ref(f"heads/{effective_base}")
            repo.create_git_ref(f"refs/heads/{branch}", base_ref.object.sha)

        await _gh_meta_write(_create_branch, "github.create_pr.branch")

        # batch_commit acquires its own contents-write semaphore
        await self.batch_commit(project_id, actions, title, branch=branch)

        def _open_pr() -> dict[str, Any]:
            repo = gh.get_repo(project_id)
            pr = repo.create_pull(title=title, body=body, head=branch, base=effective_base)
            logger.info("Created PR #%d on %s: %s", pr.number, project_id, title)
            return {"pr_number": pr.number, "url": pr.html_url}

        return await _gh_meta_write(_open_pr, "github.create_pr.open")

    # ============================================================
    # High-level catalog operations (CAB-2011)
    # ============================================================

    def _catalog_project_id(self) -> str:
        """Return the catalog repo in org/repo format."""
        return settings.git.github.catalog_project_id

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

    async def _file_exists(self, project_id: str, file_path: str, ref: str | None = None) -> bool:
        """Check if a file exists in the repository.

        NOTE (C.6): not used by :meth:`write_file` anymore. Retained for
        :meth:`create_api` / :meth:`update_api` where the pre-check is
        about producing a specific error shape to callers rather than
        race-guarding a write.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        try:
            await self.get_file_content(project_id, file_path, ref=ref)
            return True
        except FileNotFoundError:
            return False

    # --- Tenant operations ---

    async def create_tenant_structure(self, tenant_id: str, tenant_data: dict) -> bool:
        """Create initial tenant directory structure in GitHub."""
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

        The pre-existence check produces a specific ``ValueError`` shape
        for callers; the actual race-guard is handled at the batch_commit
        layer via the serial Contents-write semaphore.
        """
        project_id = self._catalog_project_id()
        api_name = api_data.get("id") or api_data["name"]
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

        actions: list[dict[str, Any]] = [
            {"action": "create", "file_path": f"{api_path}/api.yaml", "content": api_yaml},
            {
                "action": "create",
                "file_path": f"{api_path}/uac.json",
                "content": _uac_json_content(tenant_id, api_name, api_data),
            },
            {"action": "create", "file_path": f"{api_path}/policies/.gitkeep", "content": ""},
        ]

        openapi_content = _openapi_file_content(api_data.get("openapi_spec"))
        if openapi_content:
            actions.append({"action": "create", "file_path": f"{api_path}/openapi.yaml", "content": openapi_content})

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

        api_data = dict(api_data)
        overrides: dict[str, dict] = api_data.pop("overrides", {})

        current = yaml.safe_load(current_content)
        current.update({k: v for k, v in api_data.items() if k != "openapi_spec"})
        updated_yaml = yaml.dump(current, default_flow_style=False, allow_unicode=True)

        actions: list[dict[str, Any]] = [{"action": "update", "file_path": file_path, "content": updated_yaml}]
        uac_path = f"{api_path}/uac.json"
        actions.append(
            {
                "action": "update" if await self._file_exists(project_id, uac_path) else "create",
                "file_path": uac_path,
                "content": _uac_json_content(tenant_id, api_name, {**current, **api_data}),
            }
        )
        openapi_content = _openapi_file_content(api_data.get("openapi_spec"))
        if openapi_content:
            openapi_path = f"{api_path}/openapi.yaml"
            actions.append(
                {
                    "action": "update" if await self._file_exists(project_id, openapi_path) else "create",
                    "file_path": openapi_path,
                    "content": openapi_content,
                }
            )
        for env_name, env_config in overrides.items():
            override_path = f"{api_path}/overrides/{env_name}.yaml"
            override_yaml = yaml.dump(env_config, default_flow_style=False, allow_unicode=True)
            action = "update" if await self._file_exists(project_id, override_path) else "create"
            actions.append({"action": action, "file_path": override_path, "content": override_yaml})
        await self.batch_commit(project_id, actions=actions, commit_message=f"Update API {api_name}")

        logger.info("Updated API %s for tenant %s", api_name, tenant_id)
        return True

    async def delete_api(self, tenant_id: str, api_name: str) -> bool:
        """Delete API directory from GitHub."""
        default_ref = settings.git.default_branch
        project_id = self._catalog_project_id()
        api_path = self._get_api_path(tenant_id, api_name)
        gh = self._require_gh()

        def _collect_files() -> list[str]:
            repo = gh.get_repo(project_id)
            try:
                contents = repo.get_contents(api_path, ref=default_ref)
            except GithubException as exc:
                if exc.status == 404:
                    raise FileNotFoundError(f"API '{api_name}' not found for tenant '{tenant_id}'") from exc
                raise

            files_to_delete: list[str] = []
            stack = contents if isinstance(contents, list) else [contents]
            while stack:
                item = stack.pop()
                if item.type == "dir":
                    sub_contents = repo.get_contents(item.path, ref=default_ref)
                    stack.extend(sub_contents if isinstance(sub_contents, list) else [sub_contents])
                else:
                    files_to_delete.append(item.path)
            return files_to_delete

        files_to_delete = await _gh_read(_collect_files, "github.delete_api.collect", timeout=BATCH_TIMEOUT_S)

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
        default_ref = settings.git.default_branch
        project_id = self._catalog_project_id()
        server_path = self._get_mcp_server_path(tenant_id, server_name)
        gh = self._require_gh()

        def _collect_files() -> list[str]:
            repo = gh.get_repo(project_id)
            try:
                contents = repo.get_contents(server_path, ref=default_ref)
            except GithubException as exc:
                if exc.status == 404:
                    raise FileNotFoundError(f"MCP server '{server_name}' not found") from exc
                raise

            files_to_delete: list[str] = []
            stack = contents if isinstance(contents, list) else [contents]
            while stack:
                item = stack.pop()
                if item.type == "dir":
                    sub_contents = repo.get_contents(item.path, ref=default_ref)
                    stack.extend(sub_contents if isinstance(sub_contents, list) else [sub_contents])
                else:
                    files_to_delete.append(item.path)
            return files_to_delete

        files_to_delete = await _gh_read(_collect_files, "github.delete_mcp_server.collect", timeout=BATCH_TIMEOUT_S)

        if not files_to_delete:
            return True

        actions = [{"action": "delete", "file_path": f} for f in files_to_delete]
        await self.batch_commit(project_id, actions=actions, commit_message=f"Delete MCP server {server_name}")

        logger.info("Deleted MCP server %s", server_name)
        return True

    # ============================================================
    # CAB-1889 CP-1: provider-agnostic surface (GitProvider ABC).
    # ============================================================

    async def list_tree(self, path: str, ref: str | None = None) -> list[TreeEntry]:
        """List catalog tree children.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _list() -> list[TreeEntry]:
            repo = gh.get_repo(project_id)
            try:
                contents = repo.get_contents(path, ref=effective_ref)
            except GithubException as exc:
                if exc.status == 404:
                    return []
                raise
            # CP-1 H.6: GitHub's "Get repository content" returns a single
            # ContentFile for file paths and a list for directories. The
            # GitProvider contract is "enumerate children" — a file has no
            # children, so normalise to [] instead of propagating a singleton
            # blob. Matches python-gitlab behaviour on file paths.
            if not isinstance(contents, list):
                return []
            return [
                TreeEntry(
                    name=item.name,
                    type="tree" if item.type == "dir" else "blob",
                    path=item.path,
                )
                for item in contents
            ]

        return await _gh_read(_list, "github.list_tree")

    async def read_file(self, path: str, ref: str | None = None) -> str | None:
        """Return catalog file content or ``None`` if missing.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        try:
            return await self.get_file_content(self._catalog_project_id(), path, ref=ref)
        except FileNotFoundError:
            return None

    async def list_path_commits(self, path: str | None, limit: int = 20) -> list[CommitRef]:
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _list() -> list[CommitRef]:
            repo = gh.get_repo(project_id)
            kwargs: dict[str, Any] = {}
            if path:
                kwargs["path"] = path
            # PaginatedList slice + iteration happens inside the thread.
            commits = list(repo.get_commits(**kwargs)[:limit])
            refs: list[CommitRef] = []
            for c in commits:
                author = ""
                if c.author and getattr(c.author, "login", None):
                    author = c.author.login
                elif c.commit and c.commit.author and c.commit.author.name:
                    author = c.commit.author.name
                date = c.commit.author.date.isoformat() if c.commit and c.commit.author and c.commit.author.date else ""
                refs.append(
                    CommitRef(sha=c.sha, message=c.commit.message if c.commit else "", author=author, date=date)
                )
            return refs

        return await _gh_read(_list, "github.list_path_commits")

    async def write_file(
        self, path: str, content: str, commit_message: str, branch: str | None = None
    ) -> Literal["created", "updated"]:
        """CP-1 C.6: create-first, fall through to update on 'already exists'.

        Closes the TOCTOU window created by the old _file_exists pre-check.
        Does not provide full compare-and-swap — PyGithub's update_file
        already requires the blob sha (fetched inline in update_file), so
        the second leg is optimistic-concurrent per file.

        CP-1 P2 (M.4): ``branch=None`` resolves to ``settings.git.default_branch``.
        """
        effective_branch = branch if branch is not None else settings.git.default_branch
        project_id = self._catalog_project_id()
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
        return await self.delete_file(self._catalog_project_id(), path, commit_message, branch=branch)

    async def list_branches(self) -> list[BranchRef]:
        """List catalog branches.

        PyGithub's ``PaginatedList`` iterates transparently across pages,
        so there's no silent truncation to guard against (unlike GitLab's
        L.1 bug on ``project.branches.list()``). Included here for symmetry.
        """
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _list() -> list[BranchRef]:
            repo = gh.get_repo(project_id)
            # PyGithub PaginatedList — materialise inside the thread.
            return [
                BranchRef(name=b.name, commit_sha=b.commit.sha, protected=getattr(b, "protected", False))
                for b in repo.get_branches()
            ]

        return await _gh_read(_list, "github.list_branches")

    async def create_branch(self, name: str, ref: str | None = None) -> BranchRef:
        """Create a branch on the catalog repo.

        ``ref=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_ref = ref if ref is not None else settings.git.default_branch
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _create() -> BranchRef:
            repo = gh.get_repo(project_id)
            base_ref = repo.get_git_ref(f"heads/{effective_ref}")
            repo.create_git_ref(f"refs/heads/{name}", base_ref.object.sha)
            branch = repo.get_branch(name)
            return BranchRef(
                name=branch.name, commit_sha=branch.commit.sha, protected=getattr(branch, "protected", False)
            )

        return await _gh_meta_write(_create, "github.create_branch")

    @staticmethod
    def _pr_to_ref(pr: Any) -> MergeRequestRef:
        author = pr.user.login if pr.user and getattr(pr.user, "login", None) else ""
        created_at = pr.created_at.isoformat() if getattr(pr, "created_at", None) else ""
        return MergeRequestRef(
            id=pr.id,
            iid=pr.number,
            title=pr.title,
            description=pr.body or "",
            state=pr.state,
            source_branch=pr.head.ref if pr.head else "",
            target_branch=pr.base.ref if pr.base else "",
            web_url=pr.html_url,
            created_at=created_at,
            author=author,
        )

    @staticmethod
    def _map_mr_state_to_github(state: str) -> str:
        return {"opened": "open", "closed": "closed", "merged": "closed", "all": "all"}.get(state, state)

    async def list_merge_requests(self, state: str = "opened") -> list[MergeRequestRef]:
        gh = self._require_gh()
        project_id = self._catalog_project_id()
        gh_state = self._map_mr_state_to_github(state)

        def _list() -> list[MergeRequestRef]:
            repo = gh.get_repo(project_id)
            # PaginatedList iteration materialised inside the thread.
            return [self._pr_to_ref(pr) for pr in repo.get_pulls(state=gh_state)]

        return await _gh_read(_list, "github.list_merge_requests")

    async def create_merge_request(
        self,
        title: str,
        description: str,
        source_branch: str,
        target_branch: str | None = None,
    ) -> MergeRequestRef:
        """Open a pull request.

        ``target_branch=None`` resolves to ``settings.git.default_branch`` (CP-1 P2 M.4).
        """
        effective_target = target_branch if target_branch is not None else settings.git.default_branch
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _create() -> MergeRequestRef:
            repo = gh.get_repo(project_id)
            pr = repo.create_pull(title=title, body=description, head=source_branch, base=effective_target)
            return self._pr_to_ref(pr)

        return await _gh_meta_write(_create, "github.create_merge_request")

    async def merge_merge_request(self, iid: int) -> MergeRequestRef:
        """Merge a pull request by number.

        CP-1 P2 (M.2): idempotent when the PR is already merged. Short-circuits
        **only** on ``pr.merged is True``; closed-unmerged still falls through
        to ``pr.merge()`` so the provider error surfaces correctly. PyGithub's
        ``PullRequest.merge()`` does not mutate the instance in place — it
        returns a ``PullRequestMergeStatus`` — so a single re-fetch is needed
        after a successful merge to reflect the new state.
        """
        gh = self._require_gh()
        project_id = self._catalog_project_id()

        def _merge() -> MergeRequestRef:
            repo = gh.get_repo(project_id)
            pr = repo.get_pull(iid)
            if pr.merged:
                return self._pr_to_ref(pr)
            pr.merge()
            return self._pr_to_ref(repo.get_pull(iid))

        return await _gh_meta_write(_merge, "github.merge_merge_request")
