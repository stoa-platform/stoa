"""Lifecycle production deploys/promotions need a Git-backed desired state (ADF-G2).

Refusal must happen before any Promotion or GatewayDeployment write and be audited.
"""

# regression for CAB-1917

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.promotion import Promotion, PromotionStatus
from src.services.api_lifecycle.errors import ApiLifecycleTransitionError
from src.services.api_lifecycle.ports import DeployApiCommand, PublishApiCommand
from src.services.api_lifecycle.service import ApiLifecycleService
from tests.test_api_lifecycle_promotion import (
    InMemoryApiLifecycleRepository,
    _actor,
    _api,
    _gateway,
    _promote_command,
    _service,
)

PRODUCTION_GUARD_CODE = "production_requires_git_backed_desired_state"
GIT_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"


def _git_backed_api() -> APICatalog:
    api = _api()
    api.git_commit_sha = GIT_COMMIT_SHA
    api.git_path = "tenants/acme/apis/payments-api"
    return api


def _deploy_command(environment: str, **overrides) -> DeployApiCommand:
    values = {"tenant_id": "acme", "api_id": "payments-api", "environment": environment}
    values.update(overrides)
    return DeployApiCommand(**values)


async def _deploy_sync_publish(
    service: ApiLifecycleService,
    repository: InMemoryApiLifecycleRepository,
    *,
    environment: str,
) -> GatewayDeployment:
    await service.deploy_to_environment(_deploy_command(environment), _actor())
    deployment = next(
        deployment
        for (_api_catalog_id, gateway_id), deployment in repository.deployments.items()
        if repository.gateways[gateway_id].environment == environment
    )
    deployment.sync_status = DeploymentSyncStatus.SYNCED
    deployment.synced_generation = deployment.desired_generation
    deployment.last_sync_success = datetime.now(UTC)
    await service.publish_to_portal(
        PublishApiCommand(tenant_id="acme", api_id="payments-api", environment=environment),
        _actor(),
    )
    return deployment


@pytest.mark.asyncio
@pytest.mark.parametrize("gateway_environment", ["production", "prod"])
async def test_regression_lifecycle_deploy_to_production_without_git_commit_is_refused(
    gateway_environment: str,
) -> None:
    gateway = _gateway(environment=gateway_environment, name="stoa-prod")
    service, repository, audit, _ = _service(api=_api(), gateways=[gateway])

    with pytest.raises(ApiLifecycleTransitionError, match="Git-backed"):
        await service.deploy_to_environment(
            _deploy_command("production", gateway_instance_id=gateway.id),
            _actor(),
        )

    assert repository.deployments == {}
    assert [event["action"] for event in audit.events] == ["api_lifecycle.deploy_failed"]
    failure = audit.events[0]
    assert failure["outcome"] == "failure"
    assert failure["status_code"] == 409
    assert failure["details"]["environment"] == "production"
    assert failure["details"]["deployment"]["code"] == PRODUCTION_GUARD_CODE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "git_backed", "desired_source", "desired_commit_sha"),
    [
        ("dev", False, "db_shortcut", None),
        ("staging", False, "db_shortcut", None),
        ("production", True, "git", GIT_COMMIT_SHA),
    ],
)
async def test_regression_lifecycle_deploy_accepted_targets_keep_their_provenance(
    environment: str, git_backed: bool, desired_source: str, desired_commit_sha: str | None
) -> None:
    gateway = _gateway(environment=environment, name=f"stoa-{environment}")
    api = _git_backed_api() if git_backed else _api()
    service, repository, audit, _ = _service(api=api, gateways=[gateway])

    outcome = await service.deploy_to_environment(_deploy_command(environment), _actor())

    deployment = repository.deployments[(api.id, gateway.id)]
    assert outcome.action == "created"
    assert deployment.desired_state["desired_source"] == desired_source
    assert deployment.desired_state["desired_commit_sha"] == desired_commit_sha
    assert audit.events[-1]["action"] == "api_lifecycle.deploy_requested"


