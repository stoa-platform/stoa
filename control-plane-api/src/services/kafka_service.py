"""Kafka service for event-driven architecture"""

import json
import logging
import uuid
from datetime import datetime

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

from ..config import settings
from ..core.pii.masker import MaskingContext, get_masker

logger = logging.getLogger(__name__)

EVENT_SOURCE = "control-plane-api"
EVENT_VERSION = "1.0"


# Kafka topics — stoa.X.Y naming convention
class Topics:
    API_EVENTS = "stoa.api.lifecycle"
    DEPLOY_REQUESTS = "stoa.deploy.requests"
    DEPLOY_RESULTS = "stoa.deploy.results"
    APP_EVENTS = "stoa.app.lifecycle"
    TENANT_EVENTS = "stoa.tenant.lifecycle"
    AUDIT_LOG = "stoa.audit.trail"

    # MCP GitOps events
    MCP_SERVER_EVENTS = "stoa.mcp.servers"
    MCP_SYNC_REQUESTS = "stoa.mcp.sync.requests"
    MCP_SYNC_RESULTS = "stoa.mcp.sync.results"

    # Gateway orchestration events
    GATEWAY_SYNC_REQUESTS = "stoa.gateway.sync.requests"
    GATEWAY_SYNC_RESULTS = "stoa.gateway.sync.results"
    GATEWAY_EVENTS = "stoa.gateway.events"

    # New CNS topics
    SECURITY_ALERTS = "stoa.security.alerts"
    GATEWAY_METRICS = "stoa.gateway.metrics"
    DEPLOYMENT_EVENTS = "stoa.deployment.events"
    RESOURCE_LIFECYCLE = "stoa.resource.lifecycle"
    METERING_EVENTS = "stoa.metering.events"
    FEDERATION_EVENTS = "stoa.federation.events"

    # Deploy log streaming (CAB-1420)
    DEPLOYMENT_LOGS = "stoa.deployment.logs"

    # Tenant provisioning (CAB-1315)
    TENANT_PROVISIONING = "stoa.tenant.provisioning"

    # Onboarding workflows (CAB-593)
    WORKFLOW_EVENTS = "stoa.workflow.events"

    # CAB-498: Audit, catalog, and error tracking
    AUDIT_EVENTS = "stoa.audit.events"
    CATALOG_CHANGES = "stoa.catalog.changes"
    ERRORS = "stoa.errors"

    # CAB-1347: Policy propagation
    POLICY_CHANGES = "stoa.policy.changes"


