"""MinIO/S3 storage for error snapshots.

CAB-397: Async storage abstraction using aioboto3.
Stores snapshots as gzipped JSON with date-based partitioning.
"""

import gzip
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aioboto3
from botocore.exceptions import ClientError

from .config import SnapshotSettings
from .models import ErrorSnapshot, SnapshotSummary

logger = logging.getLogger(__name__)


class SnapshotStorage:
    """Async MinIO/S3 storage for error snapshots.

    Features:
    - Gzip compression for efficient storage
    - Date-based path partitioning for easy cleanup
    - Tenant isolation via path prefix
    - Automatic bucket creation
    """

    def __init__(self, settings: SnapshotSettings):
        self.settings = settings
        self._session: aioboto3.Session | None = None
        self._connected = False

    async def connect(self) -> None:
        """Initialize S3 session and ensure bucket exists."""
        self._session = aioboto3.Session()

        # Create bucket if it doesn't exist
        try:
            async with self._get_client() as client:
                try:
                    await client.head_bucket(Bucket=self.settings.storage_bucket)
                    logger.info(f"snapshot_storage_connected bucket={self.settings.storage_bucket}")
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "")
                    if error_code in ("404", "NoSuchBucket"):
                        await client.create_bucket(Bucket=self.settings.storage_bucket)
                        logger.info(f"snapshot_bucket_created bucket={self.settings.storage_bucket}")
                    else:
                        raise

            self._connected = True
        except Exception as e:
            logger.error(f"snapshot_storage_connection_failed: {e}", exc_info=True)
            raise

    def _get_client(self):
        """Get S3 client context manager."""
        if not self._session:
            self._session = aioboto3.Session()

        return self._session.client(
            "s3",
            endpoint_url=self.settings.storage_url,
            aws_access_key_id=self.settings.storage_access_key,
            aws_secret_access_key=self.settings.storage_secret_key,
            region_name=self.settings.storage_region,
        )

    def _get_object_key(self, snapshot: ErrorSnapshot) -> str:
        """Generate S3 object key for snapshot.

        Pattern: {tenant_id}/{year}/{month}/{day}/{snapshot_id}.json.gz
        """
        ts = snapshot.timestamp
        return (
            f"{snapshot.tenant_id}/"
            f"{ts.year:04d}/{ts.month:02d}/{ts.day:02d}/"
            f"{snapshot.id}.json.gz"
        )

    def _parse_object_key(self, key: str) -> dict[str, Any]:
        """Parse S3 object key to extract metadata.

        Returns dict with tenant_id, year, month, day, snapshot_id.
        """
        parts = key.split("/")
        if len(parts) != 5:
            return {}

        tenant_id, year, month, day, filename = parts
        snapshot_id = filename.replace(".json.gz", "")

        return {
            "tenant_id": tenant_id,
            "year": int(year),
            "month": int(month),
            "day": int(day),
            "snapshot_id": snapshot_id,
        }

    async def save(self, snapshot: ErrorSnapshot) -> str:
        """Store snapshot as gzipped JSON.

        Args:
            snapshot: ErrorSnapshot to store

        Returns:
            S3 URL of stored object
        """
        key = self._get_object_key(snapshot)

        # Serialize and compress
        json_data = snapshot.model_dump_json()
        compressed = gzip.compress(json_data.encode("utf-8"))

        async with self._get_client() as client:
            await client.put_object(
                Bucket=self.settings.storage_bucket,
                Key=key,
                Body=compressed,
                ContentType="application/json",
                ContentEncoding="gzip",
                Metadata={
                    "tenant_id": snapshot.tenant_id,
                    "trigger": snapshot.trigger.value,
                    "status_code": str(snapshot.response.status),
                },
            )

        url = f"s3://{self.settings.storage_bucket}/{key}"
        logger.debug(f"snapshot_saved key={key} size={len(compressed)}")
        return url

    async def get(self, snapshot_id: str, tenant_id: str) -> ErrorSnapshot | None:
        """Retrieve and decompress snapshot.

        Args:
            snapshot_id: Snapshot ID (e.g., SNP-20260115-094512-a1b2c3d4)
            tenant_id: Tenant ID for isolation

        Returns:
            ErrorSnapshot or None if not found
        """
        # Parse date from snapshot ID (SNP-YYYYMMDD-HHMMSS-xxxxxxxx)
        try:
            date_part = snapshot_id.split("-")[1]
            year = int(date_part[:4])
            month = int(date_part[4:6])
            day = int(date_part[6:8])
        except (IndexError, ValueError):
            logger.warning(f"invalid_snapshot_id snapshot_id={snapshot_id}")
            return None

        key = f"{tenant_id}/{year:04d}/{month:02d}/{day:02d}/{snapshot_id}.json.gz"

        try:
            async with self._get_client() as client:
                response = await client.get_object(
                    Bucket=self.settings.storage_bucket,
                    Key=key,
                )
                compressed = await response["Body"].read()

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                return None
            raise

        # Decompress and parse
        json_data = gzip.decompress(compressed).decode("utf-8")
        return ErrorSnapshot.model_validate_json(json_data)

    async def list(
        self,
        tenant_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SnapshotSummary], int]:
        """List snapshots with filters.

        Args:
            tenant_id: Tenant ID for isolation
            start_date: Filter snapshots after this date
            end_date: Filter snapshots before this date
            limit: Max results to return
            offset: Skip first N results

        Returns:
            Tuple of (list of SnapshotSummary, total count)
        """
        # Build prefix for listing
        prefix = f"{tenant_id}/"

        # If date range specified, narrow down the prefix
        if start_date and end_date and start_date.date() == end_date.date():
            # Same day - use specific prefix
            prefix = (
                f"{tenant_id}/"
                f"{start_date.year:04d}/{start_date.month:02d}/{start_date.day:02d}/"
            )

        all_objects: list[dict] = []

        async with self._get_client() as client:
            paginator = client.get_paginator("list_objects_v2")

            async for page in paginator.paginate(
                Bucket=self.settings.storage_bucket,
                Prefix=prefix,
            ):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith(".json.gz"):
                        continue

                    # Parse key to extract date
                    meta = self._parse_object_key(key)
                    if not meta:
                        continue

                    # Apply date filters
                    obj_date = datetime(
                        meta["year"],
                        meta["month"],
                        meta["day"],
                        tzinfo=timezone.utc,
                    )

                    if start_date and obj_date.date() < start_date.date():
                        continue
                    if end_date and obj_date.date() > end_date.date():
                        continue

                    all_objects.append(
                        {
                            "key": key,
                            "snapshot_id": meta["snapshot_id"],
                            "last_modified": obj["LastModified"],
                        }
                    )

        # Sort by last modified (newest first)
        all_objects.sort(key=lambda x: x["last_modified"], reverse=True)

        total = len(all_objects)

        # Apply pagination
        paginated = all_objects[offset : offset + limit]

        # Fetch summaries (need to read each object for full details)
        # For performance, we could store summary metadata separately
        summaries: list[SnapshotSummary] = []

        for obj in paginated:
            snapshot = await self.get(obj["snapshot_id"], tenant_id)
            if snapshot:
                summaries.append(
                    SnapshotSummary(
                        id=snapshot.id,
                        timestamp=snapshot.timestamp,
                        tenant_id=snapshot.tenant_id,
                        trigger=snapshot.trigger,
                        status=snapshot.response.status,
                        method=snapshot.request.method,
                        path=snapshot.request.path,
                        duration_ms=snapshot.response.duration_ms,
                    )
                )

        return summaries, total

    async def delete(self, snapshot_id: str, tenant_id: str) -> bool:
        """Delete snapshot.

        Args:
            snapshot_id: Snapshot ID to delete
            tenant_id: Tenant ID for isolation

        Returns:
            True if deleted, False if not found
        """
        # Parse date from snapshot ID
        try:
            date_part = snapshot_id.split("-")[1]
            year = int(date_part[:4])
            month = int(date_part[4:6])
            day = int(date_part[6:8])
        except (IndexError, ValueError):
            return False

        key = f"{tenant_id}/{year:04d}/{month:02d}/{day:02d}/{snapshot_id}.json.gz"

        try:
            async with self._get_client() as client:
                await client.delete_object(
                    Bucket=self.settings.storage_bucket,
                    Key=key,
                )
            logger.info(f"snapshot_deleted snapshot_id={snapshot_id}")
            return True

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                return False
            raise

    async def cleanup_expired(self) -> int:
        """Delete snapshots older than retention period.

        Returns:
            Number of snapshots deleted
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(
            days=self.settings.retention_days
        )

        deleted_count = 0

        async with self._get_client() as client:
            paginator = client.get_paginator("list_objects_v2")

            async for page in paginator.paginate(
                Bucket=self.settings.storage_bucket,
            ):
                objects_to_delete = []

                for obj in page.get("Contents", []):
                    if obj["LastModified"].replace(tzinfo=timezone.utc) < cutoff_date:
                        objects_to_delete.append({"Key": obj["Key"]})

                if objects_to_delete:
                    await client.delete_objects(
                        Bucket=self.settings.storage_bucket,
                        Delete={"Objects": objects_to_delete},
                    )
                    deleted_count += len(objects_to_delete)

        logger.info(
            "snapshot_cleanup_completed",
            deleted_count=deleted_count,
            retention_days=self.settings.retention_days,
        )

        return deleted_count
