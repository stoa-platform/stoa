"""Loki client for LogQL queries (CAB-840)

Provides access to Loki logs for call history and activity feeds.
Uses httpx.AsyncClient with context managers following existing patterns.

Security Features:
- Circuit breaker for resilient service calls
- PII filtering to sanitize logs before exposure
- Input validation for tenant_id
"""
import json
import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx
from circuitbreaker import circuit, CircuitBreakerError

from ..config import settings

# ===== Security Constants (CAB-840) =====

# Regex pattern for validating tenant_id, user_id, etc.
IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

# PII patterns for sanitization (CAB-840 Security)
PII_PATTERNS = [
    # Email addresses
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL]'),
    # IPv4 addresses
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), '[IP]'),
    # JWT tokens (base64 encoded with dots)
    (re.compile(r'\beyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\b'), '[JWT]'),
    # Bearer tokens and long alphanumeric strings (likely API keys/tokens)
    (re.compile(r'\bBearer\s+[A-Za-z0-9_-]{20,}\b'), '[BEARER_TOKEN]'),
    # Passwords, secrets, API keys in key-value format
    (re.compile(r'(?:password|pwd|secret|api_key|apikey|token)["\'\s:=]+[^\s"\']{8,}', re.I), '[REDACTED]'),
    # Credit card numbers (basic pattern)
    (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CARD]'),
]

logger = logging.getLogger(__name__)


