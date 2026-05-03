"""Portal publication adapter for API lifecycle operations."""

from __future__ import annotations

from copy import deepcopy

from src.models.catalog import APICatalog

from .ports import PortalPublicationState


class CatalogPortalPublisher:
    """Publishes an API to the STOA Portal by updating the catalog visibility state."""

    async def publish(
        self,
        *,
        api: APICatalog,
        publication: PortalPublicationState,
    ) -> APICatalog:
        metadata = deepcopy(api.api_metadata or {}) if isinstance(api.api_metadata, dict) else {}
        lifecycle = dict(metadata.get("lifecycle") or {})
        publications = dict(lifecycle.get("portal_publications") or {})
        key = _publication_key(publication.environment, publication.gateway_instance_id)
        publication_payload = {
            "environment": publication.environment,
            "gateway_instance_id": str(publication.gateway_instance_id),
            "deployment_id": str(publication.deployment_id),
            "publication_status": publication.publication_status,
            "result": publication.result,
            "spec_hash": publication.spec_hash,
            "published_at": publication.published_at.isoformat(),
            "source": "api_lifecycle",
        }
        publications[key] = publication_payload
        lifecycle["portal_publications"] = publications
        lifecycle["portal_last_publication"] = publication_payload
        metadata["lifecycle"] = lifecycle

        api.api_metadata = metadata
        api.portal_published = True
        return api


def _publication_key(environment: str, gateway_instance_id) -> str:
    return f"{environment}:{gateway_instance_id}"
