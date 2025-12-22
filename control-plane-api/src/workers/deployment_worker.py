"""
Deployment Worker - Consumes Kafka events and triggers AWX jobs.

This worker listens to the deploy-requests topic and triggers
the appropriate AWX job template based on the event type.

Pipeline: Control-Plane API → Kafka → DeploymentWorker → AWX → Gateway
"""
import asyncio
import logging
import json
from typing import Optional
from datetime import datetime

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from ..config import settings
from ..services.kafka_service import kafka_service, Topics
from ..services.awx_service import awx_service
from ..services.git_service import git_service

logger = logging.getLogger(__name__)


class DeploymentWorker:
    """
    Worker that consumes deployment requests from Kafka
    and triggers AWX jobs to deploy/rollback APIs on the Gateway.
    """

    def __init__(self):
        self._consumer: Optional[KafkaConsumer] = None
        self._running = False
        self._consumer_group = "deployment-worker"

    async def start(self):
        """Start the deployment worker"""
        logger.info("Starting Deployment Worker...")

        # Connect to services
        await awx_service.connect()

        # Create Kafka consumer
        self._consumer = KafkaConsumer(
            Topics.DEPLOY_REQUESTS,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
            group_id=self._consumer_group,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            consumer_timeout_ms=1000,  # Timeout for non-blocking consume
        )

        self._running = True
        logger.info(f"Deployment Worker started, consuming from {Topics.DEPLOY_REQUESTS}")

        # Start consuming
        await self._consume_loop()

    async def stop(self):
        """Stop the deployment worker"""
        logger.info("Stopping Deployment Worker...")
        self._running = False

        if self._consumer:
            self._consumer.close()
            self._consumer = None

        await awx_service.disconnect()
        logger.info("Deployment Worker stopped")

    async def _consume_loop(self):
        """Main consume loop"""
        while self._running:
            try:
                # Non-blocking consume with timeout
                for message in self._consumer:
                    if not self._running:
                        break

                    try:
                        await self._process_message(message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}", exc_info=True)

                # Small delay to prevent busy loop
                await asyncio.sleep(0.1)

            except KafkaError as e:
                logger.error(f"Kafka error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
            except Exception as e:
                logger.error(f"Unexpected error in consume loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _process_message(self, message):
        """Process a single Kafka message"""
        event = message.value
        event_type = event.get("type")
        tenant_id = event.get("tenant_id")
        payload = event.get("payload", {})
        event_id = event.get("id")

        logger.info(f"Processing event {event_id}: {event_type} for tenant {tenant_id}")

        try:
            if event_type == "deploy-request":
                await self._handle_deploy_request(tenant_id, payload, event_id)
            elif event_type == "rollback-request":
                await self._handle_rollback_request(tenant_id, payload, event_id)
            elif event_type == "promote-request":
                await self._handle_promote_request(tenant_id, payload, event_id)
            elif event_type == "sync-request":
                await self._handle_sync_request(tenant_id, payload, event_id)
            elif event_type == "tenant-provisioning":
                await self._handle_tenant_provisioning(tenant_id, payload, event_id)
            elif event_type == "api-registration":
                await self._handle_api_registration(tenant_id, payload, event_id)
            else:
                logger.warning(f"Unknown event type: {event_type}")

        except Exception as e:
            logger.error(f"Failed to process {event_type}: {e}", exc_info=True)
            # Emit failure event
            await self._emit_result(
                tenant_id=tenant_id,
                api_id=payload.get("api_id", ""),
                status="failed",
                error=str(e),
                event_id=event_id
            )

    async def _handle_deploy_request(self, tenant_id: str, payload: dict, event_id: str):
        """Handle API deployment request"""
        api_id = payload.get("api_id")
        api_name = payload.get("api_name")
        environment = payload.get("environment", "dev")
        version = payload.get("version", "1.0.0")
        openapi_spec = payload.get("openapi_spec")
        backend_url = payload.get("backend_url")

        logger.info(f"Deploying API {api_name} v{version} to {environment}")

        # Get API spec from GitLab if not provided
        if not openapi_spec and api_name:
            try:
                openapi_spec = await git_service.get_file(
                    f"tenants/{tenant_id}/apis/{api_name}/openapi.yaml"
                )
            except Exception as e:
                logger.warning(f"Could not fetch OpenAPI spec from GitLab: {e}")

        # Launch AWX job
        job = await awx_service.deploy_api(
            tenant_id=tenant_id,
            api_id=api_id,
            api_name=api_name,
            environment=environment,
            version=version,
            backend_url=backend_url or ""
        )

        job_id = job.get("id")
        logger.info(f"Launched AWX job {job_id} for deployment")

        # Start monitoring the job
        asyncio.create_task(self._monitor_job(
            job_id=job_id,
            tenant_id=tenant_id,
            api_id=api_id,
            api_name=api_name,
            action="deploy",
            event_id=event_id
        ))

    async def _handle_rollback_request(self, tenant_id: str, payload: dict, event_id: str):
        """Handle API rollback request"""
        api_id = payload.get("api_id")
        environment = payload.get("environment", "dev")
        target_version = payload.get("target_version")

        logger.info(f"Rolling back API {api_id} to v{target_version}")

        job = await awx_service.rollback_api(
            tenant_id=tenant_id,
            api_id=api_id,
            environment=environment,
            target_version=target_version or ""
        )

        job_id = job.get("id")
        logger.info(f"Launched AWX job {job_id} for rollback")

        asyncio.create_task(self._monitor_job(
            job_id=job_id,
            tenant_id=tenant_id,
            api_id=api_id,
            api_name="",
            action="rollback",
            event_id=event_id
        ))

    async def _handle_promote_request(self, tenant_id: str, payload: dict, event_id: str):
        """Handle API promotion to portal request"""
        api_id = payload.get("api_id")
        api_name = payload.get("api_name")

        logger.info(f"Promoting API {api_name} to Developer Portal")

        # Get promote-portal template
        template = await awx_service.get_job_template_by_name("Promote Portal")
        if not template:
            raise ValueError("Job template 'Promote Portal' not found")

        job = await awx_service.launch_job(
            template_id=template["id"],
            extra_vars={
                "tenant_id": tenant_id,
                "api_id": api_id,
                "api_name": api_name,
            }
        )

        job_id = job.get("id")
        logger.info(f"Launched AWX job {job_id} for portal promotion")

        asyncio.create_task(self._monitor_job(
            job_id=job_id,
            tenant_id=tenant_id,
            api_id=api_id,
            api_name=api_name,
            action="promote",
            event_id=event_id
        ))

    async def _handle_sync_request(self, tenant_id: str, payload: dict, event_id: str):
        """Handle Gateway sync request"""
        logger.info(f"Syncing Gateway for tenant {tenant_id}")

        # Get sync-gateway template
        template = await awx_service.get_job_template_by_name("Sync Gateway")
        if not template:
            raise ValueError("Job template 'Sync Gateway' not found")

        job = await awx_service.launch_job(
            template_id=template["id"],
            extra_vars={
                "tenant_id": tenant_id,
            }
        )

        job_id = job.get("id")
        logger.info(f"Launched AWX job {job_id} for gateway sync")

        asyncio.create_task(self._monitor_job(
            job_id=job_id,
            tenant_id=tenant_id,
            api_id="",
            api_name="",
            action="sync",
            event_id=event_id
        ))

    async def _handle_tenant_provisioning(self, tenant_id: str, payload: dict, event_id: str):
        """
        Handle tenant provisioning request.

        Creates Keycloak groups, users, and K8s namespaces via AWX playbook.
        """
        tenant_name = payload.get("tenant_name", tenant_id)
        users = payload.get("users", [])
        environments = payload.get("environments", ["dev", "staging"])

        logger.info(f"Provisioning tenant {tenant_id} with {len(users)} users")

        # If users not provided in payload, try to fetch from GitLab
        if not users:
            try:
                users_yaml = await git_service.get_file(
                    f"tenants/{tenant_id}/iam/users.yaml"
                )
                if users_yaml:
                    import yaml
                    users_data = yaml.safe_load(users_yaml)
                    users = users_data.get("users", [])
                    logger.info(f"Loaded {len(users)} users from GitLab")
            except Exception as e:
                logger.warning(f"Could not fetch users from GitLab: {e}")

        # Launch AWX provisioning job
        job = await awx_service.provision_tenant(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            users=users,
            environments=environments
        )

        job_id = job.get("id")
        logger.info(f"Launched AWX job {job_id} for tenant provisioning")

        asyncio.create_task(self._monitor_job(
            job_id=job_id,
            tenant_id=tenant_id,
            api_id="",
            api_name="",
            action="provision-tenant",
            event_id=event_id
        ))

    async def _handle_api_registration(self, tenant_id: str, payload: dict, event_id: str):
        """
        Handle API registration in Gateway request.

        Imports API from OpenAPI spec, configures OIDC and policies via AWX playbook.
        """
        api_name = payload.get("api_name")
        api_version = payload.get("api_version", "1.0")
        openapi_url = payload.get("openapi_url", "")
        backend_url = payload.get("backend_url", "")
        oidc_enabled = payload.get("oidc_enabled", True)
        rate_limit = payload.get("rate_limit", 100)

        logger.info(f"Registering API {api_name} v{api_version} in Gateway")

        # If OpenAPI URL not provided, construct from internal service
        if not openapi_url and backend_url:
            openapi_url = f"{backend_url}/openapi.json"

        # Launch AWX registration job
        job = await awx_service.register_api_gateway(
            tenant_id=tenant_id,
            api_name=api_name,
            api_version=api_version,
            openapi_url=openapi_url,
            backend_url=backend_url,
            oidc_enabled=oidc_enabled,
            rate_limit=rate_limit
        )

        job_id = job.get("id")
        logger.info(f"Launched AWX job {job_id} for API registration")

        asyncio.create_task(self._monitor_job(
            job_id=job_id,
            tenant_id=tenant_id,
            api_id="",
            api_name=api_name,
            action="register-api",
            event_id=event_id
        ))

    async def _monitor_job(
        self,
        job_id: int,
        tenant_id: str,
        api_id: str,
        api_name: str,
        action: str,
        event_id: str
    ):
        """Monitor AWX job until completion"""
        max_wait_seconds = 300  # 5 minutes
        poll_interval = 5  # seconds
        elapsed = 0

        while elapsed < max_wait_seconds:
            try:
                job = await awx_service.get_job(job_id)
                status = job.get("status")

                logger.debug(f"Job {job_id} status: {status}")

                if status in ("successful", "failed", "canceled", "error"):
                    # Job finished
                    success = status == "successful"

                    # Get job output for details
                    stdout = ""
                    try:
                        stdout = await awx_service.get_job_stdout(job_id)
                    except Exception:
                        pass

                    await self._emit_result(
                        tenant_id=tenant_id,
                        api_id=api_id,
                        api_name=api_name,
                        action=action,
                        status="success" if success else "failed",
                        job_id=job_id,
                        message=f"AWX job {status}",
                        details=stdout[-1000:] if stdout else "",  # Last 1000 chars
                        event_id=event_id
                    )

                    logger.info(f"Job {job_id} completed with status: {status}")
                    return

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            except Exception as e:
                logger.error(f"Error monitoring job {job_id}: {e}")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        # Timeout
        logger.warning(f"Job {job_id} timed out after {max_wait_seconds}s")
        await self._emit_result(
            tenant_id=tenant_id,
            api_id=api_id,
            api_name=api_name,
            action=action,
            status="timeout",
            job_id=job_id,
            message="AWX job timed out",
            event_id=event_id
        )

    async def _emit_result(
        self,
        tenant_id: str,
        api_id: str,
        status: str,
        api_name: str = "",
        action: str = "",
        job_id: int = 0,
        message: str = "",
        details: str = "",
        error: str = "",
        event_id: str = ""
    ):
        """Emit deployment result to Kafka"""
        try:
            await kafka_service.publish(
                topic=Topics.DEPLOY_RESULTS,
                event_type=f"{action}-result" if action else "deployment-result",
                tenant_id=tenant_id,
                payload={
                    "api_id": api_id,
                    "api_name": api_name,
                    "action": action,
                    "status": status,
                    "awx_job_id": job_id,
                    "message": message,
                    "details": details,
                    "error": error,
                    "original_event_id": event_id,
                    "completed_at": datetime.utcnow().isoformat() + "Z",
                }
            )
            logger.info(f"Emitted {action}-result for API {api_id}: {status}")
        except Exception as e:
            logger.error(f"Failed to emit deployment result: {e}")


# Global instance
deployment_worker = DeploymentWorker()
