"""Tests for gateway policies — CRUD, bindings, and policy sync in sync engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.adapters.gateway_adapter_interface import AdapterResult
from src.models.gateway_deployment import DeploymentSyncStatus
from src.models.gateway_instance import GatewayInstanceStatus
from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding, PolicyType, PolicyScope


class TestGatewayPolicyModels:
    """Tests for gateway policy model creation and validation."""

    def test_create_policy(self):
        """Policy created with correct fields."""
        policy = GatewayPolicy(
            name="rate-limit-100",
            description="100 req/min",
            policy_type=PolicyType.RATE_LIMIT,
            tenant_id="acme",
            scope=PolicyScope.API,
            config={"rate": 100, "window": "1m"},
            priority=50,
            enabled=True,
        )
        assert policy.name == "rate-limit-100"
        assert policy.policy_type == PolicyType.RATE_LIMIT
        assert policy.scope == PolicyScope.API
        assert policy.config["rate"] == 100
        assert policy.priority == 50

    def test_policy_types_enum(self):
        """All expected policy types are available."""
        assert PolicyType.CORS.value == "cors"
        assert PolicyType.RATE_LIMIT.value == "rate_limit"
        assert PolicyType.JWT_VALIDATION.value == "jwt_validation"
        assert PolicyType.IP_FILTER.value == "ip_filter"
        assert PolicyType.LOGGING.value == "logging"
        assert PolicyType.CACHING.value == "caching"
        assert PolicyType.TRANSFORM.value == "transform"

    def test_policy_scopes_enum(self):
        """All expected policy scopes are available."""
        assert PolicyScope.API.value == "api"
        assert PolicyScope.GATEWAY.value == "gateway"
        assert PolicyScope.TENANT.value == "tenant"

    def test_create_binding(self):
        """Binding created with correct foreign key references."""
        policy_id = uuid4()
        api_id = uuid4()
        gw_id = uuid4()
        binding = GatewayPolicyBinding(
            policy_id=policy_id,
            api_catalog_id=api_id,
            gateway_instance_id=gw_id,
            tenant_id="acme",
            enabled=True,
        )
        assert binding.policy_id == policy_id
        assert binding.api_catalog_id == api_id
        assert binding.gateway_instance_id == gw_id


class TestGatewayPolicyRepository:
    """Tests for policy repository operations (mocked DB session)."""

    def _make_policy(self, **overrides):
        defaults = {
            "id": uuid4(),
            "name": "cors-permissive",
            "description": "Allow all origins",
            "policy_type": PolicyType.CORS,
            "tenant_id": "acme",
            "scope": PolicyScope.API,
            "config": {"allow_origins": ["*"]},
            "priority": 100,
            "enabled": True,
            "bindings": [],
        }
        defaults.update(overrides)
        mock = MagicMock(spec=GatewayPolicy)
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_binding(self, **overrides):
        defaults = {
            "id": uuid4(),
            "policy_id": uuid4(),
            "api_catalog_id": uuid4(),
            "gateway_instance_id": uuid4(),
            "tenant_id": "acme",
            "enabled": True,
        }
        defaults.update(overrides)
        mock = MagicMock(spec=GatewayPolicyBinding)
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_list_policies_by_tenant(self):
        """list_all filters by tenant_id and includes platform-wide policies."""
        from src.repositories.gateway_policy import GatewayPolicyRepository

        tenant_policy = self._make_policy(tenant_id="acme")
        platform_policy = self._make_policy(tenant_id=None, name="global-cors")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tenant_policy, platform_policy]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = GatewayPolicyRepository(mock_session)
        result = await repo.list_all(tenant_id="acme")

        assert len(result) == 2
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_policy_cascades_bindings(self):
        """Deleting a policy cascades to its bindings via relationship."""
        from src.repositories.gateway_policy import GatewayPolicyRepository

        binding = self._make_binding()
        policy = self._make_policy(bindings=[binding])

        mock_session = AsyncMock()
        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()

        repo = GatewayPolicyRepository(mock_session)
        await repo.delete(policy)

        mock_session.delete.assert_awaited_once_with(policy)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_policies_for_deployment(self):
        """Resolves API + gateway + tenant scoped policies."""
        from src.repositories.gateway_policy import GatewayPolicyRepository

        api_policy = self._make_policy(name="api-cors", scope=PolicyScope.API)
        gw_policy = self._make_policy(name="gw-logging", scope=PolicyScope.GATEWAY)
        tenant_policy = self._make_policy(name="tenant-rate", scope=PolicyScope.TENANT)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [api_policy, gw_policy, tenant_policy]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = GatewayPolicyRepository(mock_session)
        result = await repo.get_policies_for_deployment(
            api_catalog_id=uuid4(),
            gateway_instance_id=uuid4(),
            tenant_id="acme",
        )

        assert len(result) == 3
        mock_session.execute.assert_awaited_once()


class TestGatewayPolicyBindingRepository:
    """Tests for policy binding repository operations."""

    @pytest.mark.asyncio
    async def test_create_binding_api_scope(self):
        """Binding with api_catalog_id + gateway_instance_id created."""
        from src.repositories.gateway_policy import GatewayPolicyBindingRepository

        binding = GatewayPolicyBinding(
            policy_id=uuid4(),
            api_catalog_id=uuid4(),
            gateway_instance_id=uuid4(),
            tenant_id="acme",
        )

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        repo = GatewayPolicyBindingRepository(mock_session)
        result = await repo.create(binding)

        mock_session.add.assert_called_once_with(binding)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_binding_gateway_scope(self):
        """Binding with gateway_instance_id only (no api) created."""
        from src.repositories.gateway_policy import GatewayPolicyBindingRepository

        binding = GatewayPolicyBinding(
            policy_id=uuid4(),
            api_catalog_id=None,
            gateway_instance_id=uuid4(),
            tenant_id=None,
        )

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        repo = GatewayPolicyBindingRepository(mock_session)
        result = await repo.create(binding)

        mock_session.add.assert_called_once_with(binding)
        assert binding.api_catalog_id is None

    @pytest.mark.asyncio
    async def test_delete_binding(self):
        """Binding removed, policy unchanged."""
        from src.repositories.gateway_policy import GatewayPolicyBindingRepository

        binding = MagicMock(spec=GatewayPolicyBinding)

        mock_session = AsyncMock()
        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()

        repo = GatewayPolicyBindingRepository(mock_session)
        await repo.delete(binding)

        mock_session.delete.assert_awaited_once_with(binding)


class TestPolicySyncInSyncEngine:
    """Tests for policy sync within sync engine _handle_sync."""

    def _make_deployment(self, **overrides):
        defaults = {
            "id": uuid4(),
            "api_catalog_id": uuid4(),
            "gateway_instance_id": uuid4(),
            "desired_state": {"spec_hash": "abc123", "tenant_id": "acme", "api_name": "Test"},
            "actual_state": None,
            "sync_status": DeploymentSyncStatus.PENDING,
            "sync_attempts": 0,
            "sync_error": None,
            "gateway_resource_id": None,
            "last_sync_attempt": None,
            "last_sync_success": None,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_gateway(self, **overrides):
        defaults = {
            "id": uuid4(),
            "name": "webmethods-prod",
            "gateway_type": MagicMock(value="webmethods"),
            "base_url": "https://gw.example.com",
            "auth_config": {},
            "status": GatewayInstanceStatus.ONLINE,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_policy(self, **overrides):
        defaults = {
            "id": uuid4(),
            "name": "rate-limit-100",
            "policy_type": MagicMock(value="rate_limit"),
            "config": {"rate": 100},
            "priority": 50,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_policy_sync_in_handle_sync(self):
        """After sync_api success, upsert_policy called for each bound policy."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        policy1 = self._make_policy(name="cors-policy")
        policy2 = self._make_policy(name="rate-limit-policy")

        adapter = MagicMock()
        adapter.connect = AsyncMock()
        adapter.disconnect = AsyncMock()
        adapter.sync_api = AsyncMock(
            return_value=AdapterResult(success=True, resource_id="gw-api-1", data={"spec_hash": "abc123"})
        )
        adapter.upsert_policy = AsyncMock(return_value=AdapterResult(success=True))

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_policy_repo = MagicMock()
        mock_policy_repo.get_policies_for_deployment = AsyncMock(return_value=[policy1, policy2])

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry, \
             patch("src.repositories.gateway_policy.GatewayPolicyRepository", return_value=mock_policy_repo):

            mock_registry.create.return_value = adapter

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

            # API synced successfully
            assert deployment.sync_status == DeploymentSyncStatus.SYNCED
            # upsert_policy called for each bound policy
            assert adapter.upsert_policy.await_count == 2

    @pytest.mark.asyncio
    async def test_policy_sync_failure_non_fatal(self):
        """upsert_policy failure doesn't change deployment status from SYNCED."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        policy1 = self._make_policy(name="failing-policy")

        adapter = MagicMock()
        adapter.connect = AsyncMock()
        adapter.disconnect = AsyncMock()
        adapter.sync_api = AsyncMock(
            return_value=AdapterResult(success=True, resource_id="gw-api-1", data={"spec_hash": "abc123"})
        )
        # upsert_policy raises an exception
        adapter.upsert_policy = AsyncMock(side_effect=RuntimeError("Policy apply failed"))

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_policy_repo = MagicMock()
        mock_policy_repo.get_policies_for_deployment = AsyncMock(return_value=[policy1])

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry, \
             patch("src.repositories.gateway_policy.GatewayPolicyRepository", return_value=mock_policy_repo):

            mock_registry.create.return_value = adapter

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

            # Deployment is still SYNCED even though policy failed
            assert deployment.sync_status == DeploymentSyncStatus.SYNCED
            assert deployment.sync_error is None
