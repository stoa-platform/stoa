"""Kafka service for event-driven architecture"""
import json
import logging
from typing import Optional, Callable, Any
from datetime import datetime
import uuid

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

from ..config import settings

logger = logging.getLogger(__name__)

# Kafka topics
class Topics:
    API_EVENTS = "api-events"           # api-created, api-updated, api-deleted
    DEPLOY_REQUESTS = "deploy-requests"  # Deployment requests for AWX
    DEPLOY_RESULTS = "deploy-results"    # Deployment results from AWX
    APP_EVENTS = "app-events"           # Application lifecycle events
    TENANT_EVENTS = "tenant-events"     # Tenant lifecycle events
    AUDIT_LOG = "audit-log"             # Audit trail

class KafkaService:
    """Service for Kafka/Redpanda message handling"""

    def __init__(self):
        self._producer: Optional[KafkaProducer] = None
        self._consumers: dict[str, KafkaConsumer] = {}

    async def connect(self):
        """Initialize Kafka producer"""
        try:
            self._producer = KafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
            )
            logger.info("Kafka producer connected")
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
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

    def _create_event(
        self,
        event_type: str,
        tenant_id: str,
        payload: dict,
        user_id: Optional[str] = None
    ) -> dict:
        """Create a standardized event envelope"""
        return {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "payload": payload,
        }

    async def publish(
        self,
        topic: str,
        event_type: str,
        tenant_id: str,
        payload: dict,
        user_id: Optional[str] = None,
        key: Optional[str] = None
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
        if not self._producer:
            raise RuntimeError("Kafka producer not initialized")

        event = self._create_event(event_type, tenant_id, payload, user_id)
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
        return await self.publish(
            Topics.API_EVENTS,
            "api-created",
            tenant_id,
            api_data,
            user_id
        )

    async def emit_api_updated(self, tenant_id: str, api_data: dict, user_id: str) -> str:
        """Emit api-updated event"""
        return await self.publish(
            Topics.API_EVENTS,
            "api-updated",
            tenant_id,
            api_data,
            user_id
        )

    async def emit_api_deleted(self, tenant_id: str, api_id: str, user_id: str) -> str:
        """Emit api-deleted event"""
        return await self.publish(
            Topics.API_EVENTS,
            "api-deleted",
            tenant_id,
            {"api_id": api_id},
            user_id
        )

    async def emit_deploy_request(
        self,
        tenant_id: str,
        api_id: str,
        environment: str,
        version: str,
        user_id: str
    ) -> str:
        """Emit deployment request for AWX to process"""
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
            user_id
        )

    async def emit_audit_event(
        self,
        tenant_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        details: Optional[dict] = None
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
            user_id
        )

    def create_consumer(
        self,
        topics: list[str],
        group_id: str,
        tenant_filter: Optional[str] = None
    ) -> KafkaConsumer:
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
