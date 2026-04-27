"""Remote file/commit value objects.

Spec §6.7 (CAB-2184 B-CLIENT).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteFile:
    """A file fetched from ``stoa-catalog``.

    ``content`` is the decoded bytes of the file (NOT base64). ``sha`` is the
    Git blob SHA returned by the Contents API; needed for optimistic CAS in
    ``create_or_update``.
    """

    path: str
    content: bytes
    sha: str


@dataclass(frozen=True)
class RemoteCommit:
    """A commit produced by ``create_or_update``.

    ``commit_sha`` is the commit SHA on the branch. ``file_sha`` is the new
    blob SHA of the file (returned by the Contents API).
    """

    commit_sha: str
    file_sha: str
    path: str