class KafkaService:
    """Service for Kafka/Redpanda message handling"""

    def __init__(self):
        self._producer: KafkaProducer | None = None
        self._consumers: dict[str, KafkaConsumer] = {}

    async def connect(self):
        """Initialize Kafka producer with retry logic"""
        if not settings.KAFKA_ENABLED:
            logger.info("Kafka disabled — skipping producer initialization")
            return

        import time

        max_retries = 5
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    acks="all",
                    retries=3,
                    request_timeout_ms=10000,
                    api_version_auto_timeout_ms=10000,
                )
                logger.info("Kafka producer connected")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Kafka connection attempt {attempt + 1} failed: {e}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to connect to Kafka after {max_retries} attempts: {e}")
                    raise

    async def disconnect(self):
        """Close Kafka connections"""
        if self._producer:
            self._producer.close()
            self._producer = None

        for consumer in self._consumers.values():
            consumer.close()
        self._consumers.clear()

        logger.info("Kafka connections closed")

    def _create_event(self, event_type: str, tenant_id: str, payload: dict, user_id: str | None = None) -> dict:
        """Create a standardized event envelope with canonical fields."""
        return {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "source": EVENT_SOURCE,
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": EVENT_VERSION,
            "user_id": user_id,
            "payload": payload,
        }

    async def publish(
        self,
        topic: str,
        event_type: str,
        tenant_id: str,
        payload: dict,
        user_id: str | None = None,
        key: str | None = None,
    ) -> str:
        """
        Publish an event to a Kafka topic.

        Args:
            topic: Kafka topic name
            event_type: Type of event (e.g., "api-created")
            tenant_id: Tenant ID for filtering
            payload: Event data
            user_id: User who triggered the event
            key: Optional partition key (defaults to tenant_id)

        Returns:
            Event ID
        """
        if not settings.KAFKA_ENABLED:
            logger.debug(f"Kafka disabled — skipping {event_type} event to {topic}")
            return str(uuid.uuid4())

        if not self._producer:
            raise RuntimeError("Kafka producer not initialized")

        masker = get_masker()
        masked_payload = masker.mask_dict(
            payload,
            context=MaskingContext(tenant_id=tenant_id, source="kafka-publish"),
        )
        event = self._create_event(event_type, tenant_id, masked_payload, user_id)
        partition_key = key or tenant_id

        try:
            future = self._producer.send(topic, value=event, key=partition_key)
            future.get(timeout=10)  # Wait for confirmation
            logger.info(f"Published {event_type} event to {topic}: {event['id']}")
            return event["id"]
        except KafkaError as e:
            logger.error(f"Failed to publish event: {e}")
            raise

    # Convenience methods for common events
    async def emit_api_created(self, tenant_id: str, api_data: dict, user_id: str) -> str:
        """Emit api-created event"""
        return await self.publish(Topics.API_EVENTS, "api-created", tenant_id, api_data, user_id)

    async def emit_api_updated(self, tenant_id: str, api_data: dict, user_id: str) -> str:
        """Emit api-updated event"""
        return await self.publish(Topics.API_EVENTS, "api-updated", tenant_id, api_data, user_id)

    async def emit_api_deleted(self, tenant_id: str, api_id: str, user_id: str) -> str:
        """Emit api-deleted event"""
        return await self.publish(Topics.API_EVENTS, "api-deleted", tenant_id, {"api_id": api_id}, user_id)

    async def emit_deploy_request(
        self, tenant_id: str, api_id: str, environment: str, version: str, user_id: str
    ) -> str:
        """Emit deployment request for gateway adapter to process"""
        return await self.publish(
            Topics.DEPLOY_REQUESTS,
            "deploy-request",
            tenant_id,
            {
                "api_id": api_id,
                "environment": environment,
                "version": version,
                "requested_by": user_id,
            },
            user_id,
        )

    async def emit_audit_event(
        self,
        tenant_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        details: dict | None = None,
    ) -> str:
        """Emit audit log event"""
        return await self.publish(
            Topics.AUDIT_LOG,
            "audit",
            tenant_id,
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "details": details or {},
            },
            user_id,
        )

    async def emit_security_alert(
        self,
        tenant_id: str,
        event_type: str,
        severity: str,
        details: dict,
        source: str = EVENT_SOURCE,
    ) -> str:
        """Emit a security alert to the security alerts topic."""
        return await self.publish(
            Topics.SECURITY_ALERTS,
            event_type,
            tenant_id,
            {
                "severity": severity,
                "source": source,
                "details": details,
            },
        )

    async def emit_subscription_event(
        self,
        tenant_id: str,
        subscription_data: dict,
        user_id: str,
    ) -> str:
        """Emit a subscription lifecycle event."""
        return await self.publish(
            Topics.RESOURCE_LIFECYCLE,
            "subscription-changed",
            tenant_id,
            subscription_data,
            user_id,
        )

    async def emit_policy_created(self, tenant_id: str, policy_data: dict, user_id: str) -> str:
        """Emit policy-created event to stoa.policy.changes."""
        return await self.publish(Topics.POLICY_CHANGES, "policy-created", tenant_id, policy_data, user_id)

    async def emit_policy_updated(self, tenant_id: str, policy_data: dict, user_id: str) -> str:
        """Emit policy-updated event to stoa.policy.changes."""
        return await self.publish(Topics.POLICY_CHANGES, "policy-updated", tenant_id, policy_data, user_id)

    async def emit_policy_deleted(self, tenant_id: str, policy_id: str, user_id: str) -> str:
        """Emit policy-deleted event to stoa.policy.changes."""
        return await self.publish(
            Topics.POLICY_CHANGES, "policy-deleted", tenant_id, {"policy_id": policy_id}, user_id
        )

    async def emit_policy_binding_created(self, tenant_id: str, binding_data: dict, user_id: str) -> str:
        """Emit policy-binding-created event to stoa.policy.changes."""
        return await self.publish(
            Topics.POLICY_CHANGES, "policy-binding-created", tenant_id, binding_data, user_id
        )

    async def emit_policy_binding_deleted(self, tenant_id: str, binding_data: dict, user_id: str) -> str:
        """Emit policy-binding-deleted event to stoa.policy.changes."""
        return await self.publish(
            Topics.POLICY_CHANGES, "policy-binding-deleted", tenant_id, binding_data, user_id
        )

    def create_consumer(self, topics: list[str], group_id: str, tenant_filter: str | None = None) -> KafkaConsumer:
        """
        Create a Kafka consumer for the specified topics.

        Args:
            topics: List of topics to subscribe to
            group_id: Consumer group ID
            tenant_filter: Optional tenant_id to filter events

        Returns:
            KafkaConsumer instance
        """
        consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )

        consumer_id = f"{group_id}-{uuid.uuid4().hex[:8]}"
        self._consumers[consumer_id] = consumer

        logger.info(f"Created consumer {consumer_id} for topics: {topics}")
        return consumer


# Global instance
kafka_service = KafkaService()