class LokiClient:
    """Service for Loki LogQL queries with circuit breaker and PII filtering."""

    def __init__(self):
        self._base_url: str = settings.LOKI_INTERNAL_URL.rstrip("/")
        self._timeout: float = float(settings.LOKI_TIMEOUT_SECONDS)
        self._enabled: bool = settings.LOKI_ENABLED
        self._circuit_failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self._circuit_recovery_timeout: int = settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    # ===== Input Validation (CAB-840 Security) =====

    def _validate_identifier(self, value: Optional[str], field: str) -> Optional[str]:
        """Validate identifier format to prevent injection.

        Args:
            value: The value to validate
            field: Field name for error messages

        Returns:
            The validated value or None

        Raises:
            ValueError: If value doesn't match safe pattern
        """
        if value is None:
            return None
        if not IDENTIFIER_PATTERN.match(value):
            raise ValueError(f"Invalid {field} format: must match ^[a-zA-Z0-9_-]{{1,64}}$")
        return value

    # ===== PII Sanitization (CAB-840 Security) =====

    def _sanitize_log_entry(self, log_text: str) -> str:
        """Sanitize log entry by removing PII.

        Removes or masks:
        - Email addresses → [EMAIL]
        - IP addresses → [IP]
        - JWT tokens → [JWT]
        - Bearer tokens → [BEARER_TOKEN]
        - Passwords/secrets/API keys → [REDACTED]
        - Credit card numbers → [CARD]

        Args:
            log_text: Raw log text that may contain PII

        Returns:
            Sanitized log text with PII masked
        """
        sanitized = log_text
        for pattern, replacement in PII_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    async def connect(self):
        """Initialize Loki client (validates connectivity)."""
        if not self._enabled:
            logger.info("Loki client disabled via configuration")
            return

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/ready")
                if response.status_code == 200:
                    logger.info(f"Loki connected at {self._base_url}")
                else:
                    logger.warning(f"Loki health check failed: {response.status_code}")
        except Exception as e:
            logger.warning(f"Loki connectivity check failed: {e}")

    async def disconnect(self):
        """Cleanup (no-op for stateless client)."""
        pass

    @circuit(
        failure_threshold=5,
        recovery_timeout=30,
        expected_exception=Exception,
        name="loki_query_range"
    )
    async def query_range(
        self,
        logql: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
        direction: str = "backward"
    ) -> Optional[List[Dict[str, Any]]]:
        """Execute LogQL range query with circuit breaker protection.

        Args:
            logql: LogQL query string (should be built using validated inputs)
            start: Start timestamp
            end: End timestamp
            limit: Maximum number of entries to return
            direction: Query direction ("forward" or "backward")

        Returns:
            List of log entries or None on error

        Raises:
            CircuitBreakerError: When circuit is open after repeated failures
        """
        if not self._enabled:
            return None

        try:
            async with httpx.AsyncClient(
                base_url=f"{self._base_url}/loki/api/v1",
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            ) as client:
                response = await client.get("/query_range", params={
                    "query": logql,
                    "start": str(int(start.timestamp() * 1e9)),  # nanoseconds
                    "end": str(int(end.timestamp() * 1e9)),
                    "limit": limit,
                    "direction": direction,
                })
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "success":
                    return self._extract_log_entries(data.get("data", {}))
                return None
        except httpx.TimeoutException:
            logger.warning(f"Loki query timeout: {logql[:50]}...")
            raise  # Let circuit breaker count this as failure
        except Exception as e:
            logger.warning(f"Loki query error: {e}")
            raise  # Let circuit breaker count this as failure

    # ===== Specific Query Methods (with validation) =====

    async def get_recent_calls(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 20,
        tool_id: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent API calls from logs with input validation.

        Args:
            user_id: User ID to filter by
            tenant_id: Tenant ID to filter by
            limit: Maximum number of calls to return
            tool_id: Optional tool ID filter
            status: Optional status filter (success, error, timeout)
            from_date: Optional start date
            to_date: Optional end date

        Returns:
            List of call entries (PII sanitized)
        """
        # Validate inputs
        self._validate_identifier(user_id, "user_id")
        self._validate_identifier(tenant_id, "tenant_id")
        if tool_id:
            self._validate_identifier(tool_id, "tool_id")

        end = to_date or datetime.utcnow()
        start = from_date or (end - timedelta(days=7))

        # Build LogQL query with stream selector and filters
        stream_selector = f'{{job="mcp-gateway",user_id="{user_id}",tenant_id="{tenant_id}"}}'
        line_filters = '| json'

        if tool_id:
            line_filters += f' | tool_id="{tool_id}"'
        if status:
            line_filters += f' | status="{status}"'

        query = f'{stream_selector} {line_filters}'

        try:
            entries = await self.query_range(query, start, end, limit=limit)
            return self._format_call_entries(entries or [])
        except CircuitBreakerError:
            logger.warning("Loki circuit breaker open, returning empty list")
            return []

    async def get_recent_activity(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent activity for dashboard with input validation.

        Args:
            user_id: User ID to filter by
            tenant_id: Tenant ID to filter by
            limit: Maximum number of activities to return

        Returns:
            List of activity entries (PII sanitized)
        """
        # Validate inputs
        self._validate_identifier(user_id, "user_id")
        self._validate_identifier(tenant_id, "tenant_id")

        end = datetime.utcnow()
        start = end - timedelta(days=30)

        # Query for all activity types from multiple sources
        query = (
            f'{{job=~"mcp-gateway|control-plane-api",tenant_id="{tenant_id}",user_id="{user_id}"}} '
            f'| json '
            f'| event_type=~"subscription.*|api.call|key.rotated"'
        )

        try:
            entries = await self.query_range(query, start, end, limit=limit)
            return self._format_activity_entries(entries or [])
        except CircuitBreakerError:
            logger.warning("Loki circuit breaker open, returning empty list")
            return []

    async def get_recent_errors(
        self,
        tenant_id: str,
        limit: int = 50,
        severity: str = "error",
        from_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent error logs for a tenant with PII sanitization.

        Args:
            tenant_id: Tenant ID to filter by
            limit: Maximum number of errors to return (default: 50)
            severity: Log level to filter by (default: "error", also accepts "warn")
            from_date: Optional start date (default: last 24h)

        Returns:
            List of sanitized error log entries with:
            - timestamp: When the error occurred
            - level: Log level (error, warn)
            - message: Sanitized error message
            - service: Source service name
            - labels: Additional log labels
        """
        # Validate inputs
        self._validate_identifier(tenant_id, "tenant_id")

        # Validate severity
        valid_severities = {"error", "warn", "warning"}
        if severity.lower() not in valid_severities:
            raise ValueError(f"Invalid severity: {severity}. Allowed: error, warn")

        end = datetime.utcnow()
        start = from_date or (end - timedelta(days=1))

        # Build LogQL query for errors
        # Match both error and warning levels if severity is "warn"
        level_filter = 'level=~"error|warn"' if severity.lower() in {"warn", "warning"} else 'level="error"'

        query = (
            f'{{tenant_id="{tenant_id}"}} '
            f'| json '
            f'| {level_filter}'
        )

        try:
            entries = await self.query_range(query, start, end, limit=limit)
            return self._format_error_entries(entries or [])
        except CircuitBreakerError:
            logger.warning("Loki circuit breaker open, returning empty error list")
            return []

    def _format_error_entries(self, entries: List[Dict]) -> List[Dict[str, Any]]:
        """Format log entries as error objects with PII sanitization."""
        errors = []
        for i, entry in enumerate(entries):
            try:
                # Sanitize raw log before parsing
                raw_log = entry.get("raw", "{}")
                sanitized_raw = self._sanitize_log_entry(raw_log)
                log_data = self._parse_log_line(sanitized_raw)
                if not log_data:
                    continue

                # Get the error message and sanitize it
                message = log_data.get("message") or log_data.get("msg") or log_data.get("error") or ""
                if message:
                    message = self._sanitize_log_entry(str(message))

                errors.append({
                    "id": log_data.get("request_id", f"err-{i:04d}"),
                    "timestamp": entry.get("timestamp"),
                    "level": log_data.get("level", "error"),
                    "message": message,
                    "service": log_data.get("service") or entry.get("labels", {}).get("job", "unknown"),
                    "labels": entry.get("labels", {}),
                    "api_id": log_data.get("api_id"),
                    "subscription_id": log_data.get("subscription_id"),
                })
            except Exception as e:
                logger.debug(f"Skipping malformed error entry: {e}")
                continue
        return errors

    # ===== Helper Methods =====

    def _extract_log_entries(self, data: Dict) -> List[Dict[str, Any]]:
        """Extract log entries from Loki response."""
        entries = []
        try:
            for stream in data.get("result", []):
                stream_labels = stream.get("stream", {})
                for value in stream.get("values", []):
                    timestamp_ns, log_line = value
                    entries.append({
                        "timestamp": datetime.utcfromtimestamp(int(timestamp_ns) / 1e9),
                        "raw": log_line,
                        "labels": stream_labels,
                    })
        except Exception as e:
            logger.warning(f"Error extracting log entries: {e}")
        return entries

    def _format_call_entries(self, entries: List[Dict]) -> List[Dict[str, Any]]:
        """Format log entries as UsageCall-compatible objects with PII sanitization."""
        calls = []
        for i, entry in enumerate(entries):
            try:
                # Sanitize raw log before parsing (defense in depth)
                raw_log = entry.get("raw", "{}")
                sanitized_raw = self._sanitize_log_entry(raw_log)
                log_data = self._parse_log_line(sanitized_raw)
                if not log_data:
                    continue

                # Additional sanitization on error messages
                error_message = log_data.get("error")
                if error_message:
                    error_message = self._sanitize_log_entry(str(error_message))

                calls.append({
                    "id": log_data.get("request_id", f"call-{i:04d}"),
                    "timestamp": entry.get("timestamp"),
                    "tool_id": log_data.get("tool_id", "unknown"),
                    "tool_name": log_data.get("tool_name", "Unknown"),
                    "status": log_data.get("status", "success"),
                    "latency_ms": int(log_data.get("duration_ms", 0)),
                    "error_message": error_message,
                })
            except Exception as e:
                logger.debug(f"Skipping malformed call entry: {e}")
                continue
        return calls

    def _format_activity_entries(self, entries: List[Dict]) -> List[Dict[str, Any]]:
        """Format log entries as RecentActivityItem-compatible objects with PII sanitization."""
        activities = []
        for i, entry in enumerate(entries):
            try:
                # Sanitize raw log before parsing (defense in depth)
                raw_log = entry.get("raw", "{}")
                sanitized_raw = self._sanitize_log_entry(raw_log)
                log_data = self._parse_log_line(sanitized_raw)
                if not log_data:
                    continue

                event_type = log_data.get("event_type", "api.call")

                # Additional sanitization on description
                description = log_data.get("description")
                if description:
                    description = self._sanitize_log_entry(str(description))

                activities.append({
                    "id": log_data.get("event_id", f"act-{i:04d}"),
                    "type": event_type,
                    "title": self._get_activity_title(event_type, log_data),
                    "description": description,
                    "tool_id": log_data.get("tool_id"),
                    "tool_name": log_data.get("tool_name"),
                    "timestamp": entry.get("timestamp"),
                })
            except Exception as e:
                logger.debug(f"Skipping malformed activity entry: {e}")
                continue
        return activities

    def _parse_log_line(self, log_line: str) -> Optional[Dict[str, Any]]:
        """Parse a log line as JSON."""
        try:
            return json.loads(log_line)
        except json.JSONDecodeError:
            return None

    def _get_activity_title(self, event_type: str, data: Dict) -> str:
        """Generate human-readable activity title."""
        tool_name = data.get("tool_name", "tool")
        titles = {
            "subscription.created": f"Subscribed to {tool_name}",
            "subscription.approved": f"Subscription approved for {tool_name}",
            "subscription.revoked": f"Subscription revoked for {tool_name}",
            "api.call": f"API call to {tool_name}",
            "key.rotated": f"API key rotated for {tool_name}",
        }
        return titles.get(event_type, f"Activity: {event_type}")


# Global instance
loki_client = LokiClient()
