"""Tenant provisioning: reuse of an existing Keycloak tenant group (CAB-2079)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from keycloak.exceptions import KeycloakGetError, KeycloakPostError

from src.models.tenant import TenantProvisioningStatus
from src.services.keycloak_service import KeycloakService

TENANT = "candidate-a"
GROUP = {"id": "grp-1", "name": TENANT, "path": f"/{TENANT}", "attributes": {"display_name": ["A"]}}


def _svc(admin):
    s = KeycloakService()
    s._admin = admin
    return s


def _tenant():
    t = MagicMock()
    t.id = TENANT
    t.provisioning_attempts = 0
    t.kc_group_id = None
    return t


async def _gen(value):
    yield value


async def _provision(svc, tenant):
    db = AsyncMock()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=tenant)
    from src.services import tenant_provisioning_service as tps

    with (
        patch.object(tps, "get_db", return_value=_gen(db)),
        patch.object(tps, "TenantRepository", return_value=repo),
        patch.object(tps, "keycloak_service", svc),
        patch.object(tps, "kafka_service") as kafka,
        patch.object(tps, "_seed_default_rate_limit_policy", new_callable=AsyncMock),
        patch.object(tps.asyncio, "sleep", new_callable=AsyncMock) as sleep,
    ):
        kafka.publish = AsyncMock()
        await tps.provision_tenant(TENANT, "a@example.invalid", "A", "corr-1")
    return sleep


def _existing_admin():
    admin = MagicMock()
    admin.get_group_by_path.return_value = dict(GROUP)
    admin.create_user.return_value = "user-1"
    admin.get_realm_role.return_value = {"name": "tenant-admin"}
    return admin


@pytest.mark.asyncio
async def test_existing_group_is_reused():
    admin = _existing_admin()
    tenant = _tenant()
    await _provision(_svc(admin), tenant)
    admin.create_group.assert_not_called()
    assert tenant.kc_group_id == "grp-1"
    assert tenant.provisioning_status == TenantProvisioningStatus.READY.value
    upd = admin.update_group.call_args[0]
    assert upd[0] == "grp-1"
    assert upd[1]["attributes"] == {"display_name": ["A"], "stoa_tenant_id": [TENANT]}


@pytest.mark.asyncio
async def test_create_409_triggers_lookup_without_second_create():
    admin = MagicMock()
    admin.get_group_by_path.side_effect = [
        KeycloakGetError(error_message="not found", response_code=404),
        dict(GROUP),
    ]
    admin.create_group.side_effect = KeycloakPostError(error_message="exists", response_code=409)
    gid = await _svc(admin).setup_tenant_group(TENANT, "A")
    assert gid == "grp-1"
    assert admin.create_group.call_count == 1
    assert admin.get_group_by_path.call_count == 2


@pytest.mark.asyncio
async def test_new_group_gets_marker():
    admin = MagicMock()
    admin.get_group_by_path.side_effect = KeycloakGetError(error_message="nf", response_code=404)
    admin.create_group.return_value = "grp-new"
    assert await _svc(admin).setup_tenant_group(TENANT, "A") == "grp-new"
    assert admin.create_group.call_args[0][0]["attributes"]["stoa_tenant_id"] == [TENANT]


@pytest.mark.asyncio
async def test_403_not_retried_and_tenant_failed():
    admin = MagicMock()
    admin.get_group_by_path.side_effect = KeycloakGetError(error_message="nf", response_code=404)
    admin.create_group.side_effect = KeycloakPostError(error_message="forbidden", response_code=403)
    tenant = _tenant()
    sleep = await _provision(_svc(admin), tenant)
    sleep.assert_not_called()
    assert admin.create_group.call_count == 1
    assert tenant.provisioning_status == TenantProvisioningStatus.FAILED.value
    assert tenant.provisioning_error.startswith("KC group creation failed:")


@pytest.mark.asyncio
async def test_two_provisions_ready_same_group_id():
    admin = MagicMock()
    created = {}

    def create_group(data):
        created["g"] = {
            "id": "grp-1",
            "name": data["name"],
            "path": f"/{data['name']}",
            "attributes": data["attributes"],
        }
        return "grp-1"

    def by_path(path):
        if "g" in created:
            return created["g"]
        raise KeycloakGetError(error_message="nf", response_code=404)

    admin.create_group.side_effect = create_group
    admin.get_group_by_path.side_effect = by_path
    admin.create_user.return_value = "user-1"
    svc = _svc(admin)
    t1, t2 = _tenant(), _tenant()
    await _provision(svc, t1)
    await _provision(svc, t2)
    assert t1.provisioning_status == t2.provisioning_status == TenantProvisioningStatus.READY.value
    assert t1.kc_group_id == t2.kc_group_id == "grp-1"
    assert admin.create_group.call_count == 1


@pytest.mark.asyncio
async def test_foreign_marker_blocks_adoption():
    admin = MagicMock()
    admin.get_group_by_path.return_value = {**GROUP, "attributes": {"stoa_tenant_id": ["other"]}}
    with pytest.raises(ValueError):
        await _svc(admin).setup_tenant_group(TENANT, "A")
    admin.update_group.assert_not_called()
    admin.create_group.assert_not_called()


@pytest.mark.asyncio
async def test_existing_admin_user_409_joined_by_id_to_adopted_group():
    admin = _existing_admin()
    admin.create_user.side_effect = KeycloakPostError(error_message="exists", response_code=409)
    admin.get_user_id.return_value = "user-42"
    tenant = _tenant()
    await _provision(_svc(admin), tenant)
    admin.get_user_id.assert_called_once_with(f"admin-{TENANT}")
    admin.group_user_add.assert_called_once_with("user-42", "grp-1")
    admin.get_groups.assert_not_called()
    assert tenant.kc_group_id == "grp-1"
    assert tenant.provisioning_status == TenantProvisioningStatus.READY.value


@pytest.mark.asyncio
async def test_new_admin_user_joined_by_returned_id():
    admin = _existing_admin()
    tenant = _tenant()
    await _provision(_svc(admin), tenant)
    admin.group_user_add.assert_called_once_with("user-1", "grp-1")