@pytest.mark.asyncio
async def test_regression_lifecycle_promotion_to_production_without_git_commit_writes_nothing() -> None:
    staging = _gateway(environment="staging", name="stoa-staging")
    production = _gateway(environment="production", name="stoa-prod")
    api = _api()
    service, repository, audit, _ = _service(api=api, gateways=[staging, production])
    await _deploy_sync_publish(service, repository, environment="staging")
    events_before = len(audit.events)

    with pytest.raises(ApiLifecycleTransitionError, match="Git-backed"):
        await service.promote_to_environment(
            _promote_command(source_environment="staging", target_environment="production"),
            _actor(),
        )

    assert repository.promotions == {}
    assert (api.id, production.id) not in repository.deployments
    new_events = audit.events[events_before:]
    assert [event["action"] for event in new_events] == ["api_lifecycle.promotion_failed"]
    failure = new_events[0]
    assert failure["outcome"] == "failure"
    assert failure["status_code"] == 409
    assert failure["details"]["source_environment"] == "staging"
    assert failure["details"]["target_environment"] == "production"
    assert failure["details"]["target_gateway_instance_id"] == str(production.id)
    assert failure["details"]["promotion_id"] is None
    assert failure["details"]["promotion"]["code"] == PRODUCTION_GUARD_CODE
    state = await service.get_lifecycle_state("acme", "payments-api")
    assert state.promotions == []
    assert state.lifecycle_phase != "promoting"


@pytest.mark.asyncio
async def test_regression_lifecycle_forced_production_promotion_does_not_mutate_active_promotion() -> None:
    staging = _gateway(environment="staging", name="stoa-staging")
    production = _gateway(environment="production", name="stoa-prod")
    api = _api()
    service, repository, _, _ = _service(api=api, gateways=[staging, production])
    await _deploy_sync_publish(service, repository, environment="staging")
    # An active row left behind by an earlier refused request must not be revived by force=true.
    stale = Promotion(
        id=uuid4(),
        tenant_id="acme",
        api_id="payments-api",
        source_environment="staging",
        target_environment="production",
        source_deployment_id=None,
        target_gateway_ids=[],
        status=PromotionStatus.PENDING.value,
        message="stale lifecycle promotion",
        requested_by="owner@acme.test",
        approved_by="owner@acme.test",
    )
    repository.promotions[stale.id] = stale

    with pytest.raises(ApiLifecycleTransitionError, match="Git-backed"):
        await service.promote_to_environment(
            _promote_command(source_environment="staging", target_environment="production", force=True),
            _actor(),
        )

    assert repository.promotions == {stale.id: stale}
    assert stale.status == PromotionStatus.PENDING.value
    assert stale.source_deployment_id is None
    assert stale.target_gateway_ids == []
    assert (api.id, production.id) not in repository.deployments


@pytest.mark.asyncio
async def test_regression_lifecycle_promotion_to_production_with_git_commit_is_git_backed() -> None:
    staging = _gateway(environment="staging", name="stoa-staging")
    production = _gateway(environment="production", name="stoa-prod")
    api = _git_backed_api()
    service, repository, _, _ = _service(api=api, gateways=[staging, production])
    await _deploy_sync_publish(service, repository, environment="staging")

    outcome = await service.promote_to_environment(
        _promote_command(source_environment="staging", target_environment="production"),
        _actor(),
    )

    target = repository.deployments[(api.id, production.id)]
    assert outcome.result == "requested"
    assert outcome.promotion_status == PromotionStatus.PROMOTING.value
    assert target.promotion_id == outcome.promotion_id
    assert target.desired_state["desired_source"] == "git"
    assert target.desired_state["desired_commit_sha"] == GIT_COMMIT_SHA


@pytest.mark.parametrize("client_fixture", ["client_as_tenant_admin", "client_as_cpi_admin"])
def test_regression_lifecycle_production_deploy_without_git_commit_returns_409_for_every_role(
    client_fixture: str,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.routers.api_lifecycle as router_module

    gateway = _gateway(environment="production", name="stoa-prod")
    service, repository, audit, _ = _service(api=_api(), gateways=[gateway])
    monkeypatch.setattr(router_module, "_build_service", lambda _db: service)
    client = request.getfixturevalue(client_fixture)

    response = client.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/deployments",
        json={"environment": "production"},
    )

    assert response.status_code == 409
    assert "Git-backed" in response.json()["detail"]
    assert repository.deployments == {}
    assert audit.events[-1]["action"] == "api_lifecycle.deploy_failed"
    assert audit.events[-1]["details"]["deployment"]["code"] == PRODUCTION_GUARD_CODE
