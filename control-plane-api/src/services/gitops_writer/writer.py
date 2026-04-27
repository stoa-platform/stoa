"""GitOpsWriter — Phase 3 scaffold (NotImplementedError).

Spec §6.2 + §6.5 (CAB-2185 B-FLOW).

The 18-step flow is defined in spec §6.5. The implementation lands in Phase 4
once ``CatalogGitClient`` (CAB-2184) is wired up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ApiCreatePayload, CreateApiResult

if TYPE_CHECKING:
    from ..catalog_git_client.protocol import CatalogGitClient


class GitOpsWriter:
    """Git-first writer for ``POST /v1/tenants/{tid}/apis``.

    Phase 3: every method is a stub. Phase 4 implements the spec §6.5 flow
    (CAB-2185 B-FLOW). The contract is locked in spec §6.2 — three idempotent
    cases A/B/C, ``api_id`` returned is the slug never a UUID.
    """

    def __init__(
        self,
        *,
        catalog_git_client: CatalogGitClient | None = None,
    ) -> None:
        self._catalog_git_client = catalog_git_client

    def create_api(
        self,
        *,
        tenant_id: str,
        contract_payload: ApiCreatePayload,
        actor: str,
    ) -> CreateApiResult:
        """Create an API by committing ``api.yaml`` to ``stoa-catalog`` first.

        Phase 3 stub. See spec §6.5 for the 18-step flow.
        """
        raise NotImplementedError(
            "GitOpsWriter.create_api: stub Phase 3. "
            "Implementation in Phase 4 — see CAB-2185 (B-FLOW) "
            "and spec §6.5 (api-creation-gitops-rewrite.md)."
        )
