"""Canonical API lifecycle service."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.promotion import Promotion, PromotionStatus, validate_promotion_chain
from src.services.catalog_api_definition import environment_matches, normalize_environment
from src.services.gateway_deployment_service import GatewayDeploymentService

from .errors import (
    ApiLifecycleConflictError,
    ApiLifecycleGatewayAmbiguousError,
    ApiLifecycleGatewayNotFoundError,
    ApiLifecycleNotFoundError,
    ApiLifecycleSpecValidationError,
    ApiLifecycleTransitionError,
    ApiLifecycleValidationError,
)
from .openapi import parse_openapi_contract, validate_openapi_contract
from .portal import CatalogPortalPublisher
from .portal_tags import find_legacy_portal_publication_tags
from .ports import (
    ApiDeploymentRequestOutcome,
    ApiDraftValidationOutcome,
    ApiLifecycleRepository,
    ApiLifecycleState,
    ApiPortalPublicationOutcome,
    ApiPromotionRequestOutcome,
    ApiSpecState,
    CreateApiDraftCommand,
    DeployApiCommand,
    DraftValidationResult,
    GatewayDeploymentState,
    GatewayTarget,
    LifecycleActor,
    LifecycleAuditSink,
    PortalLifecycleState,
    PortalPublicationState,
    PortalPublisherPort,
    PromoteApiCommand,
    PromotionState,
    PublishApiCommand,
    ValidateApiDraftCommand,
)


class ApiLifecycleService:
    """Coordinates the lifecycle of one catalog API across STOA control-plane state."""

    def __init__(
        self,
        repository: ApiLifecycleRepository,
        audit_sink: LifecycleAuditSink,
        portal_publisher: PortalPublisherPort | None = None,
    ):
        self.repository = repository
        self.audit_sink = audit_sink
        self.portal_publisher = portal_publisher or CatalogPortalPublisher()

    async def create_draft(self, command: CreateApiDraftCommand, actor: LifecycleActor) -> ApiLifecycleState:
        """Create a catalog draft without deploying or publishing it."""
        normalized = self._normalize_create_command(command)
        forbidden_tags = find_legacy_portal_publication_tags(normalized.tags)
        if forbidden_tags:
            raise ApiLifecycleValidationError(
                "Portal publication must use the lifecycle publish action, not catalog tags: "
                + ", ".join(forbidden_tags)
            )

        existing = await self.repository.get_api_by_name_version(
            normalized.tenant_id,
            normalized.name,
            normalized.version,
        )
        if existing:
            raise ApiLifecycleConflictError(
                f"API '{normalized.name}' version '{normalized.version}' already exists in this tenant"
            )

        api_id = _slugify(normalized.name)
        existing_api_id = await self.repository.get_api_by_id(normalized.tenant_id, api_id)
        if existing_api_id:
            raise ApiLifecycleConflictError(f"API id '{api_id}' already exists in this tenant")

        parsed_spec = parse_openapi_contract(normalized.openapi_spec)
        if not parsed_spec and not normalized.spec_reference:
            raise ApiLifecycleValidationError("API OpenAPI spec or spec_reference is required")

        catalog_metadata = {
            "name": normalized.name,
            "display_name": normalized.display_name,
            "version": normalized.version,
            "description": normalized.description,
            "backend_url": normalized.backend_url,
            "tags": list(normalized.tags),
            "owner_team": normalized.owner_team,
            "status": "draft",
            "lifecycle": {
                "catalog_status": "draft",
                "spec_source": "inline" if parsed_spec else "reference" if normalized.spec_reference else "missing",
                "spec_reference": normalized.spec_reference,
            },
        }

        api = APICatalog(
            id=uuid4(),
            tenant_id=normalized.tenant_id,
            api_id=api_id,
            api_name=normalized.name,
            version=normalized.version,
            status="draft",
            tags=list(normalized.tags),
            portal_published=False,
            api_metadata=catalog_metadata,
            openapi_spec=parsed_spec,
            synced_at=datetime.now(UTC),
        )

        created = await self.repository.create_api_catalog(api)
        await self.audit_sink.record_transition(
            tenant_id=created.tenant_id,
            actor=actor,
            action="api_lifecycle.create_draft",
            resource_id=created.api_id,
            resource_name=created.api_name,
            details={
                "api_id": created.api_id,
                "api_name": created.api_name,
                "version": created.version,
                "catalog_status": created.status,
                "spec_source": catalog_metadata["lifecycle"]["spec_source"],
                "portal_published": created.portal_published,
            },
            outcome="success",
            status_code=201,
            path=f"/v1/tenants/{created.tenant_id}/apis/lifecycle/drafts",
        )
        return await self._state_from_catalog(created)

    async def validate_draft(
        self,
        command: ValidateApiDraftCommand,
        actor: LifecycleActor,
    ) -> ApiDraftValidationOutcome:
        """Validate a catalog draft and mark it ready for deployment."""
        api = await self.repository.get_api_by_id(command.tenant_id, command.api_id)
        if not api:
            raise ApiLifecycleNotFoundError(f"API '{command.api_id}' was not found")

        if api.status == "archived":
            await self._audit_validation_failure(
                api,
                actor,
                code="transition_archived",
                message="Archived APIs cannot be validated",
                status_code=409,
            )
            raise ApiLifecycleTransitionError("Archived APIs cannot be validated")
        if api.status not in {"draft", "ready"}:
            await self._audit_validation_failure(
                api,
                actor,
                code="transition_invalid",
                message=f"API status '{api.status}' cannot be validated",
                status_code=409,
            )
            raise ApiLifecycleTransitionError(f"API status '{api.status}' cannot be validated")

        spec_source = _spec_state(api).source
        if not api.openapi_spec:
            reference = _spec_state(api).reference
            if reference:
                message = f"Spec reference cannot be resolved yet: {reference}"
                await self._audit_validation_failure(
                    api,
                    actor,
                    code="spec_reference_unresolved",
                    message=message,
                    status_code=422,
                )
                raise ApiLifecycleSpecValidationError("spec_reference_unresolved", message)

        try:
            openapi_result = validate_openapi_contract(api.openapi_spec)
        except ApiLifecycleSpecValidationError as exc:
            await self._audit_validation_failure(
                api,
                actor,
                code=exc.code,
                message=str(exc),
                status_code=422,
            )
            raise

        validated_at = datetime.now(UTC)
        validation_hash = _spec_fingerprint(api.openapi_spec)
        metadata = _metadata_copy(api)
        lifecycle = dict(metadata.get("lifecycle") or {})
        previous_hash = lifecycle.get("validation_spec_hash")
        if api.status == "ready" and previous_hash and previous_hash != validation_hash:
            await self._audit_validation_failure(
                api,
                actor,
                code="ready_spec_changed",
                message="Ready API spec changed; return the API to draft before validating again",
                status_code=409,
            )
            raise ApiLifecycleTransitionError("Ready API spec changed; return the API to draft before validating again")

        lifecycle.update(
            {
                "catalog_status": "ready",
                "validated_at": validated_at.isoformat(),
                "validation_spec_hash": validation_hash,
                "validation_result": {
                    "valid": True,
                    "code": openapi_result.code,
                    "message": openapi_result.message,
                    "spec_source": spec_source,
                    "spec_format": openapi_result.spec_format,
                    "spec_version": openapi_result.spec_version,
                    "title": openapi_result.title,
                    "version": openapi_result.version,
                    "path_count": openapi_result.path_count,
                    "operation_count": openapi_result.operation_count,
                },
            }
        )
        metadata["status"] = "ready"
        metadata["lifecycle"] = lifecycle

        api.status = "ready"
        api.api_metadata = metadata
        saved = await self.repository.save_api_catalog(api)
        validation = DraftValidationResult(
            valid=True,
            code=openapi_result.code,
            message=openapi_result.message,
            spec_source=spec_source,
            spec_format=openapi_result.spec_format,
            spec_version=openapi_result.spec_version,
            title=openapi_result.title,
            version=openapi_result.version,
            path_count=openapi_result.path_count,
            operation_count=openapi_result.operation_count,
            validated_at=validated_at,
        )
        await self.audit_sink.record_transition(
            tenant_id=saved.tenant_id,
            actor=actor,
            action="api_lifecycle.validate_draft",
            resource_id=saved.api_id,
            resource_name=saved.api_name,
            details={
                "api_id": saved.api_id,
                "api_name": saved.api_name,
                "version": saved.version,
                "catalog_status": saved.status,
                "validation": {
                    "code": validation.code,
                    "spec_source": validation.spec_source,
                    "spec_format": validation.spec_format,
                    "spec_version": validation.spec_version,
                    "path_count": validation.path_count,
                    "operation_count": validation.operation_count,
                },
                "reason": command.reason,
            },
            outcome="success",
            status_code=200,
            path=f"/v1/tenants/{saved.tenant_id}/apis/{saved.api_id}/lifecycle/validate",
        )
        return ApiDraftValidationOutcome(
            tenant_id=saved.tenant_id,
            api_id=saved.api_id,
            status=saved.status,
            validation=validation,
            lifecycle_state=await self._state_from_catalog(saved),
        )

    async def deploy_to_environment(
        self,
        command: DeployApiCommand,
        actor: LifecycleActor,
    ) -> ApiDeploymentRequestOutcome:
        """Request runtime deployment by materializing a GatewayDeployment row."""
        environment = _normalize_deployment_environment(command.environment)
        api = await self.repository.get_api_by_id(command.tenant_id, command.api_id)
        if not api:
            raise ApiLifecycleNotFoundError(f"API '{command.api_id}' was not found")

        if api.status != "ready":
            await self._audit_deploy_failure(
                api,
                actor,
                environment=environment,
                code="transition_invalid",
                message=f"API status '{api.status}' cannot be deployed; validate the draft first",
                status_code=409,
            )
            raise ApiLifecycleTransitionError(f"API status '{api.status}' cannot be deployed; validate the draft first")

        try:
            gateway = await self._resolve_gateway_target(command.tenant_id, environment, command.gateway_instance_id)
        except (
            ApiLifecycleGatewayNotFoundError,
            ApiLifecycleGatewayAmbiguousError,
            ApiLifecycleValidationError,
        ) as exc:
            failure_status = 404 if isinstance(exc, ApiLifecycleGatewayNotFoundError) else 409
            if isinstance(exc, ApiLifecycleValidationError):
                failure_status = 422
            await self._audit_deploy_failure(
                api,
                actor,
                environment=environment,
                code=exc.__class__.__name__,
                message=str(exc),
                status_code=failure_status,
            )
            raise
        desired_state = {
            **GatewayDeploymentService.build_desired_state(api),
            "target_environment": environment,
            "target_gateway_name": gateway.name,
            "target_source": "api_lifecycle",
        }
        deployment, action = await self._upsert_gateway_deployment(api, gateway, desired_state, command.force)
        audit_action = "api_lifecycle.deploy_idempotent" if action == "unchanged" else "api_lifecycle.deploy_requested"
        await self.audit_sink.record_transition(
            tenant_id=api.tenant_id,
            actor=actor,
            action=audit_action,
            resource_id=api.api_id,
            resource_name=api.api_name,
            details={
                "api_id": api.api_id,
                "api_name": api.api_name,
                "version": api.version,
                "catalog_status": api.status,
                "environment": environment,
                "gateway_instance_id": str(gateway.id),
                "gateway_name": gateway.name,
                "deployment_id": str(deployment.id),
                "deployment_status": _wire_value(deployment.sync_status),
                "action": action,
            },
            outcome="success",
            status_code=200,
            path=f"/v1/tenants/{api.tenant_id}/apis/{api.api_id}/lifecycle/deployments",
        )
        return ApiDeploymentRequestOutcome(
            tenant_id=api.tenant_id,
            api_id=api.api_id,
            environment=environment,
            gateway_instance_id=gateway.id,
            deployment_id=deployment.id,
            deployment_status=_wire_value(deployment.sync_status),
            action=action,
            lifecycle_state=await self._state_from_catalog(api),
        )

    async def publish_to_portal(
        self,
        command: PublishApiCommand,
        actor: LifecycleActor,
    ) -> ApiPortalPublicationOutcome:
        """Publish a synced API deployment to the portal catalog."""
        environment = _normalize_deployment_environment(command.environment)
        api = await self.repository.get_api_by_id(command.tenant_id, command.api_id)
        if not api:
            raise ApiLifecycleNotFoundError(f"API '{command.api_id}' was not found")

        if api.status != "ready":
            await self._audit_publish_failure(
                api,
                actor,
                environment=environment,
                code="transition_invalid",
                message=f"API status '{api.status}' cannot be published; validate the draft first",
                status_code=409,
            )
            raise ApiLifecycleTransitionError(
                f"API status '{api.status}' cannot be published; validate the draft first"
            )

        gateway = await self._resolve_publish_gateway(
            command.tenant_id, environment, command.gateway_instance_id, api, actor
        )
        deployment = await self.repository.get_gateway_deployment(api.id, gateway.id)
        if not deployment:
            await self._audit_publish_failure(
                api,
                actor,
                environment=environment,
                code="deployment_not_found",
                message=f"No GatewayDeployment found for gateway '{gateway.name}'",
                status_code=404,
                gateway_instance_id=gateway.id,
            )
            raise ApiLifecycleNotFoundError(f"No GatewayDeployment found for gateway '{gateway.name}'")
        if _wire_value(deployment.sync_status) != DeploymentSyncStatus.SYNCED.value:
            await self._audit_publish_failure(
                api,
                actor,
                environment=environment,
                code="deployment_not_synced",
                message=f"Deployment '{deployment.id}' is '{_wire_value(deployment.sync_status)}', not 'synced'",
                status_code=409,
                gateway_instance_id=gateway.id,
                deployment_id=deployment.id,
            )
            raise ApiLifecycleTransitionError(
                f"Deployment '{deployment.id}' is '{_wire_value(deployment.sync_status)}', not 'synced'"
            )

        validation_result = await self._validate_publishable_spec(api, actor, environment, gateway.id, deployment.id)
        spec_hash = _spec_fingerprint(api.openapi_spec)
        previous = _portal_publication_record(api, environment, gateway.id)
        if (
            previous
            and api.portal_published
            and previous.get("spec_hash") == spec_hash
            and previous.get("deployment_id") == str(deployment.id)
            and not command.force
        ):
            await self._complete_promotion_for_publication(
                api=api,
                actor=actor,
                environment=environment,
                gateway_instance_id=gateway.id,
                deployment_id=deployment.id,
            )
            await self.audit_sink.record_transition(
                tenant_id=api.tenant_id,
                actor=actor,
                action="api_lifecycle.publish_idempotent",
                resource_id=api.api_id,
                resource_name=api.api_name,
                details={
                    "api_id": api.api_id,
                    "api_name": api.api_name,
                    "environment": environment,
                    "gateway_instance_id": str(gateway.id),
                    "deployment_id": str(deployment.id),
                    "result": "unchanged",
                },
                outcome="success",
                status_code=200,
                path=f"/v1/tenants/{api.tenant_id}/apis/{api.api_id}/lifecycle/publications",
            )
            return ApiPortalPublicationOutcome(
                tenant_id=api.tenant_id,
                api_id=api.api_id,
                environment=environment,
                gateway_instance_id=gateway.id,
                deployment_id=deployment.id,
                publication_status="published",
                portal_published=True,
                result="unchanged",
                lifecycle_state=await self._state_from_catalog(api),
            )

        result = "republished" if previous else "published"
        published_at = datetime.now(UTC)
        publication = PortalPublicationState(
            environment=environment,
            gateway_instance_id=gateway.id,
            deployment_id=deployment.id,
            publication_status="published",
            result=result,
            spec_hash=spec_hash,
            published_at=published_at,
        )
        published_api = await self.portal_publisher.publish(api=api, publication=publication)
        saved = await self.repository.save_api_catalog(published_api)
        await self.audit_sink.record_transition(
            tenant_id=saved.tenant_id,
            actor=actor,
            action="api_lifecycle.publish_requested",
            resource_id=saved.api_id,
            resource_name=saved.api_name,
            details={
                "api_id": saved.api_id,
                "api_name": saved.api_name,
                "version": saved.version,
                "catalog_status": saved.status,
                "environment": environment,
                "gateway_instance_id": str(gateway.id),
                "gateway_name": gateway.name,
                "deployment_id": str(deployment.id),
                "deployment_status": _wire_value(deployment.sync_status),
                "publication_status": "published",
                "result": result,
                "spec": {
                    "code": validation_result.code,
                    "spec_format": validation_result.spec_format,
                    "spec_version": validation_result.spec_version,
                },
            },
            outcome="success",
            status_code=200,
            path=f"/v1/tenants/{saved.tenant_id}/apis/{saved.api_id}/lifecycle/publications",
        )
        await self._complete_promotion_for_publication(
            api=saved,
            actor=actor,
            environment=environment,
            gateway_instance_id=gateway.id,
            deployment_id=deployment.id,
        )
        return ApiPortalPublicationOutcome(
            tenant_id=saved.tenant_id,
            api_id=saved.api_id,
            environment=environment,
            gateway_instance_id=gateway.id,
            deployment_id=deployment.id,
            publication_status="published",
            portal_published=saved.portal_published,
            result=result,
            lifecycle_state=await self._state_from_catalog(saved),
        )

    async def promote_to_environment(
        self,
        command: PromoteApiCommand,
        actor: LifecycleActor,
    ) -> ApiPromotionRequestOutcome:
        """Promote a published source deployment by requesting a target GatewayDeployment."""
        source_environment = _normalize_deployment_environment(command.source_environment)
        target_environment = _normalize_deployment_environment(command.target_environment)
        try:
            validate_promotion_chain(source_environment, target_environment)
        except ValueError as exc:
            raise ApiLifecycleValidationError(str(exc)) from exc

        api = await self.repository.get_api_by_id(command.tenant_id, command.api_id)
        if not api:
            raise ApiLifecycleNotFoundError(f"API '{command.api_id}' was not found")

        if api.status != "ready":
            await self._audit_promotion_failure(
                api,
                actor,
                source_environment=source_environment,
                target_environment=target_environment,
                code="transition_invalid",
                message=f"API status '{api.status}' cannot be promoted; validate the draft first",
                status_code=409,
            )
            raise ApiLifecycleTransitionError(f"API status '{api.status}' cannot be promoted; validate the draft first")

        source_gateway = await self._resolve_promotion_gateway(
            command.tenant_id,
            source_environment,
            command.source_gateway_instance_id,
            api,
            actor,
            target_environment=target_environment,
            gateway_role="source",
        )
        target_gateway = await self._resolve_promotion_gateway(
            command.tenant_id,
            target_environment,
            command.target_gateway_instance_id,
            api,
            actor,
            source_environment=source_environment,
            gateway_role="target",
        )

        source_deployment = await self.repository.get_gateway_deployment(api.id, source_gateway.id)
        if not source_deployment:
            await self._audit_promotion_failure(
                api,
                actor,
                source_environment=source_environment,
                target_environment=target_environment,
                code="source_deployment_not_found",
                message=f"No source GatewayDeployment found for gateway '{source_gateway.name}'",
                status_code=404,
                source_gateway_instance_id=source_gateway.id,
                target_gateway_instance_id=target_gateway.id,
            )
            raise ApiLifecycleNotFoundError(f"No source GatewayDeployment found for gateway '{source_gateway.name}'")
        if _wire_value(source_deployment.sync_status) != DeploymentSyncStatus.SYNCED.value:
            await self._audit_promotion_failure(
                api,
                actor,
                source_environment=source_environment,
                target_environment=target_environment,
                code="source_deployment_not_synced",
                message=(
                    f"Source deployment '{source_deployment.id}' is "
                    f"'{_wire_value(source_deployment.sync_status)}', not 'synced'"
                ),
                status_code=409,
                source_gateway_instance_id=source_gateway.id,
                target_gateway_instance_id=target_gateway.id,
                source_deployment_id=source_deployment.id,
            )
            raise ApiLifecycleTransitionError(
                f"Source deployment '{source_deployment.id}' is "
                f"'{_wire_value(source_deployment.sync_status)}', not 'synced'"
            )

        source_publication = _portal_publication_record(api, source_environment, source_gateway.id)
        if (
            not api.portal_published
            or not source_publication
            or source_publication.get("deployment_id") != str(source_deployment.id)
        ):
            await self._audit_promotion_failure(
                api,
                actor,
                source_environment=source_environment,
                target_environment=target_environment,
                code="source_publication_missing",
                message=f"Source environment '{source_environment}' is not published through lifecycle",
                status_code=409,
                source_gateway_instance_id=source_gateway.id,
                target_gateway_instance_id=target_gateway.id,
                source_deployment_id=source_deployment.id,
            )
            raise ApiLifecycleTransitionError(
                f"Source environment '{source_environment}' is not published through lifecycle"
            )

        promotion, promotion_action = await self._upsert_promotion(
            api=api,
            actor=actor,
            source_environment=source_environment,
            target_environment=target_environment,
            source_deployment=source_deployment,
            target_gateway=target_gateway,
            force=command.force,
        )

        desired_state = {
            **GatewayDeploymentService.build_desired_state(api),
            "target_environment": target_environment,
            "target_gateway_name": target_gateway.name,
            "target_source": "api_lifecycle_promotion",
            "promotion_id": str(promotion.id),
            "source_environment": source_environment,
            "source_gateway_instance_id": str(source_gateway.id),
            "source_deployment_id": str(source_deployment.id),
        }
        target_deployment, deployment_action = await self._upsert_gateway_deployment(
            api,
            target_gateway,
            desired_state,
            command.force,
            promotion_id=promotion.id,
        )

        promotion.target_deployment_id = target_deployment.id
        promotion.target_gateway_ids = [str(target_gateway.id)]
        if promotion.status == PromotionStatus.PENDING.value:
            promotion.status = PromotionStatus.PROMOTING.value
        saved_promotion = await self.repository.save_promotion(promotion)

        result = _promotion_result(promotion_action, deployment_action)
        audit_action = (
            "api_lifecycle.promotion_idempotent" if result == "unchanged" else "api_lifecycle.promotion_requested"
        )
        await self.audit_sink.record_transition(
            tenant_id=api.tenant_id,
            actor=actor,
            action=audit_action,
            resource_id=api.api_id,
            resource_name=api.api_name,
            details={
                "api_id": api.api_id,
                "api_name": api.api_name,
                "promotion_id": str(saved_promotion.id),
                "source_environment": source_environment,
                "target_environment": target_environment,
                "source_gateway_instance_id": str(source_gateway.id),
                "target_gateway_instance_id": str(target_gateway.id),
                "source_deployment_id": str(source_deployment.id),
                "target_deployment_id": str(target_deployment.id),
                "promotion_status": saved_promotion.status,
                "deployment_status": _wire_value(target_deployment.sync_status),
                "result": result,
            },
            outcome="success",
            status_code=200,
            path=f"/v1/tenants/{api.tenant_id}/apis/{api.api_id}/lifecycle/promotions",
        )
        return ApiPromotionRequestOutcome(
            tenant_id=api.tenant_id,
            api_id=api.api_id,
            promotion_id=saved_promotion.id,
            source_environment=source_environment,
            target_environment=target_environment,
            source_gateway_instance_id=source_gateway.id,
            target_gateway_instance_id=target_gateway.id,
            target_deployment_id=target_deployment.id,
            promotion_status=saved_promotion.status,
            deployment_status=_wire_value(target_deployment.sync_status),
            result=result,
            lifecycle_state=await self._state_from_catalog(api),
        )

    async def get_lifecycle_state(self, tenant_id: str, api_id: str) -> ApiLifecycleState:
        """Return the aggregate lifecycle state calculated from canonical models."""
        api = await self.repository.get_api_by_id(tenant_id, api_id)
        if not api:
            raise ApiLifecycleNotFoundError(f"API '{api_id}' was not found")
        return await self._state_from_catalog(api)

    async def _state_from_catalog(self, api: APICatalog) -> ApiLifecycleState:
        deployments = await self.repository.list_gateway_deployments(api.id)
        promotions = await self.repository.list_promotions(api.tenant_id, api.api_id)
        deployment_states = [
            GatewayDeploymentState(
                id=item.id,
                environment=item.environment,
                gateway_instance_id=item.gateway_instance_id,
                gateway_name=item.gateway_name,
                gateway_type=item.gateway_type,
                sync_status=item.sync_status,
                desired_generation=item.desired_generation,
                synced_generation=item.synced_generation,
                gateway_resource_id=item.gateway_resource_id,
                public_url=item.public_url,
                sync_error=item.sync_error,
                last_sync_attempt=item.last_sync_attempt,
                last_sync_success=item.last_sync_success,
                policy_sync_status=item.policy_sync_status,
                policy_sync_error=item.policy_sync_error,
                sync_steps=item.sync_steps,
            )
            for item in deployments
        ]
        promotion_states = [
            PromotionState(
                id=item.id,
                source_environment=item.source_environment,
                target_environment=item.target_environment,
                status=item.status,
                message=item.message,
                requested_by=item.requested_by,
                approved_by=item.approved_by,
                completed_at=item.completed_at,
            )
            for item in promotions
        ]

        return ApiLifecycleState(
            catalog_id=api.id,
            tenant_id=api.tenant_id,
            api_id=api.api_id,
            api_name=api.api_name,
            display_name=str(_metadata(api).get("display_name") or api.api_name),
            version=api.version,
            description=str(_metadata(api).get("description") or ""),
            backend_url=str(_metadata(api).get("backend_url") or ""),
            catalog_status=api.status,
            lifecycle_phase=_calculate_lifecycle_phase(
                api.status, api.portal_published, deployment_states, promotion_states
            ),
            portal_published=api.portal_published,
            tags=list(api.tags or []),
            spec=_spec_state(api),
            deployments=deployment_states,
            promotions=promotion_states,
            last_error=_last_error(api.status, deployment_states, promotion_states),
            portal=_portal_state(api),
        )

    @staticmethod
    def _normalize_create_command(command: CreateApiDraftCommand) -> CreateApiDraftCommand:
        name = command.name.strip()
        display_name = command.display_name.strip()
        version = command.version.strip() or "1.0.0"
        backend_url = command.backend_url.strip()
        if not name:
            raise ApiLifecycleValidationError("API name is required")
        if not display_name:
            raise ApiLifecycleValidationError("API display_name is required")
        if not backend_url:
            raise ApiLifecycleValidationError("API backend_url is required")

        return CreateApiDraftCommand(
            tenant_id=command.tenant_id,
            name=name,
            display_name=display_name,
            version=version,
            description=command.description.strip(),
            backend_url=backend_url,
            openapi_spec=command.openapi_spec,
            spec_reference=command.spec_reference.strip() if command.spec_reference else None,
            tags=tuple(tag.strip() for tag in command.tags if tag and tag.strip()),
            owner_team=command.owner_team.strip() if command.owner_team else None,
        )

    async def _resolve_gateway_target(
        self,
        tenant_id: str,
        environment: str,
        gateway_instance_id,
    ) -> GatewayTarget:
        if gateway_instance_id:
            gateway = await self.repository.get_gateway_target(tenant_id, gateway_instance_id)
            if not gateway:
                raise ApiLifecycleGatewayNotFoundError(f"Gateway '{gateway_instance_id}' was not found")
            if not gateway.enabled:
                raise ApiLifecycleGatewayNotFoundError(f"Gateway '{gateway.name}' is disabled")
            if not environment_matches(gateway.environment, environment):
                raise ApiLifecycleValidationError(
                    f"Gateway '{gateway.name}' is in environment '{gateway.environment}', not '{environment}'"
                )
            return gateway

        gateways = await self.repository.list_gateway_targets(tenant_id, environment)
        if not gateways:
            raise ApiLifecycleGatewayNotFoundError(f"No gateway target found for environment '{environment}'")
        if len(gateways) > 1:
            gateway_names = ", ".join(gateway.name for gateway in gateways)
            raise ApiLifecycleGatewayAmbiguousError(
                f"Multiple gateway targets found for environment '{environment}': {gateway_names}. "
                "Provide gateway_instance_id explicitly."
            )
        return gateways[0]

    async def _upsert_gateway_deployment(
        self,
        api: APICatalog,
        gateway: GatewayTarget,
        desired_state: dict,
        force: bool,
        promotion_id: UUID | None = None,
    ) -> tuple[GatewayDeployment, str]:
        now = datetime.now(UTC)
        existing = await self.repository.get_gateway_deployment(api.id, gateway.id)
        if existing:
            if promotion_id and existing.promotion_id != promotion_id:
                existing.promotion_id = promotion_id
                if existing.desired_state == desired_state and not force:
                    saved = await self.repository.save_gateway_deployment(existing)
                    return saved, "unchanged"
            if existing.desired_state == desired_state and not force:
                return existing, "unchanged"

            existing.desired_state = desired_state
            existing.promotion_id = promotion_id or existing.promotion_id
            existing.desired_at = now
            existing.sync_status = DeploymentSyncStatus.PENDING
            existing.sync_error = None
            existing.sync_attempts = 0
            existing.desired_generation = (existing.desired_generation or 0) + 1
            saved = await self.repository.save_gateway_deployment(existing)
            return saved, "updated"

        deployment = GatewayDeployment(
            id=uuid4(),
            api_catalog_id=api.id,
            gateway_instance_id=gateway.id,
            desired_state=desired_state,
            desired_at=now,
            desired_generation=1,
            synced_generation=0,
            attempted_generation=0,
            sync_status=DeploymentSyncStatus.PENDING,
            sync_attempts=0,
            promotion_id=promotion_id,
        )
        created = await self.repository.create_gateway_deployment(deployment)
        return created, "created"

    async def _resolve_promotion_gateway(
        self,
        tenant_id: str,
        environment: str,
        gateway_instance_id,
        api: APICatalog,
        actor: LifecycleActor,
        *,
        gateway_role: str,
        source_environment: str | None = None,
        target_environment: str | None = None,
    ) -> GatewayTarget:
        try:
            return await self._resolve_gateway_target(tenant_id, environment, gateway_instance_id)
        except (
            ApiLifecycleGatewayNotFoundError,
            ApiLifecycleGatewayAmbiguousError,
            ApiLifecycleValidationError,
        ) as exc:
            failure_status = 404 if isinstance(exc, ApiLifecycleGatewayNotFoundError) else 409
            if isinstance(exc, ApiLifecycleValidationError):
                failure_status = 422
            await self._audit_promotion_failure(
                api,
                actor,
                source_environment=source_environment or environment,
                target_environment=target_environment or environment,
                code=f"{gateway_role}_gateway_{exc.__class__.__name__}",
                message=str(exc),
                status_code=failure_status,
            )
            raise

    async def _upsert_promotion(
        self,
        *,
        api: APICatalog,
        actor: LifecycleActor,
        source_environment: str,
        target_environment: str,
        source_deployment: GatewayDeployment,
        target_gateway: GatewayTarget,
        force: bool,
    ) -> tuple[Promotion, str]:
        active = await self.repository.get_active_promotion(
            api.tenant_id,
            api.api_id,
            source_environment,
            target_environment,
        )
        if active and not force:
            return active, "unchanged"

        if not force:
            promoted = await self.repository.get_latest_promoted_promotion(
                api.tenant_id,
                api.api_id,
                source_environment,
                target_environment,
            )
            if promoted:
                return promoted, "unchanged"

        promotion = active if active and force else None
        if promotion:
            promotion.status = PromotionStatus.PROMOTING.value
            promotion.source_deployment_id = source_deployment.id
            promotion.target_gateway_ids = [str(target_gateway.id)]
            promotion.completed_at = None
            saved = await self.repository.save_promotion(promotion)
            return saved, "updated"

        requested_by = actor.email or actor.username or actor.actor_id or "system"
        promotion = Promotion(
            id=uuid4(),
            tenant_id=api.tenant_id,
            api_id=api.api_id,
            source_environment=source_environment,
            target_environment=target_environment,
            source_deployment_id=source_deployment.id,
            target_gateway_ids=[str(target_gateway.id)],
            status=PromotionStatus.PROMOTING.value,
            message=f"Lifecycle promotion {source_environment}->{target_environment}",
            requested_by=requested_by,
            approved_by=requested_by,
        )
        created = await self.repository.create_promotion(promotion)
        return created, "created"

    async def _complete_promotion_for_publication(
        self,
        *,
        api: APICatalog,
        actor: LifecycleActor,
        environment: str,
        gateway_instance_id: UUID,
        deployment_id: UUID,
    ) -> None:
        promotion = await self.repository.get_active_promotion_for_target_deployment(
            api.tenant_id,
            api.api_id,
            environment,
            deployment_id,
        )
        if not promotion:
            return

        promotion.status = PromotionStatus.PROMOTED.value
        promotion.target_deployment_id = deployment_id
        promotion.completed_at = datetime.now(UTC)
        saved = await self.repository.save_promotion(promotion)
        await self.audit_sink.record_transition(
            tenant_id=api.tenant_id,
            actor=actor,
            action="api_lifecycle.promotion_completed",
            resource_id=api.api_id,
            resource_name=api.api_name,
            details={
                "api_id": api.api_id,
                "api_name": api.api_name,
                "promotion_id": str(saved.id),
                "source_environment": saved.source_environment,
                "target_environment": saved.target_environment,
                "target_gateway_instance_id": str(gateway_instance_id),
                "target_deployment_id": str(deployment_id),
                "promotion_status": saved.status,
                "result": "promoted",
            },
            outcome="success",
            status_code=200,
            path=f"/v1/tenants/{api.tenant_id}/apis/{api.api_id}/lifecycle/promotions",
        )

    async def _audit_validation_failure(
        self,
        api: APICatalog,
        actor: LifecycleActor,
        *,
        code: str,
        message: str,
        status_code: int,
    ) -> None:
        await self.audit_sink.record_transition(
            tenant_id=api.tenant_id,
            actor=actor,
            action="api_lifecycle.validate_draft_failed",
            resource_id=api.api_id,
            resource_name=api.api_name,
            details={
                "api_id": api.api_id,
                "api_name": api.api_name,
                "version": api.version,
                "catalog_status": api.status,
                "validation": {
                    "valid": False,
                    "code": code,
                    "message": message,
                },
            },
            outcome="failure",
            status_code=status_code,
            path=f"/v1/tenants/{api.tenant_id}/apis/{api.api_id}/lifecycle/validate",
        )

    async def _audit_deploy_failure(
        self,
        api: APICatalog,
        actor: LifecycleActor,
        *,
        environment: str,
        code: str,
        message: str,
        status_code: int,
    ) -> None:
        await self.audit_sink.record_transition(
            tenant_id=api.tenant_id,
            actor=actor,
            action="api_lifecycle.deploy_failed",
            resource_id=api.api_id,
            resource_name=api.api_name,
            details={
                "api_id": api.api_id,
                "api_name": api.api_name,
                "version": api.version,
                "catalog_status": api.status,
                "environment": environment,
                "deployment": {
                    "valid": False,
                    "code": code,
                    "message": message,
                },
            },
            outcome="failure",
            status_code=status_code,
            path=f"/v1/tenants/{api.tenant_id}/apis/{api.api_id}/lifecycle/deployments",
        )

    async def _resolve_publish_gateway(
        self,
        tenant_id: str,
        environment: str,
        gateway_instance_id,
        api: APICatalog,
        actor: LifecycleActor,
    ) -> GatewayTarget:
        try:
            return await self._resolve_gateway_target(tenant_id, environment, gateway_instance_id)
        except (
            ApiLifecycleGatewayNotFoundError,
            ApiLifecycleGatewayAmbiguousError,
            ApiLifecycleValidationError,
        ) as exc:
            failure_status = 404 if isinstance(exc, ApiLifecycleGatewayNotFoundError) else 409
            if isinstance(exc, ApiLifecycleValidationError):
                failure_status = 422
            await self._audit_publish_failure(
                api,
                actor,
                environment=environment,
                code=exc.__class__.__name__,
                message=str(exc),
                status_code=failure_status,
            )
            raise

    async def _validate_publishable_spec(
        self,
        api: APICatalog,
        actor: LifecycleActor,
        environment: str,
        gateway_instance_id,
        deployment_id,
    ):
        if not api.openapi_spec:
            reference = _spec_state(api).reference
            if reference:
                code = "spec_reference_unresolved"
                message = f"Spec reference cannot be resolved for publication: {reference}"
            else:
                code = "openapi_spec_missing"
                message = "OpenAPI spec is required for portal publication"
            await self._audit_publish_failure(
                api,
                actor,
                environment=environment,
                code=code,
                message=message,
                status_code=422,
                gateway_instance_id=gateway_instance_id,
                deployment_id=deployment_id,
            )
            raise ApiLifecycleSpecValidationError(code, message)

        try:
            return validate_openapi_contract(api.openapi_spec)
        except ApiLifecycleSpecValidationError as exc:
            await self._audit_publish_failure(
                api,
                actor,
                environment=environment,
                code=exc.code,
                message=str(exc),
                status_code=422,
                gateway_instance_id=gateway_instance_id,
                deployment_id=deployment_id,
            )
            raise

    async def _audit_publish_failure(
        self,
        api: APICatalog,
        actor: LifecycleActor,
        *,
        environment: str,
        code: str,
        message: str,
        status_code: int,
        gateway_instance_id=None,
        deployment_id=None,
    ) -> None:
        await self.audit_sink.record_transition(
            tenant_id=api.tenant_id,
            actor=actor,
            action="api_lifecycle.publish_failed",
            resource_id=api.api_id,
            resource_name=api.api_name,
            details={
                "api_id": api.api_id,
                "api_name": api.api_name,
                "version": api.version,
                "catalog_status": api.status,
                "environment": environment,
                "gateway_instance_id": str(gateway_instance_id) if gateway_instance_id else None,
                "deployment_id": str(deployment_id) if deployment_id else None,
                "publication": {
                    "valid": False,
                    "code": code,
                    "message": message,
                },
            },
            outcome="failure",
            status_code=status_code,
            path=f"/v1/tenants/{api.tenant_id}/apis/{api.api_id}/lifecycle/publications",
        )

    async def _audit_promotion_failure(
        self,
        api: APICatalog,
        actor: LifecycleActor,
        *,
        source_environment: str,
        target_environment: str,
        code: str,
        message: str,
        status_code: int,
        source_gateway_instance_id=None,
        target_gateway_instance_id=None,
        source_deployment_id=None,
        target_deployment_id=None,
        promotion_id=None,
    ) -> None:
        await self.audit_sink.record_transition(
            tenant_id=api.tenant_id,
            actor=actor,
            action="api_lifecycle.promotion_failed",
            resource_id=api.api_id,
            resource_name=api.api_name,
            details={
                "api_id": api.api_id,
                "api_name": api.api_name,
                "version": api.version,
                "catalog_status": api.status,
                "promotion_id": str(promotion_id) if promotion_id else None,
                "source_environment": source_environment,
                "target_environment": target_environment,
                "source_gateway_instance_id": (str(source_gateway_instance_id) if source_gateway_instance_id else None),
                "target_gateway_instance_id": (str(target_gateway_instance_id) if target_gateway_instance_id else None),
                "source_deployment_id": str(source_deployment_id) if source_deployment_id else None,
                "target_deployment_id": str(target_deployment_id) if target_deployment_id else None,
                "promotion": {
                    "valid": False,
                    "code": code,
                    "message": message,
                },
            },
            outcome="failure",
            status_code=status_code,
            path=f"/v1/tenants/{api.tenant_id}/apis/{api.api_id}/lifecycle/promotions",
        )


def _slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s-]+", "-", value).strip("-")
    return value or "api"


def _normalize_deployment_environment(value: str) -> str:
    environment = normalize_environment(value)
    if environment not in {"dev", "staging", "production"}:
        raise ApiLifecycleValidationError(f"Invalid deployment environment: {value}")
    return environment


def _wire_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _promotion_result(promotion_action: str, deployment_action: str) -> str:
    if promotion_action == "unchanged" and deployment_action == "unchanged":
        return "unchanged"
    if "created" in {promotion_action, deployment_action}:
        return "requested"
    return "updated"


def _metadata(api: APICatalog) -> dict:
    return api.api_metadata if isinstance(api.api_metadata, dict) else {}


def _metadata_copy(api: APICatalog) -> dict:
    return deepcopy(_metadata(api))


def _spec_fingerprint(spec: object) -> str:
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _spec_state(api: APICatalog) -> ApiSpecState:
    metadata = _metadata(api)
    lifecycle = metadata.get("lifecycle") if isinstance(metadata.get("lifecycle"), dict) else {}
    source = lifecycle.get("spec_source")
    reference = lifecycle.get("spec_reference")
    if api.openapi_spec:
        source = "git" if api.git_path or api.git_commit_sha else source or "inline"
    elif reference:
        source = source or "reference"
    else:
        source = source or "missing"

    return ApiSpecState(
        source=source,
        has_openapi_spec=bool(api.openapi_spec),
        git_path=api.git_path,
        git_commit_sha=api.git_commit_sha,
        reference=reference,
        fallback_reason=lifecycle.get("fallback_reason"),
    )


def _portal_state(api: APICatalog) -> PortalLifecycleState:
    records = _portal_publication_records(api)
    publications: list[PortalPublicationState] = []
    for record in records:
        try:
            publications.append(
                PortalPublicationState(
                    environment=str(record["environment"]),
                    gateway_instance_id=record["gateway_instance_id"],
                    deployment_id=record["deployment_id"],
                    publication_status=str(record["publication_status"]),
                    result=str(record["result"]),
                    spec_hash=str(record["spec_hash"]),
                    published_at=record["published_at"],
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    publications.sort(key=lambda item: item.published_at, reverse=True)
    last = publications[0] if publications else None
    return PortalLifecycleState(
        published=bool(api.portal_published),
        status="published" if api.portal_published else "not_published",
        publications=publications,
        last_result=last.result if last else None,
        last_environment=last.environment if last else None,
        last_gateway_instance_id=last.gateway_instance_id if last else None,
        last_deployment_id=last.deployment_id if last else None,
        last_published_at=last.published_at if last else None,
    )


def _portal_publication_record(api: APICatalog, environment: str, gateway_instance_id) -> dict | None:
    metadata = _metadata(api)
    lifecycle = metadata.get("lifecycle") if isinstance(metadata.get("lifecycle"), dict) else {}
    publications = (
        lifecycle.get("portal_publications") if isinstance(lifecycle.get("portal_publications"), dict) else {}
    )
    key = f"{environment}:{gateway_instance_id}"
    record = publications.get(key)
    return record if isinstance(record, dict) else None


def _portal_publication_records(api: APICatalog) -> list[dict]:
    metadata = _metadata(api)
    lifecycle = metadata.get("lifecycle") if isinstance(metadata.get("lifecycle"), dict) else {}
    publications = (
        lifecycle.get("portal_publications") if isinstance(lifecycle.get("portal_publications"), dict) else {}
    )
    records: list[dict] = []
    for raw in publications.values():
        if not isinstance(raw, dict):
            continue
        parsed = dict(raw)
        try:
            from uuid import UUID

            parsed["gateway_instance_id"] = UUID(str(parsed["gateway_instance_id"]))
            parsed["deployment_id"] = UUID(str(parsed["deployment_id"]))
            parsed["published_at"] = datetime.fromisoformat(str(parsed["published_at"]))
        except (KeyError, TypeError, ValueError):
            continue
        records.append(parsed)
    return records


def _calculate_lifecycle_phase(
    catalog_status: str,
    portal_published: bool,
    deployments: list[GatewayDeploymentState],
    promotions: list[PromotionState],
) -> str:
    if catalog_status in {"archived", "failed"}:
        return catalog_status
    if any(deployment.sync_status == "error" for deployment in deployments):
        return "failed"
    if any(promotion.status == "failed" for promotion in promotions):
        return "failed"
    if any(promotion.status in {"pending", "promoting"} for promotion in promotions):
        return "promoting"
    if any(promotion.status == "promoted" for promotion in promotions):
        return "promoted"
    if portal_published:
        return "published"
    if any(deployment.sync_status == "synced" for deployment in deployments):
        return "deployed"
    return catalog_status


def _last_error(
    catalog_status: str,
    deployments: list[GatewayDeploymentState],
    promotions: list[PromotionState],
) -> str | None:
    if catalog_status == "failed":
        return "catalog validation failed"
    for deployment in deployments:
        if deployment.sync_status == "error" and deployment.sync_error:
            return deployment.sync_error
    for promotion in promotions:
        if promotion.status == "failed":
            return promotion.message
    return None
