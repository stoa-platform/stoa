#!/usr/bin/env python3
"""
Create Kafka topics from topic-policies.yaml configuration.

Usage:
    # Dry-run (show what would be created)
    python create-topics.py --dry-run

    # Create topics
    python create-topics.py --broker localhost:9092

    # With Redpanda
    python create-topics.py --broker localhost:9092 --redpanda

Dependencies:
    pip install pyyaml kafka-python
"""

import argparse
import sys
from pathlib import Path

import yaml
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError


def load_topic_policies(yaml_path: Path) -> dict:
    """Load topic policies from YAML file."""
    with open(yaml_path) as f:
        config = yaml.safe_load(f)
    return config.get("topics", {})


def create_topics(broker: str, topics_config: dict, replication_factor: int = 3, dry_run: bool = False):
    """Create Kafka topics based on policy configuration."""
    if dry_run:
        print("DRY RUN - Topics that would be created:")
        print("-" * 80)

    topics_to_create = []

    for topic_name, config in topics_config.items():
        partitions = config.get("partitions", 3)
        retention_days = config.get("retention_days", 30)
        retention_ms = retention_days * 24 * 60 * 60 * 1000 if retention_days > 0 else -1
        delivery = config.get("delivery", "at_least_once")
        description = config.get("description", "")

        # Kafka topic configs
        topic_configs = {
            "retention.ms": str(retention_ms),
            "min.insync.replicas": "2",  # RF=3, min.isr=2 for durability
        }

        # Exactly-once delivery requires idempotence
        if delivery == "exactly_once":
            topic_configs["cleanup.policy"] = "compact,delete"

        if dry_run:
            print(f"Topic: {topic_name}")
            print(f"  Partitions: {partitions}")
            print(f"  Replication Factor: {replication_factor}")
            print(f"  Retention: {retention_days} days ({retention_ms} ms)")
            print(f"  Delivery: {delivery}")
            print(f"  Description: {description}")
            print(f"  Config: {topic_configs}")
            print()
        else:
            new_topic = NewTopic(
                name=topic_name,
                num_partitions=partitions,
                replication_factor=replication_factor,
                topic_configs=topic_configs,
            )
            topics_to_create.append(new_topic)

    if not dry_run and topics_to_create:
        admin_client = KafkaAdminClient(
            bootstrap_servers=broker,
            client_id="stoa-topic-creator",
        )

        try:
            result = admin_client.create_topics(new_topics=topics_to_create, validate_only=False)
            for topic, future in result.items():
                try:
                    future  # Trigger any exception
                    print(f"✓ Created topic: {topic}")
                except TopicAlreadyExistsError:
                    print(f"⚠ Topic already exists: {topic}")
                except Exception as e:
                    print(f"✗ Failed to create topic {topic}: {e}")
        finally:
            admin_client.close()

    print(f"\n{'DRY RUN COMPLETE' if dry_run else 'TOPIC CREATION COMPLETE'}")
    print(f"Total topics: {len(topics_config)}")


def main():
    parser = argparse.ArgumentParser(description="Create Kafka topics from topic-policies.yaml")
    parser.add_argument(
        "--broker",
        default="localhost:9092",
        help="Kafka bootstrap server (default: localhost:9092)",
    )
    parser.add_argument(
        "--replication-factor",
        type=int,
        default=3,
        help="Replication factor (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating",
    )
    parser.add_argument(
        "--redpanda",
        action="store_true",
        help="Use Redpanda-specific settings",
    )
    parser.add_argument(
        "--yaml",
        type=Path,
        default=Path(__file__).parent / "topic-policies.yaml",
        help="Path to topic-policies.yaml (default: ./topic-policies.yaml)",
    )

    args = parser.parse_args()

    if not args.yaml.exists():
        print(f"Error: {args.yaml} not found", file=sys.stderr)
        sys.exit(1)

    topics_config = load_topic_policies(args.yaml)

    create_topics(
        broker=args.broker,
        topics_config=topics_config,
        replication_factor=args.replication_factor,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
