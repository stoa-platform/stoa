# catalog_git_client

`CatalogGitClient` Protocol + first PyGithub Contents API implementation for
`stoa-catalog`.

**Status**: Phase 3 scaffold. Protocol is figé; `GitHubContentsCatalogClient`
methods raise `NotImplementedError` until Phase 4.

## Spec

`specs/api-creation-gitops-rewrite.md` §6.7 (CAB-2184 B-CLIENT).

## Contract (5 methods, spec §6.7)

- `get(path)` → `RemoteFile | None`
- `create_or_update(path, content, expected_sha, actor, message)` →
  `RemoteCommit`
- `read_at_commit(path, commit_sha)` → `bytes | None`
- `latest_file_commit(path)` → `str`
- `list(glob_pattern)` → `list[str]`

No `git` CLI / worktree dependency. Reuses the existing
`services.github_service.GitHubService` PyGithub wrapper.
