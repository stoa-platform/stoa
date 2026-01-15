"""
MCP Error Snapshot Models

Pydantic schemas for capturing MCP Gateway errors with full context.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import hashlib
import uuid


class MCPErrorType(str, Enum):
    """Types of MCP errors"""
    # Server errors
    SERVER_TIMEOUT = "server_timeout"
    SERVER_UNAVAILABLE = "server_unavailable"
    SERVER_RATE_LIMITED = "server_rate_limited"
    SERVER_AUTH_FAILURE = "server_auth_failure"
    SERVER_INTERNAL_ERROR = "server_internal_error"

    # Tool errors
    TOOL_NOT_FOUND = "tool_not_found"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    TOOL_VALIDATION_ERROR = "tool_validation_error"
    TOOL_TIMEOUT = "tool_timeout"

    # LLM errors
    LLM_CONTEXT_EXCEEDED = "llm_context_exceeded"
    LLM_CONTENT_FILTERED = "llm_content_filtered"
    LLM_QUOTA_EXCEEDED = "llm_quota_exceeded"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_INVALID_REQUEST = "llm_invalid_request"

    # Policy errors
    POLICY_DENIED = "policy_denied"
    POLICY_ERROR = "policy_error"

    # Generic
    UNKNOWN = "unknown"


class MCPServerContext(BaseModel):
    """Context about the MCP server involved in the error"""
    name: str = Field(..., description="Server name/identifier")
    url: Optional[str] = Field(None, description="Server URL (masked if contains secrets)")
    version: Optional[str] = Field(None, description="Server version")
    tools_available: list[str] = Field(default_factory=list, description="List of available tools")
    health_at_error: Optional[str] = Field(None, description="Server health status at error time")
    latency_p99_ms: Optional[int] = Field(None, description="P99 latency in ms")
    error_rate_percent: Optional[float] = Field(None, description="Recent error rate")


class ToolInvocation(BaseModel):
    """Details of a tool invocation that failed"""
    tool_name: str = Field(..., description="Name of the tool")
    input_params: dict[str, Any] = Field(default_factory=dict, description="Input parameters (masked)")
    input_params_masked: list[str] = Field(default_factory=list, description="List of masked parameter keys")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: int = Field(0, description="Execution duration in ms")
    error_type: Optional[str] = Field(None, description="Error type/class name")
    error_message: Optional[str] = Field(None, description="Error message")
    error_retryable: bool = Field(False, description="Whether the error is retryable")
    backend_status_code: Optional[int] = Field(None, description="Backend HTTP status code")
    backend_response_preview: Optional[str] = Field(None, description="First 500 chars of backend response")


class LLMContext(BaseModel):
    """Context about LLM usage (if applicable)"""
    provider: str = Field(..., description="LLM provider (anthropic, openai, etc.)")
    model: str = Field(..., description="Model identifier")
    tokens_input: int = Field(0, description="Input tokens consumed")
    tokens_output: int = Field(0, description="Output tokens generated")
    estimated_cost_usd: float = Field(0.0, description="Estimated cost in USD")
    latency_ms: int = Field(0, description="LLM call latency")
    error_code: Optional[str] = Field(None, description="LLM-specific error code")
    prompt_length: Optional[int] = Field(None, description="Length of prompt (chars)")
    prompt_hash: Optional[str] = Field(None, description="SHA256 hash of prompt for correlation")


class RetryContext(BaseModel):
    """Information about retry attempts"""
    attempts: int = Field(1, description="Number of attempts made")
    max_attempts: int = Field(3, description="Maximum attempts configured")
    strategy: str = Field("exponential_backoff", description="Retry strategy used")
    delays_ms: list[int] = Field(default_factory=list, description="Delays between attempts")
    fallback_attempted: bool = Field(False, description="Whether fallback was attempted")
    fallback_server: Optional[str] = Field(None, description="Fallback server name if used")
    fallback_result: Optional[str] = Field(None, description="Result of fallback attempt")


class RequestContext(BaseModel):
    """HTTP request context"""
    method: str
    path: str
    query_params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict, description="Masked headers")
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


class UserContext(BaseModel):
    """User/authentication context"""
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


class MCPErrorSnapshot(BaseModel):
    """
    Complete error snapshot for MCP Gateway errors.

    Captures all context needed for time-travel debugging of MCP failures.
    """
    # Identification
    id: str = Field(default_factory=lambda: f"MCP-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Error classification
    error_type: MCPErrorType = Field(..., description="Type of MCP error")
    error_message: str = Field(..., description="Human-readable error message")
    error_code: Optional[str] = Field(None, description="Machine-readable error code")

    # Request context
    request: RequestContext
    response_status: int = Field(500, description="HTTP response status code")

    # User context
    user: Optional[UserContext] = None

    # MCP specific context
    mcp_server: Optional[MCPServerContext] = None
    tool_invocation: Optional[ToolInvocation] = None
    llm_context: Optional[LLMContext] = None
    retry_context: Optional[RetryContext] = None

    # Conversation tracking (for multi-turn debugging)
    conversation_id: Optional[str] = Field(None, description="Conversation/session ID")
    message_index: Optional[int] = Field(None, description="Message index in conversation")

    # Cost tracking
    total_cost_usd: float = Field(0.0, description="Total cost incurred (including wasted)")
    tokens_wasted: int = Field(0, description="Tokens consumed but wasted due to error")

    # Metadata
    gateway_version: str = Field("1.0.0", description="MCP Gateway version")
    environment: str = Field("production", description="Environment (dev, staging, prod)")
    trace_id: Optional[str] = Field(None, description="Distributed trace ID")
    span_id: Optional[str] = Field(None, description="Span ID")

    # PII tracking
    masked_fields: list[str] = Field(default_factory=list, description="List of fields that were masked")

    def to_kafka_message(self) -> dict:
        """Serialize for Kafka publishing"""
        return self.model_dump(mode="json")

    @classmethod
    def generate_prompt_hash(cls, prompt: str) -> str:
        """Generate SHA256 hash of prompt for correlation without storing content"""
        return f"sha256:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"


# Cost constants for estimation
LLM_COST_PER_1K_INPUT_TOKENS = {
    "claude-sonnet-4-20250514": 0.003,
    "claude-opus-4-20250514": 0.015,
    "claude-3-5-sonnet-20241022": 0.003,
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
}

LLM_COST_PER_1K_OUTPUT_TOKENS = {
    "claude-sonnet-4-20250514": 0.015,
    "claude-opus-4-20250514": 0.075,
    "claude-3-5-sonnet-20241022": 0.015,
    "gpt-4o": 0.015,
    "gpt-4o-mini": 0.0006,
}


def estimate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate LLM cost in USD"""
    input_cost = LLM_COST_PER_1K_INPUT_TOKENS.get(model, 0.003) * (input_tokens / 1000)
    output_cost = LLM_COST_PER_1K_OUTPUT_TOKENS.get(model, 0.015) * (output_tokens / 1000)
    return round(input_cost + output_cost, 6)
