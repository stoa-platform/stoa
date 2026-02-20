"""Tests for Kafka service — event creation, publish, convenience methods."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.kafka_service import (
    EVENT_SOURCE,
    EVENT_VERSION,
    KafkaService,
    QuotaTier,
    Topics,
)


@pytest.fixture
def kafka_svc():
    return KafkaService()


class TestTopics:
    """Verify all topics follow stoa.X.Y naming convention."""

    def test_api_events_topic(self):
        assert Topics.API_EVENTS == "stoa.api.lifecycle"

    def test_deploy_requests_topic(self):
        assert Topics.DEPLOY_REQUESTS == "stoa.deploy.requests"

    def test_deploy_results_topic(self):
        assert Topics.DEPLOY_RESULTS == "stoa.deploy.results"

    def test_app_events_topic(self):
        assert Topics.APP_EVENTS == "stoa.app.lifecycle"

    def test_tenant_events_topic(self):
        assert Topics.TENANT_EVENTS == "stoa.tenant.lifecycle"

    def test_audit_log_topic(self):
        assert Topics.AUDIT_LOG == "stoa.audit.trail"

    def test_mcp_server_events_topic(self):
        assert Topics.MCP_SERVER_EVENTS == "stoa.mcp.servers"

    def test_mcp_sync_requests_topic(self):
        assert Topics.MCP_SYNC_REQUESTS == "stoa.mcp.sync.requests"

    def test_mcp_sync_results_topic(self):
        assert Topics.MCP_SYNC_RESULTS == "stoa.mcp.sync.results"

    def test_gateway_sync_requests_topic(self):
        assert Topics.GATEWAY_SYNC_REQUESTS == "stoa.gateway.sync.requests"

    def test_gateway_sync_results_topic(self):
        assert Topics.GATEWAY_SYNC_RESULTS == "stoa.gateway.sync.results"

    def test_gateway_events_topic(self):
        assert Topics.GATEWAY_EVENTS == "stoa.gateway.events"

    def test_security_alerts_topic(self):
        assert Topics.SECURITY_ALERTS == "stoa.security.alerts"

    def test_gateway_metrics_topic(self):
        assert Topics.GATEWAY_METRICS == "stoa.gateway.metrics"

    def test_deployment_events_topic(self):
        assert Topics.DEPLOYMENT_EVENTS == "stoa.deployment.events"

    def test_resource_lifecycle_topic(self):
        assert Topics.RESOURCE_LIFECYCLE == "stoa.resource.lifecycle"

    def test_metering_events_topic(self):
        assert Topics.METERING_EVENTS == "stoa.metering.events"

    def test_all_topics_use_stoa_prefix(self):
        """Every topic constant must start with 'stoa.'."""
        for attr in dir(Topics):
            if attr.isupper() and not attr.startswith("_"):
                value = getattr(Topics, attr)
                assert value.startswith("stoa."), f"{attr} = {value!r} missing stoa. prefix"


class TestCreateEvent:
    def test_event_structure(self, kafka_svc):
        event = kafka_svc._create_event(
            event_type="api-created",
            tenant_id="acme",
            payload={"name": "test-api"},
            user_id="user-1",
        )
        assert event["type"] == "api-created"
        assert event["tenant_id"] == "acme"
        assert event["user_id"] == "user-1"
        assert event["payload"] == {"name": "test-api"}
        assert "id" in event
        assert "timestamp" in event

    def test_event_has_uuid(self, kafka_svc):
        e1 = kafka_svc._create_event("t", "acme", {})
        e2 = kafka_svc._create_event("t", "acme", {})
        assert e1["id"] != e2["id"]

    def test_event_timestamp_format(self, kafka_svc):
        event = kafka_svc._create_event("t", "acme", {})
        assert event["timestamp"].endswith("Z")

    def test_canonical_envelope_has_source(self, kafka_svc):
        event = kafka_svc._create_event("t", "acme", {})
        assert event["source"] == EVENT_SOURCE

    def test_canonical_envelope_has_version(self, kafka_svc):
        event = kafka_svc._create_event("t", "acme", {})
        assert event["version"] == EVENT_VERSION

    def test_canonical_envelope_fields(self, kafka_svc):
        """Verify all 7 canonical fields are present in the envelope."""
        event = kafka_svc._create_event("test-type", "acme", {"k": "v"}, "user-1")
        required_fields = {"id", "type", "source", "tenant_id", "timestamp", "version", "payload"}
        assert required_fields.issubset(event.keys())


class TestPublish:
    @patch("src.services.kafka_service.settings")
    async def test_publish_disabled_returns_uuid(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.publish("topic", "type", "acme", {})
        assert isinstance(event_id, str)
        assert len(event_id) == 36  # UUID format

    @patch("src.services.kafka_service.settings")
    async def test_publish_no_producer_raises(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        kafka_svc._producer = None
        with pytest.raises(RuntimeError, match="not initialized"):
            await kafka_svc.publish("topic", "type", "acme", {})

    @patch("src.services.kafka_service.settings")
    async def test_publish_happy_path(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        mock_producer = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = None
        mock_producer.send.return_value = mock_future
        kafka_svc._producer = mock_producer

        event_id = await kafka_svc.publish(
            topic="stoa.api.lifecycle",
            event_type="api-created",
            tenant_id="acme",
            payload={"name": "test"},
            user_id="user-1",
        )

        assert isinstance(event_id, str)
        mock_producer.send.assert_called_once()
        call_kwargs = mock_producer.send.call_args
        assert call_kwargs[1]["key"] == "acme"  # default partition key

    @patch("src.services.kafka_service.get_masker")
    @patch("src.services.kafka_service.settings")
    async def test_publish_masks_pii_in_payload(self, mock_settings, mock_get_masker, kafka_svc):
        """PII masking is applied to payload before serialization."""
        mock_settings.KAFKA_ENABLED = True
        mock_producer = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = None
        mock_producer.send.return_value = mock_future
        kafka_svc._producer = mock_producer

        mock_masker = MagicMock()
        mock_masker.mask_dict.return_value = {"email": "[MASKED]"}
        mock_get_masker.return_value = mock_masker

        await kafka_svc.publish(
            topic="stoa.api.lifecycle",
            event_type="api-created",
            tenant_id="acme",
            payload={"email": "test@example.com"},
        )

        mock_masker.mask_dict.assert_called_once()
        sent_event = mock_producer.send.call_args[1]["value"]
        assert sent_event["payload"] == {"email": "[MASKED]"}


class TestConvenienceMethods:
    @patch("src.services.kafka_service.settings")
    async def test_emit_api_created(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.emit_api_created("acme", {"name": "test"}, "user-1")
        assert isinstance(event_id, str)

    @patch("src.services.kafka_service.settings")
    async def test_emit_api_deleted(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.emit_api_deleted("acme", "api-123", "user-1")
        assert isinstance(event_id, str)

    @patch("src.services.kafka_service.settings")
    async def test_emit_audit_event(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.emit_audit_event(
            tenant_id="acme",
            action="create",
            resource_type="api",
            resource_id="api-1",
            user_id="user-1",
        )
        assert isinstance(event_id, str)

    @patch("src.services.kafka_service.settings")
    async def test_emit_security_alert(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.emit_security_alert(
            tenant_id="acme",
            event_type="auth_failure",
            severity="high",
            details={"ip": "1.2.3.4", "reason": "invalid_token"},
        )
        assert isinstance(event_id, str)

    @patch("src.services.kafka_service.settings")
    async def test_emit_subscription_event(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        event_id = await kafka_svc.emit_subscription_event(
            tenant_id="acme",
            subscription_data={"api_id": "api-1", "status": "active"},
            user_id="user-1",
        )
        assert isinstance(event_id, str)


class TestQuotaTiers:
    """Verify quota tier constants are correctly defined."""

    def test_standard_tier_producer_rate(self):
        assert QuotaTier.STANDARD["producer_byte_rate"] == 10 * 1024 * 1024  # 10 MB/s

    def test_standard_tier_consumer_rate(self):
        assert QuotaTier.STANDARD["consumer_byte_rate"] == 20 * 1024 * 1024  # 20 MB/s

    def test_standard_tier_request_percentage(self):
        assert QuotaTier.STANDARD["request_percentage"] == 25.0  # 25%

    def test_premium_tier_producer_rate(self):
        assert QuotaTier.PREMIUM["producer_byte_rate"] == 50 * 1024 * 1024  # 50 MB/s

    def test_premium_tier_consumer_rate(self):
        assert QuotaTier.PREMIUM["consumer_byte_rate"] == 100 * 1024 * 1024  # 100 MB/s

    def test_premium_tier_request_percentage(self):
        assert QuotaTier.PREMIUM["request_percentage"] == 50.0  # 50%


class TestConfigureTenantQuota:
    """Tests for Kafka tenant quota configuration."""

    @patch("src.services.kafka_service.settings")
    def test_configure_quota_disabled_returns_true(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        result = kafka_svc.configure_tenant_quota("acme", "standard")
        assert result is True

    @patch("src.services.kafka_service.settings")
    def test_configure_quota_no_admin_client_raises(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        kafka_svc._admin_client = None
        with pytest.raises(RuntimeError, match="not initialized"):
            kafka_svc.configure_tenant_quota("acme", "standard")

    @patch("src.services.kafka_service.settings")
    def test_configure_quota_invalid_tier_raises(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        mock_admin = MagicMock()
        kafka_svc._admin_client = mock_admin
        with pytest.raises(ValueError, match="Invalid tier"):
            kafka_svc.configure_tenant_quota("acme", "invalid")

    @patch("src.services.kafka_service.settings")
    def test_configure_standard_quota_success(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        mock_admin = MagicMock()
        kafka_svc._admin_client = mock_admin

        result = kafka_svc.configure_tenant_quota("acme", "standard")

        assert result is True
        mock_admin.alter_configs.assert_called_once()
        call_args = mock_admin.alter_configs.call_args[0][0]
        assert len(call_args) == 1
        quota_entity = call_args[0]
        assert quota_entity.name == "tenant-acme"
        assert quota_entity.configs["producer_byte_rate"] == str(10 * 1024 * 1024)
        assert quota_entity.configs["consumer_byte_rate"] == str(20 * 1024 * 1024)
        assert quota_entity.configs["request_percentage"] == "25.0"

    @patch("src.services.kafka_service.settings")
    def test_configure_premium_quota_success(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        mock_admin = MagicMock()
        kafka_svc._admin_client = mock_admin

        result = kafka_svc.configure_tenant_quota("acme", "premium")

        assert result is True
        mock_admin.alter_configs.assert_called_once()
        call_args = mock_admin.alter_configs.call_args[0][0]
        quota_entity = call_args[0]
        assert quota_entity.name == "tenant-premium-acme"
        assert quota_entity.configs["producer_byte_rate"] == str(50 * 1024 * 1024)
        assert quota_entity.configs["consumer_byte_rate"] == str(100 * 1024 * 1024)
        assert quota_entity.configs["request_percentage"] == "50.0"

    @patch("src.services.kafka_service.settings")
    def test_configure_quota_kafka_error_raises(self, mock_settings, kafka_svc):
        """Verify that Kafka errors are propagated."""
        from kafka.errors import KafkaError

        mock_settings.KAFKA_ENABLED = True
        mock_admin = MagicMock()
        mock_admin.alter_configs.side_effect = KafkaError("Connection failed")
        kafka_svc._admin_client = mock_admin

        with pytest.raises(KafkaError):
            kafka_svc.configure_tenant_quota("acme", "standard")


class TestGetTenantQuota:
    """Tests for retrieving tenant quota configuration."""

    @patch("src.services.kafka_service.settings")
    def test_get_quota_disabled_returns_empty(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = False
        result = kafka_svc.get_tenant_quota("acme", "standard")
        assert result == {}

    @patch("src.services.kafka_service.settings")
    def test_get_quota_no_admin_client_raises(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        kafka_svc._admin_client = None
        with pytest.raises(RuntimeError, match="not initialized"):
            kafka_svc.get_tenant_quota("acme", "standard")

    @patch("src.services.kafka_service.settings")
    def test_get_quota_success(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        mock_admin = MagicMock()

        # Mock the response structure from describe_configs
        mock_config_entry = MagicMock()
        mock_config_entry.resources = [
            (
                None,  # type
                "tenant-acme",  # name
                None,  # error
                None,  # msg
                {  # configs
                    "producer_byte_rate": {"value": "10485760"},
                    "consumer_byte_rate": {"value": "20971520"},
                    "request_percentage": {"value": "25.0"},
                },
            )
        ]
        mock_admin.describe_configs.return_value = [mock_config_entry]
        kafka_svc._admin_client = mock_admin

        result = kafka_svc.get_tenant_quota("acme", "standard")

        assert result["producer_byte_rate"] == 10485760
        assert result["consumer_byte_rate"] == 20971520
        assert result["request_percentage"] == 25.0

    @patch("src.services.kafka_service.settings")
    def test_get_quota_not_found_returns_empty(self, mock_settings, kafka_svc):
        mock_settings.KAFKA_ENABLED = True
        mock_admin = MagicMock()
        mock_admin.describe_configs.return_value = []
        kafka_svc._admin_client = mock_admin

        result = kafka_svc.get_tenant_quota("nonexistent", "standard")

        assert result == {}
