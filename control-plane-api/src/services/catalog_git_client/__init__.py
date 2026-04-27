"""Catalog Git client abstraction — Phase 3 scaffold.

Spec §6.7 (CAB-2184 B-CLIENT).

Reads/writes ``stoa-catalog`` via PyGithub Contents API (no worktree, no
``git push`` CLI). The Protocol is figé in this scaffold; the
``GitHubContentsCatalogClient`` implementation lands in Phase 4.
"""

from .github_contents import CatalogShaConflictError, GitHubContentsCatalogClient
from .models import RemoteCommit, RemoteFile
from .protocol import CatalogGitClient

__all__ = [
    "CatalogGitClient",
    "CatalogShaConflictError",
    "GitHubContentsCatalogClient",
    "RemoteCommit",
    "RemoteFile",
]
