#!/usr/bin/env python3
"""Configure Kafka/Redpanda multi-tenant quotas to prevent noisy neighbor abuse.

Usage:
    python scripts/kafka/configure-quotas.py --broker redpanda.stoa-system.svc:9092
    python scripts/kafka/configure-quotas.py --broker redpanda.stoa-system.svc:9092 --dry-run

Quotas:
    - Standard tier: 10MB/s producer, 20MB/s consumer, 25% CPU
    - Premium tier: 50MB/s producer, 100MB/s consumer, 50% CPU
"""

import argparse
import logging
import sys
from typing import Any

from kafka.admin import KafkaAdminClient, QuotaEntity, QuotaEntityType, QuotaOperation

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Quota tiers (values in bytes/sec for throughput, percentage for CPU)
STANDARD_TIER = {
    "producer_byte_rate": 10 * 1024 * 1024,  # 10 MB/s
    "consumer_byte_rate": 20 * 1024 * 1024,  # 20 MB/s
    "request_percentage": 25.0,  # 25% CPU
}

PREMIUM_TIER = {
    "producer_byte_rate": 50 * 1024 * 1024,  # 50 MB/s
    "consumer_byte_rate": 100 * 1024 * 1024,  # 100 MB/s
    "request_percentage": 50.0,  # 50% CPU
}


def configure_quota(
    admin_client: KafkaAdminClient,
    client_id: str,
    producer_byte_rate: int,
    consumer_byte_rate: int,
    request_percentage: float,
    dry_run: bool = False,
) -> None:
    """Configure quota for a client ID pattern.

    Args:
        admin_client: KafkaAdminClient instance
        client_id: Client ID pattern (e.g., "tenant-*", "tenant-premium-*")
        producer_byte_rate: Producer throughput limit (bytes/sec)
        consumer_byte_rate: Consumer throughput limit (bytes/sec)
        request_percentage: CPU request % limit (e.g., 25.0)
        dry_run: If True, only log what would be done
    """
    entity = QuotaEntity(entity_type=QuotaEntityType.CLIENT_ID, entity_name=client_id)

    operations = [
        QuotaOperation("producer_byte_rate", producer_byte_rate),
        QuotaOperation("consumer_byte_rate", consumer_byte_rate),
        QuotaOperation("request_percentage", request_percentage),
    ]

    if dry_run:
        logger.info(
            f"[DRY RUN] Would set quota for client_id={client_id}: "
            f"prod={producer_byte_rate / 1024 / 1024:.1f}MB/s, "
            f"cons={consumer_byte_rate / 1024 / 1024:.1f}MB/s, "
            f"cpu={request_percentage}%"
        )
        return

    try:
        admin_client.alter_client_quotas(entities=[entity], quotas=operations, validate_only=False)
        logger.info(
            f"✓ Configured quota for client_id={client_id}: "
            f"prod={producer_byte_rate / 1024 / 1024:.1f}MB/s, "
            f"cons={consumer_byte_rate / 1024 / 1024:.1f}MB/s, "
            f"cpu={request_percentage}%"
        )
    except Exception as e:
        logger.error(f"✗ Failed to configure quota for client_id={client_id}: {e}")
        raise


def verify_quotas(admin_client: KafkaAdminClient, client_ids: list[str]) -> dict[str, Any]:
    """Verify configured quotas.

    Args:
        admin_client: KafkaAdminClient instance
        client_ids: List of client ID patterns to check

    Returns:
        Dict mapping client_id to quota config
    """
    results = {}
    for client_id in client_ids:
        entity = QuotaEntity(entity_type=QuotaEntityType.CLIENT_ID, entity_name=client_id)
        try:
            quotas = admin_client.describe_client_quotas(entities=[entity])
            results[client_id] = quotas
            if quotas:
                logger.info(f"✓ Quota verification for client_id={client_id}: {quotas}")
            else:
                logger.warning(f"⚠ No quota found for client_id={client_id}")
        except Exception as e:
            logger.error(f"✗ Failed to verify quota for client_id={client_id}: {e}")
            results[client_id] = None
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Configure Kafka/Redpanda multi-tenant quotas")
    parser.add_argument(
        "--broker",
        default="redpanda.stoa-system.svc:9092",
        help="Kafka broker address (default: redpanda.stoa-system.svc:9092)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing quotas without applying",
    )

    args = parser.parse_args()

    logger.info(f"Connecting to Kafka broker: {args.broker}")

    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=[args.broker],
            client_id="quota-configurator",
            request_timeout_ms=10000,
        )
    except Exception as e:
        logger.error(f"Failed to connect to Kafka broker {args.broker}: {e}")
        return 1

    client_ids = ["tenant-*", "tenant-premium-*"]

    if args.verify_only:
        logger.info("Verifying existing quotas...")
        results = verify_quotas(admin_client, client_ids)
        if all(v is not None for v in results.values()):
            logger.info("✓ All quotas verified successfully")
            return 0
        else:
            logger.warning("⚠ Some quotas are missing or failed verification")
            return 1

    logger.info("Configuring Kafka quotas...")

    try:
        # Standard tier: tenant-*
        configure_quota(
            admin_client,
            client_id="tenant-*",
            producer_byte_rate=STANDARD_TIER["producer_byte_rate"],
            consumer_byte_rate=STANDARD_TIER["consumer_byte_rate"],
            request_percentage=STANDARD_TIER["request_percentage"],
            dry_run=args.dry_run,
        )

        # Premium tier: tenant-premium-*
        configure_quota(
            admin_client,
            client_id="tenant-premium-*",
            producer_byte_rate=PREMIUM_TIER["producer_byte_rate"],
            consumer_byte_rate=PREMIUM_TIER["consumer_byte_rate"],
            request_percentage=PREMIUM_TIER["request_percentage"],
            dry_run=args.dry_run,
        )

        if not args.dry_run:
            logger.info("\nVerifying applied quotas...")
            verify_quotas(admin_client, client_ids)

        logger.info("\n✓ Quota configuration complete")
        return 0

    except Exception as e:
        logger.error(f"Quota configuration failed: {e}")
        return 1
    finally:
        admin_client.close()


if __name__ == "__main__":
    sys.exit(main())
